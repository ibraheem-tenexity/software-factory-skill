"""Project-scoped source materials and their durable document projections."""
from __future__ import annotations

import mimetypes
import os
import uuid
from typing import Any, Callable

from .. import project_view, storage
from ..db import ProjectStore
from ..input_pipeline import make_prompt
from ..log import get_logger
from ..memory import ingest as memory_ingest
from ..memory.ingest import maybe_ingest_async
from ..memory.store import MemoryStore
from ..services.errors import Invalid, NotFound, Conflict, Forbidden
from .intake import project_paths

logger = get_logger(__name__)


class ProjectMaterials:
    """Own uploaded project materials, their ingestion, and their document projection."""

    def __init__(
        self,
        projects_dir: str,
        *,
        blobs: Any,
        console: Any,
        records: Any,
        users: Any,
        document_kind: Callable[[str], str],
        push_ingest_progress: Callable[..., None],
    ):
        self._projects_dir = projects_dir
        self._blobs = blobs
        self._console = console
        self._records = records
        self._users = users
        self._document_kind = document_kind
        self._push_ingest_progress = push_ingest_progress

    def documents(self, project_id: str) -> dict:
        """Return project uploads, produced artifacts, and the owner's organization materials."""
        doc_summaries = MemoryStore().list_doc_summaries("project", project_id)
        org = self._users.org_for_user(self._records.project_owner(project_id))
        org_docs = self._blobs.list_org_docs(org["id"]) if org else []
        return project_view.documents(
            self._blobs.list_for("project", project_id),
            self._records.artifacts(project_id),
            doc_summaries,
            org_docs,
        )

    def upload(self, project_id: str, name: str, raw: bytes, tag: str, content_type: str,
               directory_id: str | None = None) -> int:
        """Persist one project source file, record its blob, and start asynchronous ingestion.
        Returns the new blob id (the route picks the projection to return). The blob's directory
        membership is written in the SAME insert as the blob row (see BlobRepository.insert), so a
        successful upload can never leave a blob without its directory. Uploads target THIS
        project's folders — `directory_id` defaults to the project root; an explicit directory must
        be project-scoped (a file is placed in an organization folder by MOVING it, which routes
        through the existing scope-change policy)."""
        directory = self._upload_destination(project_id, directory_id)
        key = f"materials/{uuid.uuid4().hex}-{os.path.basename(name)}"
        storage.put(project_id, key, raw)
        blob_id = self._blobs.record(
            "project",
            project_id,
            f"{project_id}/{key}",
            name=name,
            tag=tag,
            kind=self._document_kind(name),
            content_type=content_type,
            size_bytes=len(raw),
            sha256=storage.sha256(raw),
            directory_id=directory["id"],
        )
        self._blobs.touch_directory(directory["id"])
        logger.info("[ingest] %s: material uploaded — blob %s (%s, %s bytes) in dir %s, ingestion queued",
                    project_id, blob_id, name, len(raw), directory["id"])
        maybe_ingest_async(blob_id, self._console, push_progress=self._push_ingest_progress)
        return blob_id

    def record_draft_attachments(self, project_id: str, files: list[dict]) -> None:
        """Durably store originals attached to a draft and start their document ingestion."""
        input_dir = project_paths(self._projects_dir, project_id)["input_dir"]
        for file in files:
            name = os.path.basename(file.get("name") or "")
            file_path = os.path.join(input_dir, name)
            if not name or not os.path.exists(file_path):
                continue
            with open(file_path, "rb") as source:
                raw = source.read()
            key = f"materials/{uuid.uuid4().hex}-{name}"
            storage.put(project_id, key, raw)
            blob_id = self._blobs.record(
                "project",
                project_id,
                f"{project_id}/{key}",
                name=name,
                kind=self._document_kind(name),
                content_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
                size_bytes=len(raw),
                sha256=storage.sha256(raw),
            )
            logger.info("[ingest] %s: draft attachment stored — blob %s (%s, %s bytes), ingestion queued",
                        project_id, blob_id, name, len(raw))
            maybe_ingest_async(blob_id, self._console, push_progress=self._push_ingest_progress)

    def delete(self, project_id: str, material_id: int) -> dict | None:
        """Delete a project material from storage, memory, source input, and its artifact record.
        Returns the deleted root blob (truthy = found) or None; the route picks the projection."""
        root = self._blobs.get_blob(material_id)
        if not root or root["scope"] != "project" or root["scope_id"] != project_id:
            return None

        member_dir = root.get("directory_id")
        memory = MemoryStore()
        for row in self._blobs.descendants(material_id):
            storage.delete_by_path(row["storage_key"])
            memory.delete_document(row["id"])
        self._blobs.delete_tree(material_id)
        if member_dir:
            # the directory lost a member — its rollup summary is now stale (SOF-253)
            self._blobs.touch_directory(member_dir)

        input_dir = project_paths(self._projects_dir, project_id)["input_dir"]
        name = os.path.basename(root.get("name") or "")
        paths = [name, f"{name}.md"]
        for relative in paths:
            path = os.path.join(input_dir, relative)
            if os.path.exists(path):
                os.remove(path)
        remaining_docs = []
        for blob in self._blobs.list_for("project", project_id):
            if blob.get("source_blob_id") is not None:
                continue
            doc_name = os.path.basename(blob.get("name") or "")
            markdown_path = os.path.join(input_dir, f"{doc_name}.md")
            if os.path.isfile(markdown_path):
                with open(markdown_path) as source:
                    remaining_docs.append((doc_name, source.read()))
        context_path = os.path.join(input_dir, "context.md")
        context = make_prompt("", remaining_docs)
        if context:
            with open(context_path, "w") as target:
                target.write(context)
        else:
            if os.path.exists(context_path):
                os.remove(context_path)
        store = ProjectStore(project_paths(self._projects_dir, project_id)["db"])
        store.delete_artifacts_by_paths([f"input/{relative}" for relative in paths] + ["input/context.md"])
        if context:
            store.record_artifact("input", "input/context.md", kind="context")
        return root

    def summarize(self, project_id: str, blob_id: int) -> dict | None:
        """Regenerate one uploaded project's memory summary."""
        blob = self._blobs.get_blob(blob_id)
        if not blob or blob["scope"] != "project" or blob["scope_id"] != project_id:
            return None
        return memory_ingest.ingest_blob(blob_id, console=self._console, force=True)

    def set_scope(self, project_id: str, material_id: int, scope: str,
                  directory_id: str | None = None) -> dict:
        """Move one source between project and owner-organization scope (PRD §2.4) and re-home it
        under the destination scope's tree (SOF-253 owns the re-home). `blobs.set_scope` NULLs the
        old directory (the old scope's tree can't hold a blob of the new scope); we then file the
        blob under the given destination directory (validated same-scope) or the destination scope
        root. Refusals raise an honest ServiceError; the destination is validated BEFORE the scope
        change so a bad target can't leave the blob moved-but-unfiled."""
        blob = self._blobs.get_blob(material_id)
        if not blob:
            raise NotFound("material not found")
        # The blob must already live in a scope this project may touch (its own project scope or its
        # owner org) — re-scoping is not a way to reach into another tenant's material.
        self._authorize_scope(project_id, blob["scope"], blob["scope_id"])
        if blob.get("source_blob_id") is not None:
            raise Conflict("extracted assets are filed by their source document and cannot be re-scoped")
        if scope == "org":
            org = self._org(project_id)
            if not org:
                raise Conflict("project owner has no org on file")
            dest_scope, dest_scope_id, dest_name = "org", org["id"], (org.get("name") or org["id"])
        elif scope == "project":
            dest_scope, dest_scope_id = "project", project_id
            dest_name = self._records.project_name(project_id)
        else:
            raise Invalid("scope must be 'project' or 'org'")
        if directory_id:
            dest = self._blobs.get_directory(directory_id)
            if not dest or dest["scope"] != dest_scope or dest["scope_id"] != dest_scope_id:
                raise Invalid("destination folder is not in the target scope")
            dest_dir_id = dest["id"]
        else:
            dest_dir_id = self._blobs.ensure_root(dest_scope, dest_scope_id, dest_name)["id"]
        old_dir = blob.get("directory_id")
        self._blobs.set_scope(material_id, dest_scope, dest_scope_id)   # NULLs directory_id
        self._blobs.assign_directory(material_id, dest_dir_id)
        if old_dir:
            self._blobs.touch_directory(old_dir)
        self._blobs.touch_directory(dest_dir_id)
        return blob

    # ── Files browser: directory-aware read model + mutations (SOF-253) ───────────────────────
    def files(self, project_id: str) -> dict:
        """The Files browser read model: the synthesized virtual combined root, this project's
        persisted source root + tree, and the owner-organization's documents/tree. Roots are
        ensured (created lazily if a scope owns no tree yet) so the browser always has real root
        identities to hang folders under. Only the project's own scope + its owner org are read, so
        the payload can never leak another project or organization."""
        self._blobs.ensure_root("project", project_id, self._records.project_name(project_id))
        scopes = [self._scope_bundle("project", project_id)]
        org = self._org(project_id)
        if org:
            self._blobs.ensure_root("org", org["id"], org.get("name") or org["id"])
            scopes.append(self._scope_bundle("org", org["id"]))
        return project_view.files_tree(scopes)

    def _scope_bundle(self, scope: str, scope_id: str) -> dict:
        return {"scope": scope, "scope_id": scope_id,
                "directories": self._blobs.list_directories(scope, scope_id),
                "blobs": self._blobs.list_for(scope, scope_id),
                "doc_summaries": MemoryStore().list_doc_summaries(scope, scope_id)}

    def _org(self, project_id: str) -> dict | None:
        return self._users.org_for_user(self._records.project_owner(project_id))

    def _authorize_scope(self, project_id: str, scope: str, scope_id: str) -> None:
        """A project's Files mutations may only touch the two scopes its read model exposes: its OWN
        project scope, and its owner-organization scope. This mirrors the existing document access
        exactly (project routes already move material to/from the owner org via set_scope) — it does
        not add a new, more-permissive cross-tenant surface. Anything else is another tenant's tree."""
        if scope == "project":
            if scope_id != project_id:
                raise Forbidden("cannot modify another project's files")
        elif scope == "org":
            org = self._org(project_id)
            if not org or scope_id != org["id"]:
                raise Forbidden("cannot modify another organization's files")
        else:
            raise Invalid(f"unknown scope {scope!r}")

    def _resolve_target_dir(self, project_id: str, directory_id: str | None) -> dict:
        """Resolve a mutation's destination directory to a real, authorized directory, or raise.
        A missing directory_id means the virtual Files root, which is never a mutation target."""
        if not directory_id:
            raise Invalid("the Files root is virtual — choose a project or organization folder")
        d = self._blobs.get_directory(directory_id)
        if not d:
            raise NotFound("directory not found")
        self._authorize_scope(project_id, d["scope"], d["scope_id"])
        return d

    def _upload_destination(self, project_id: str, directory_id: str | None) -> dict:
        """Uploads land in THIS project's tree. No directory_id => the project root; an explicit
        directory must be project-scoped (org folders receive files by MOVE, not direct upload, so
        an org KB write still goes through the scope-change policy rather than this route)."""
        if not directory_id:
            return self._blobs.ensure_root("project", project_id, self._records.project_name(project_id))
        d = self._blobs.get_directory(directory_id)
        if not d:
            raise NotFound("directory not found")
        if d["scope"] != "project" or d["scope_id"] != project_id:
            raise Forbidden("uploads target this project's folders — move a file to place it in an "
                            "organization folder")
        return d

    def create_directory(self, project_id: str, parent_id: str | None, name: str) -> dict:
        """Create a child directory under a real, authorized scoped parent. The parent must be a
        real directory (a scope root, or a folder within it) — never the virtual Files root.
        Duplicate sibling names raise a precise 409 (the DB partial-unique index is the backstop)."""
        name = (name or "").strip()
        if not name:
            raise Invalid("folder name required")
        parent = self._resolve_target_dir(project_id, parent_id)
        if self._blobs.sibling_name_exists(parent["scope"], parent["scope_id"], parent["id"], name):
            raise Conflict(f"a folder named “{name}” already exists here")
        self._blobs.create_directory(parent["scope"], parent["scope_id"], parent["id"], name)
        return self.files(project_id)

    def move_file(self, project_id: str, blob_id: int, directory_id: str | None) -> dict:
        """Move an existing source among directories WITHIN its own scope. The destination must be a
        real directory in the same scope as the blob (a cross-scope move goes through set_scope).
        Extracted-child assets are filed by their source document and cannot be moved directly."""
        blob = self._blobs.get_blob(blob_id)
        if not blob:
            raise NotFound("file not found")
        if blob.get("source_blob_id") is not None:
            raise Conflict("extracted assets are filed by their source document and cannot be moved")
        self._authorize_scope(project_id, blob["scope"], blob["scope_id"])
        dest = self._resolve_target_dir(project_id, directory_id)
        if dest["scope"] != blob["scope"] or dest["scope_id"] != blob["scope_id"]:
            raise Invalid("that folder is in a different scope — use a cross-scope move to change scope")
        old_dir = blob.get("directory_id")
        self._blobs.assign_directory(blob_id, dest["id"])
        for d in {old_dir, dest["id"]}:
            if d:
                self._blobs.touch_directory(d)
        return self.files(project_id)
