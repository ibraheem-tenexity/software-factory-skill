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

    def upload(self, project_id: str, name: str, raw: bytes, tag: str, content_type: str) -> dict:
        """Persist one project material, record its blob, and start asynchronous ingestion."""
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
        )
        logger.info("[ingest] %s: material uploaded — blob %s (%s, %s bytes), ingestion queued",
                    project_id, blob_id, name, len(raw))
        maybe_ingest_async(blob_id, self._console, push_progress=self._push_ingest_progress)
        return self.documents(project_id)

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
        """Delete a project material from storage, memory, source input, and its artifact record."""
        root = self._blobs.get_blob(material_id)
        if not root or root["scope"] != "project" or root["scope_id"] != project_id:
            return None

        memory = MemoryStore()
        for row in self._blobs.descendants(material_id):
            storage.delete_by_path(row["storage_key"])
            memory.delete_document(row["id"])
        self._blobs.delete_tree(material_id)

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
        return self.documents(project_id)

    def summarize(self, project_id: str, blob_id: int) -> dict | None:
        """Regenerate one uploaded project's memory summary."""
        blob = self._blobs.get_blob(blob_id)
        if not blob or blob["scope"] != "project" or blob["scope_id"] != project_id:
            return None
        return memory_ingest.ingest_blob(blob_id, console=self._console, force=True)

    def set_scope(self, project_id: str, material_id: int, scope: str) -> tuple[str, dict | None]:
        """Move one material between project and owner-organization scope."""
        blob = self._blobs.get_blob(material_id)
        if not blob:
            return "not_found", None
        if scope == "org":
            org = self._users.org_for_user(self._records.project_owner(project_id))
            if not org:
                return "no_org", None
            self._blobs.set_scope(material_id, "org", org["id"])
        elif scope == "project":
            self._blobs.set_scope(material_id, "project", project_id)
        else:
            return "invalid_scope", None
        return "ok", self.documents(project_id)
