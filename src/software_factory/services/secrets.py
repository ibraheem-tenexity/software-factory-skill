"""In-memory mock secrets vault — stands in until the DB agent ships migration 0008 + org_secrets table."""
import time

from software_factory.services.errors import ServiceError


class Secrets:
    def __init__(self):
        self._store: dict = {}  # org_id → {name → {kind, last4, used_by, updated_at}}

    def _org(self, org_id: str) -> dict:
        return self._store.setdefault(org_id, {})

    def list(self, org_id: str) -> list[dict]:
        return [{"name": k, **v} for k, v in self._org(org_id).items()]

    def create(self, org_id: str, name: str, value: str, kind: str) -> dict:
        org = self._org(org_id)
        if name in org:
            raise ServiceError(409, f"secret '{name}' already exists")
        org[name] = {"kind": kind, "last4": value[-4:], "used_by": 0, "updated_at": _now()}
        return {"name": name, **org[name]}

    def rotate(self, org_id: str, name: str, value: str) -> dict:
        org = self._org(org_id)
        if name not in org:
            raise ServiceError(404, f"secret '{name}' not found")
        org[name]["last4"] = value[-4:]
        org[name]["updated_at"] = _now()
        return {"name": name, **org[name]}

    def delete(self, org_id: str, name: str) -> None:
        org = self._org(org_id)
        if name not in org:
            raise ServiceError(404, f"secret '{name}' not found")
        del org[name]

    def get_ref(self, org_id: str, name: str) -> dict:
        org = self._org(org_id)
        if name not in org:
            raise ServiceError(404, f"secret '{name}' not found")
        return {"name": name, "kind": org[name]["kind"]}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
