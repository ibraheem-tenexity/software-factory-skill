"""Pure CRUD for the seven project-scoped "canvas" tables (SQLAlchemy Core): projectstate, phases,
artifacts, blockers, gates, verifications, deployments. One repository class per table — same-table
access stays together, never split — grouped in this one module because all seven are consumed
exclusively by `ProjectStore` (db.py).

Per-project repos take a `PathExec` lane + a live `project_id` getter (a zero-arg callable read on
every query, per the #200 canary fix), except `ProjectStateRepository`, whose `read`/`write` already
take an explicit `project_id` per call (the `ProjectState` Store protocol's own parameter — mirrors
the original raw SQL, which used the passed argument, not the store's own scoping id).
"""
from __future__ import annotations

from sqlalchemy import select, insert, update, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import projectstate, phases, artifacts, blockers, gates, verifications, deployments


class ProjectStateRepository:
    def __init__(self, exec_):
        self._x = exec_

    def upsert(self, project_id: str, data: str, name, summary) -> None:
        stmt = pg_insert(projectstate).values(project_id=project_id, data=data, name=name, summary=summary)
        stmt = stmt.on_conflict_do_update(
            index_elements=["project_id"],
            set_={"data": stmt.excluded.data, "name": stmt.excluded.name, "summary": stmt.excluded.summary})
        self._x.execute(stmt)

    def by_project(self, project_id: str):
        return self._x.fetchone(
            select(projectstate.c.data, projectstate.c.name, projectstate.c.summary)
            .where(projectstate.c.project_id == project_id))


class PhaseRepository:
    def __init__(self, exec_, project_id):
        self._x, self._pid = exec_, project_id

    def insert(self, name, status, stage, ts) -> None:
        self._x.execute(insert(phases).values(project_id=self._pid(), name=name, status=status,
                                              stage=stage, ts=ts))

    def all_for_project(self) -> list:
        return self._x.fetchall(select(phases).where(phases.c.project_id == self._pid())
                                .order_by(phases.c.ts, phases.c.id))


class ArtifactRepository:
    def __init__(self, exec_, project_id):
        self._x, self._pid = exec_, project_id

    def insert(self, title, path, kind, agent, ts) -> None:
        self._x.execute(insert(artifacts).values(project_id=self._pid(), title=title, path=path,
                                                 kind=kind, agent=agent, ts=ts))

    def all_for_project(self) -> list:
        return self._x.fetchall(select(artifacts).where(artifacts.c.project_id == self._pid())
                                .order_by(artifacts.c.id))

    def by_id_global(self, artifact_id: int):
        """Cross-project lookup by primary key — used by GET /api/artifacts/{id}, not scoped by
        project_id (mirrors the original: a fresh global connection, not this store's path)."""
        return self._x.fetchone(select(artifacts).where(artifacts.c.id == artifact_id))


class BlockerRepository:
    def __init__(self, exec_, project_id):
        self._x, self._pid = exec_, project_id

    def insert(self, what, blocks, ts) -> None:
        self._x.execute(insert(blockers).values(project_id=self._pid(), what=what, blocks=blocks, ts=ts))

    def clear(self, what) -> None:
        self._x.execute(update(blockers)
                        .where(blockers.c.project_id == self._pid(), blockers.c.what == what)
                        .values(cleared=1))

    def all_for_project(self) -> list:
        return self._x.fetchall(select(blockers).where(blockers.c.project_id == self._pid())
                                .order_by(blockers.c.id))


class GateRepository:
    def __init__(self, exec_, project_id):
        self._x, self._pid = exec_, project_id

    def upsert(self, name, status, ts) -> None:
        stmt = pg_insert(gates).values(project_id=self._pid(), name=name, status=status, ts=ts)
        stmt = stmt.on_conflict_do_update(index_elements=["project_id", "name"],
                                          set_={"status": stmt.excluded.status, "ts": stmt.excluded.ts})
        self._x.execute(stmt)

    def all_for_project(self) -> list:
        return self._x.fetchall(select(gates.c.name, gates.c.status)
                                .where(gates.c.project_id == self._pid()))


class VerificationRepository:
    def __init__(self, exec_, project_id):
        self._x, self._pid = exec_, project_id

    def insert(self, url, passed, result, ts) -> None:
        self._x.execute(insert(verifications).values(project_id=self._pid(), url=url, passed=passed,
                                                     result=result, ts=ts))

    def all_for_project(self) -> list:
        return self._x.fetchall(select(verifications).where(verifications.c.project_id == self._pid())
                                .order_by(verifications.c.id))

    def passing_count(self) -> int:
        row = self._x.fetchone(select(func.count().label("n"))
                               .where(verifications.c.project_id == self._pid(),
                                      verifications.c.passed == 1))
        return row["n"]


class DeploymentRepository:
    def __init__(self, exec_, project_id):
        self._x, self._pid = exec_, project_id

    def insert(self, app, service_name, url, status, verified, ts) -> None:
        self._x.execute(insert(deployments).values(project_id=self._pid(), app=app,
                                                   service_name=service_name, url=url, status=status,
                                                   verified=verified, ts=ts))

    def all_for_project(self) -> list:
        return self._x.fetchall(select(deployments).where(deployments.c.project_id == self._pid())
                                .order_by(deployments.c.id))
