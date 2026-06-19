"""Per-run schema versioning for the schema-per-run model.

Alembic owns the GLOBAL `public` tables (see migrations/). But each run lives in its own
`sf_run_<id>` schema, and Alembic can't iterate dynamically-named schemas — so per-run schema
changes are versioned here and applied by a **fan-out** (software_factory.migrate) across every
`sf_run_*` schema, with each schema's version recorded in `public.sf_run_schema_version`.

Adding a per-run schema change later = append a revision below with its UNQUALIFIED, idempotent
DDL (statements run with `search_path` set to the target schema). v0001 is the baseline: the per-run
tables are created by the store constructors (db.py / tickets.py / agents.py) on first write, so the
baseline applies no DDL — it only establishes the version that new + existing schemas are stamped at.
"""
from __future__ import annotations

# Ordered list of (version, [SQL statements]). Append-only.
PER_RUN_REVISIONS: list[tuple[str, list[str]]] = [
    ("0001", []),   # baseline — tables self-created by the stores; nothing to apply
    # Example of a future revision:
    # ("0002", ['ALTER TABLE tickets ADD COLUMN IF NOT EXISTS priority integer NOT NULL DEFAULT 0']),
]


def per_run_head() -> str:
    return PER_RUN_REVISIONS[-1][0]


def _index_of(version: str | None) -> int:
    """Index of `version` in the revision list, or -1 if None/unknown (→ apply everything)."""
    if version is None:
        return -1
    for i, (v, _) in enumerate(PER_RUN_REVISIONS):
        if v == version:
            return i
    return -1


def pending_per_run(from_version: str | None) -> list[tuple[str, list[str]]]:
    """Revisions strictly newer than `from_version`, in order."""
    return PER_RUN_REVISIONS[_index_of(from_version) + 1:]
