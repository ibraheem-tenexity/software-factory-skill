"""Service layer: application/business logic that sits between the HTTP routers (console/) and the
data-access Stores. Services own validation, orchestration, cross-store aggregation, and caching
policy; they are framework-free (no FastAPI types) and signal failures with the domain errors in
`errors.py`, which the console maps to HTTP status codes. See docs/ARCHITECTURE.md.
"""
