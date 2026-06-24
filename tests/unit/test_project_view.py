"""Project View §2.5 pure assemblers — Overview build status / services / agents, Documents lists."""
from software_factory import project_view as pv


def test_build_status_computes_pct_and_counts():
    status = {"agents": {"running": 3, "done": 5}, "spent_usd": 4.201, "budget_ceiling": 30.0,
              "done": False, "deploy_url": ""}
    tickets = [{"id": 1, "status": "done"}, {"id": 2, "status": "deployed"},
               {"id": 3, "status": "open"}, {"id": 4, "status": "in_progress"}]
    b = pv.build_status(status, tickets)
    assert b["tickets_total"] == 4 and b["tickets_done"] == 2
    assert b["pct"] == 50
    assert b["agents_working"] == 3
    assert b["spent_usd"] == 4.20 and b["budget_ceiling"] == 30.0
    assert b["done"] is False and b["deploy_url"] == ""


def test_build_status_no_tickets_is_zero_pct():
    b = pv.build_status({"agents": {}}, [])
    assert b["pct"] == 0 and b["tickets_total"] == 0 and b["agents_working"] == 0


def test_services_at_work_from_real_signals_only():
    org = {"connected_systems": ["epicor"]}
    deployments = [{"service_name": "sf-project-ab12", "app": "web", "url": "https://x", "status": "live"}]
    svc = pv.services_at_work(org, deployments, impl_model="claude-opus-4-8",
                              has_verification=True, in_build=True)
    kinds = [(s["kind"], s["label"], s["status"]) for s in svc]
    assert ("Integration", "epicor", "connected") in kinds
    assert ("Hosting", "sf-project-ab12", "live") in kinds
    assert ("LLM", "claude-opus-4-8", "active") in kinds
    assert ("Testing", "Playwright", "passed") in kinds
    host = next(s for s in svc if s["kind"] == "Hosting")
    assert host["url"] == "https://x" and host["detail"] == "web"


def test_services_omits_absent_signals_and_testing_running_in_build():
    svc = pv.services_at_work(None, [], impl_model="", has_verification=False, in_build=True)
    assert svc == [{"label": "Playwright", "kind": "Testing", "status": "running",
                    "detail": "e2e verification", "url": None}]
    assert pv.services_at_work(None, [], "", False, False) == []   # nothing at all


def test_agents_projection_joins_ticket_title():
    agents = [{"role": "opus", "model": "m1", "status": "running", "ticket_id": 7, "cost_usd": 1.1009},
              {"role": "qa", "model": "m2", "status": "done", "ticket_id": None, "cost_usd": 0}]
    tickets = [{"id": 7, "title": "Discount approval workflow"}]
    a = pv.agents_projection(agents, tickets)
    assert a[0] == {"role": "opus", "model": "m1", "status": "running",
                    "task": "Discount approval workflow", "cost_usd": 1.1009}
    assert a[1]["task"] == ""        # no ticket → empty task


def test_documents_uploaded_name_from_storage_key_and_kind():
    blobs = [{"storage_key": "project-abc/inputs/sample-rfq-email.pdf", "size_bytes": 94208,
              "content_type": "application/pdf", "created_at": 1718000000.0}]
    artifacts = [{"title": "Architecture", "path": "workspace/ARCHITECTURE.md", "kind": "plan",
                  "agent": "architect", "ts": 1718000500.0}]
    d = pv.documents(blobs, artifacts)
    up = d["uploaded"][0]
    assert up["name"] == "sample-rfq-email.pdf" and up["kind"] == "pdf"
    assert up["size_bytes"] == 94208 and up["storage_key"].endswith("sample-rfq-email.pdf")
    assert d["produced"][0]["title"] == "Architecture" and d["produced"][0]["kind"] == "plan"


def test_documents_produced_items_carry_artifact_id():
    # The artifact viewer opens by stable integer id — produced items MUST include it.
    artifacts = [{"id": 7, "title": "Arch", "path": "arch.md", "kind": "plan",
                  "agent": "architect", "ts": 1718000500.0}]
    d = pv.documents([], artifacts)
    assert d["produced"][0]["id"] == 7


def test_documents_produced_id_is_none_when_missing():
    artifacts = [{"title": "Arch", "path": "arch.md", "kind": "plan", "agent": "a", "ts": 1.0}]
    d = pv.documents([], artifacts)
    assert d["produced"][0]["id"] is None


def test_brief_block_pulls_goal_scope_from_project_and_owner_from_status():
    project = {"name": "Quote-to-Epicor", "goal": "automate quoting",
               "scope": ["Quoting / RFQ", "Pricing"], "description": "composed"}
    status = {"owner": "op@acme.com", "phase": "Build · stage 3", "stage": 3, "description": "composed"}
    b = pv.brief_block(project, status, created=1718000000.0)
    assert b["name"] == "Quote-to-Epicor" and b["goal"] == "automate quoting"
    assert b["scope"] == ["Quoting / RFQ", "Pricing"]
    assert b["owner"] == "op@acme.com" and b["stage"] == 3 and b["created"] == 1718000000.0
