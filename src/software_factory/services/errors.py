"""Framework-free domain errors raised by the service layer.

Services never raise FastAPI's `HTTPException` (that would couple business logic to the web layer).
They raise these instead; `console/app.py` registers a single handler that maps each to its HTTP
status with the same `{"detail": ...}` body FastAPI's HTTPException produces, so the wire contract
is unchanged.
"""
from __future__ import annotations


class ServiceError(Exception):
    """Base for service-layer failures. `status_code` is the HTTP status the console maps it to."""
    status_code = 400

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class Invalid(ServiceError):
    """Bad input the request schema can't catch (e.g. blank name, malformed base64)."""
    status_code = 400


class NotFound(ServiceError):
    """A referenced resource does not exist or isn't visible to the caller."""
    status_code = 404


class Forbidden(ServiceError):
    """The caller is authenticated but not allowed to perform this action."""
    status_code = 403
