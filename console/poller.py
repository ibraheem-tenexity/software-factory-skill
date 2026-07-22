"""Compatibility imports for the worker supervisor.

The autonomy loop lives in ``software_factory.workers.supervisor``. Keep this
module while active operator and test callers migrate from the old console path.
"""
from software_factory.workers import supervisor as _supervisor

globals().update(
    (name, value)
    for name, value in vars(_supervisor).items()
    if not name.startswith("__")
)
