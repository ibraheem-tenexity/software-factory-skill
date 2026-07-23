"""Read-only projections over one project's durable factory records."""
from __future__ import annotations

import json
import logging

from ..db import ProjectStore
from ..projectstate import ProjectState
from ..runtime_agents import AgentRegistry
from ..tickets import TicketStore
from .intake import project_paths

logger = logging.getLogger(__name__)


class ProjectRecords:
    """Own project record reads that do not control stage execution or lifecycle mutation."""

    def __init__(self, projects_dir: str):
        self._projects_dir = projects_dir

    def _paths(self, project_id: str) -> dict:
        return project_paths(self._projects_dir, project_id)

    def _state(self, project_id: str) -> ProjectState:
        return ProjectState.load(project_id, ProjectStore(self._paths(project_id)["db"]))

    def deployments(self, project_id: str) -> dict:
        rows = ProjectStore(self._paths(project_id)["db"]).deployments()
        return {"deployments": rows, "apps": sorted({row["app"] for row in rows if row.get("app")})}

    def tickets(self, project_id: str) -> dict:
        store = TicketStore(self._paths(project_id)["tickets_db"])
        items = [
            {
                "id": ticket.id,
                "title": ticket.title,
                "wave": ticket.wave,
                "status": ticket.status,
                "agent": ticket.agent,
                "provenance": ticket.provenance,
                "provenance_type": ticket.provenance_type,
                "diff_lines": ticket.diff_lines,
                "acceptance": ticket.acceptance,
                "dod": ticket.dod,
                "app": getattr(ticket, "app", None),
                "description": getattr(ticket, "description", ""),
                "goal": getattr(ticket, "goal", ""),
                "design_refs": getattr(ticket, "design_refs", None),
                "dependencies": getattr(ticket, "dependencies", None),
                "scope_genre": getattr(ticket, "scope_genre", None),
                "implementation_notes": getattr(ticket, "implementation_notes", ""),
                "decision_log": getattr(ticket, "decision_log", None),
            }
            for ticket in store.all_tickets()
        ]
        return {"tickets": items, "waves": sorted({ticket["wave"] for ticket in items})}

    def agents(self, project_id: str) -> list[dict]:
        agents = AgentRegistry(self._paths(project_id)["agents_db"]).agents_for(project_id)
        return [
            {
                "agent_id": agent.agent_id,
                "role": agent.role,
                "model": agent.model,
                "phase": agent.phase,
                "status": agent.status,
                "outcome": agent.outcome,
                "ticket_id": agent.ticket_id,
                "cost_usd": agent.cost_usd,
            }
            for agent in agents
        ]

    def artifacts(self, project_id: str) -> list[dict]:
        return ProjectStore(self._paths(project_id)["db"]).artifacts()

    def project_created(self, project_id: str) -> float | None:
        timestamps = [phase["ts"] for phase in ProjectStore(self._paths(project_id)["db"]).phases()
                      if phase.get("ts")]
        return min(timestamps) if timestamps else None

    def project_owner(self, project_id: str) -> str:
        return (self._state(project_id).owner or "").lower()

    def project_name(self, project_id: str) -> str:
        """Operator-chosen display label (falls back to the project_id key). Used to name the
        source-directory root when a scope's tree is created lazily (SOF-253)."""
        return (self._state(project_id).name or "").strip() or project_id

    def project_links(self, project_id: str) -> dict:
        repo = live = None
        for artifact in self.artifacts(project_id):
            path = artifact.get("path") or ""
            if not path.startswith("http"):
                continue
            title = (artifact.get("title") or "").lower()
            kind = (artifact.get("kind") or "").lower()
            if repo is None and ("repo" in title or kind == "repo"):
                repo = path
            elif live is None and ("live" in title or kind == "deploy"):
                live = path
        state = self._state(project_id)
        return {"repo": repo or state.repo_url, "live": live or state.deploy_url}

    def repo_shared_with_owner(self, project_id: str) -> bool:
        return any((artifact.get("kind") or "").lower() == "repo-shared"
                   for artifact in self.artifacts(project_id))

    def events(self, project_id: str) -> list[dict]:
        db = ProjectStore(self._paths(project_id)["db"])
        items = []
        for phase in db.phases():
            items.append({"ts": phase["ts"], "type": "phase",
                          "payload": {"name": phase["name"], "status": phase["status"]}})
        for artifact in db.artifacts():
            # SOF-252: a design-review DECISION (approve/reopen/iterate) is a customer-visible
            # process event, not a produced output — project it as a dedicated "design_review"
            # event carrying the decoded decision payload, not a generic "Produced …" artifact row.
            if (artifact.get("kind") or "").lower() == "design_review":
                payload = {"title": artifact["title"], "path": artifact["path"]}
                try:
                    payload.update(json.loads(artifact.get("content") or "{}"))
                except (ValueError, TypeError):
                    logger.exception("[records] undecodable design_review content on artifact %s",
                                     artifact.get("id"))
                items.append({"ts": artifact["ts"], "type": "design_review", "payload": payload})
                continue
            items.append({"ts": artifact["ts"], "type": "artifact",
                          "payload": {"title": artifact["title"], "path": artifact["path"]}})
        for blocker in db.blockers():
            if not blocker["cleared"]:
                items.append({"ts": blocker["ts"], "type": "blocker", "payload": {"what": blocker["what"]}})
        for verification in db.verifications():
            if verification["passed"]:
                items.append({"ts": verification["ts"], "type": "done", "payload": {"url": verification["url"]}})
        # SOF-188: lifecycle actions (stop/pause/resume/auto-resume/archive/restore) live on the
        # ProjectState JSON blob (NOT the pipeline-only phases table), so /events is a complete
        # account of the run's history — not silent about an operator kill or a host relaunch.
        state = db.read(project_id) or {}
        for entry in state.get("lifecycle") or []:
            payload = {"action": entry.get("action"), "actor": entry.get("actor")}
            if entry.get("reason"):
                payload["reason"] = entry["reason"]
            items.append({"ts": entry.get("ts", 0), "type": "lifecycle", "payload": payload})
        items.sort(key=lambda event: event["ts"])
        return items
