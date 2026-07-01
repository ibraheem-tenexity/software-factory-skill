#!/usr/bin/env python3
"""Import-smoke check — run at Docker build time (see Dockerfile) so a Python dependency that's
declared in pyproject.toml but not actually installed (or used in code but never declared) fails
the BUILD, not a live deploy. Root-caused by #237: pgvector was added to pyproject.toml but not to
the Dockerfile's separately-hand-maintained pip3 line, crash-looping prod on the next deploy.

SOF-48's fix makes pyproject.toml the single source of truth (the Dockerfile now runs
`pip install /app`, no separate list) — this script is the safety net on top of that: it also
explicitly imports every KNOWN LAZY (function-local, not module-top-level) third-party import,
since a plain module walk can't see those and pip installing a broken/incompatible package can
still succeed while the import itself fails (e.g. a C-extension ABI mismatch).

No DB/network required: GlobalExec()-backed constructors are lazy-connect, and the stores' own
eager seed calls are wrapped in try/except (confirmed: `import console.app` with zero env vars set
completes in under 2 seconds) — so this is safe and fast to run with no service configuration.
"""
import importlib
import pkgutil
import sys

# Add here whenever a new function-local (not top-of-file) third-party import is introduced,
# alongside its pyproject.toml declaration — a plain module walk cannot see these.
_LAZY_IMPORTS = ["markitdown", "pypandoc", "mammoth", "markdownify"]

failures = []


def _walk(package_name):
    pkg = importlib.import_module(package_name)
    if not hasattr(pkg, "__path__"):
        return
    for info in pkgutil.walk_packages(pkg.__path__, prefix=package_name + "."):
        try:
            importlib.import_module(info.name)
        except Exception as e:
            failures.append((info.name, e))


for name in ("software_factory", "console"):
    try:
        _walk(name)
    except Exception as e:
        failures.append((name, e))

for name in _LAZY_IMPORTS:
    try:
        importlib.import_module(name)
    except Exception as e:
        failures.append((name, e))

if failures:
    print("verify_deps: IMPORT FAILURES:", file=sys.stderr)
    for name, e in failures:
        print(f"  {name}: {e!r}", file=sys.stderr)
    sys.exit(1)

print(f"verify_deps: OK — software_factory + console modules and {len(_LAZY_IMPORTS)} "
      f"known lazy-import packages all resolve cleanly")
