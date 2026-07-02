"""SOF-61 regression guard: every migrations/versions/*.py revision must be frozen DDL, never a
live dependency on `software_factory.models`. A revision file that imports the live models module
breaks the moment a later commit renames/removes a table it references (exactly how 0002-0005
broke when c97c7eb dropped `models.agent_prompts`/`agent_registry`) — a fresh-DB `alembic upgrade
head` replays every revision in order and has no way to know the module has moved on.

Only the import/attribute-access pattern is checked, not the substring "models." anywhere in a
file — several revisions legitimately mention `models.metadata` in their docstrings to document
what they used to do before being frozen. `migrations/env.py` imports `models` for Alembic's
`target_metadata` (autogenerate support) and is explicitly out of scope; it isn't a revision file.
"""
import re
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "versions"

_LIVE_MODELS_IMPORT = re.compile(
    r"^\s*(from\s+software_factory\s+import\s+models\b|import\s+software_factory\.models\b)",
    re.MULTILINE,
)


def test_no_revision_imports_the_live_models_module():
    # A relocated/renamed versions dir would make the glob below match nothing and this test would
    # silently pass with zero offenders — assert the directory is actually there so that fails loud.
    assert VERSIONS_DIR.is_dir(), f"expected migrations/versions at {VERSIONS_DIR}"
    offenders = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if _LIVE_MODELS_IMPORT.search(path.read_text()):
            offenders.append(path.name)
    assert not offenders, (
        f"migrations/versions files must be frozen (inline DDL only), not import the live "
        f"models module: {offenders}"
    )
