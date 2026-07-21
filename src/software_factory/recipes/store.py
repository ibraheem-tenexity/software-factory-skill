"""Repo-backed recipes (CBT-9) — the `recipes/` bounded context: table CRUD, the one repo-validity
fact gate, and the queries `conversation`/`projects`/`console` consume.

DATA ACCESS: `recipes/` is a fresh bounded context, not a repositories/ pair — this store owns its
SQLAlchemy Core statements over GlobalExec directly (no pass-through repository for a single
caller; see docs/STRUCTURE.md's note that store/repository pairs which only delegate are a
consolidation target, not a pattern to keep multiplying).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Optional

from sqlalchemy import select, insert, update, func

from ..models import recipes
from ..repositories._exec import GlobalExec
from ..repositories._compile import epoch_cast, serialize_jsonb, uuid_str_cast

_COLS = (
    uuid_str_cast(recipes.c.id).label("id"),
    recipes.c.name, recipes.c.tagline, recipes.c.category, recipes.c.capabilities,
    recipes.c.body_md, recipes.c.repo_url, recipes.c.images, recipes.c.status,
    epoch_cast(recipes.c.created_at).label("created_at"),
    epoch_cast(recipes.c.updated_at).label("updated_at"),
)

# Customer-facing picker source: light fields only — no body_md, no internal repo_url.
_LIGHT_COLS = (
    uuid_str_cast(recipes.c.id).label("id"), recipes.c.name, recipes.c.tagline,
    recipes.c.category, recipes.c.capabilities, recipes.c.images,
)

_FIELDS = {"name", "tagline", "category", "capabilities", "body_md", "repo_url", "images", "status"}
_JSONB_FIELDS = ("capabilities", "images")


class RecipeValidationError(Exception):
    """Raised with the honest, user-visible reason a recipe save was refused."""


def _validate_repo(repo_url: str) -> None:
    """Shallow-clone to a temp dir; require AGENTS.md or CLAUDE.md at the root. File-EXISTS fact
    check only (philosophy: gates check facts, not judgment). Clone is discarded."""
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(["git", "clone", "--depth", "1", repo_url, tmp],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RecipeValidationError(
                f"could not clone {repo_url}: {(r.stderr or r.stdout).strip()[-500:]}")
        if not (os.path.exists(os.path.join(tmp, "AGENTS.md"))
                or os.path.exists(os.path.join(tmp, "CLAUDE.md"))):
            raise RecipeValidationError(
                f"{repo_url} has no AGENTS.md or CLAUDE.md at the repo root — a recipe repo "
                f"must document its architecture/extension points before it can be saved")


class RecipeStore:
    """CRUD store for the recipes table. Staff-authored (Tenexity OS); customers only ever see
    `published()`'s light fields of `status='published'` rows."""

    def __init__(self):
        self._x = GlobalExec()

    def list_all(self) -> list[dict]:
        return self._x.fetchall(
            select(*_COLS).select_from(recipes).order_by(recipes.c.created_at.desc()))

    def get(self, recipe_id: str) -> Optional[dict]:
        return self._x.fetchone(
            select(*_COLS).select_from(recipes).where(recipes.c.id == recipe_id))

    def create(self, name: str, **fields) -> dict:
        repo_url = fields.get("repo_url")
        if repo_url:
            _validate_repo(repo_url)
        vals = {k: fields.get(k) for k in _FIELDS if k != "name"}
        vals["name"] = name
        for jf in _JSONB_FIELDS:
            vals[jf] = serialize_jsonb(vals.get(jf), default=[])
        vals["status"] = vals.get("status") or "draft"
        stmt = insert(recipes).values(**vals).returning(*_COLS)
        return self._x.fetchone(stmt)

    def update(self, recipe_id: str, fields: dict) -> Optional[dict]:
        updates = {k: v for k, v in fields.items() if k in _FIELDS and v is not None}
        if not updates:
            return self.get(recipe_id)
        if updates.get("repo_url"):
            _validate_repo(updates["repo_url"])
        for jf in _JSONB_FIELDS:
            if jf in updates:
                updates[jf] = serialize_jsonb(updates[jf], default=[])
        stmt = (update(recipes).where(recipes.c.id == recipe_id)
                .values(**updates, updated_at=func.now()).returning(*_COLS))
        return self._x.fetchone(stmt)

    def published(self) -> list[dict]:
        """The intake picker source: `status='published'` rows, light fields — a data filter, not
        a judgment. Only public images are ever returned to a customer-facing caller."""
        rows = self._x.fetchall(
            select(*_LIGHT_COLS).select_from(recipes)
            .where(recipes.c.status == "published").order_by(recipes.c.name))
        for r in rows:
            r["images"] = [i for i in (r.get("images") or []) if i.get("public")]
        return rows

    def body(self, recipe_id: str) -> Optional[str]:
        row = self._x.fetchone(
            select(recipes.c.body_md).select_from(recipes).where(recipes.c.id == recipe_id))
        return row["body_md"] if row else None

    def repo_url(self, recipe_id: str) -> Optional[str]:
        row = self._x.fetchone(
            select(recipes.c.repo_url).select_from(recipes).where(recipes.c.id == recipe_id))
        return row["repo_url"] if row else None
