"""Compatibility exports for the pre-refactor console module.

Execution now belongs to ``software_factory.execution.service``. This module remains while
operator scripts and external callers migrate, so existing import paths keep their behavior.
"""
from .execution import service as _service

globals().update(
    (name, value)
    for name, value in vars(_service).items()
    if not name.startswith("__")
)

Console = ExecutionService
