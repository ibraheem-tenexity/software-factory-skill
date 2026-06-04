"""Proposal §4 — memory & context architecture, made concrete + testable.

Pull-not-push memory with the proposal's namespaces (project/<id>, run/<id>, tickets/<id>,
coordination) and a ReasoningBank precedent loop (record trajectory→verdict, recall by
similarity, consolidate = distill+prune between phases). In production these bind to ruflo over
MCP; this module is the namespace + precedent CONVENTION plus a local fallback store so the
behaviour is deterministic and unit-testable.
"""
from software_factory import memory


def test_namespaces_match_the_proposal(tmp_path):
    assert memory.project_ns("p1") == "project/p1"
    assert memory.run_ns("r1") == "run/r1"
    assert memory.ticket_ns("7") == "tickets/7"
    assert memory.COORDINATION == "coordination"


def test_write_read_roundtrip(tmp_path):
    store = memory.MemoryStore(str(tmp_path))
    store.write(memory.run_ns("r1"), "prd", {"problem": "x"})
    assert store.read(memory.run_ns("r1"), "prd")["problem"] == "x"


def test_search_pulls_by_relevance(tmp_path):
    store = memory.MemoryStore(str(tmp_path))
    store.write("coordination", "swarm/a/status", {"text": "building the guestbook form"})
    store.write("coordination", "swarm/b/status", {"text": "wiring supabase auth"})
    hits = store.search("coordination", "guestbook")
    assert any("guestbook" in str(h).lower() for h in hits)
    assert all("supabase" not in str(h).lower() for h in hits)


def test_reasoningbank_record_then_recall(tmp_path):
    store = memory.MemoryStore(str(tmp_path))
    memory.record_precedent(store, memory.project_ns("p1"),
                            trajectory="added supabase RLS policy then 401 went away",
                            verdict="success", confidence=0.9)
    hits = memory.recall_precedent(store, memory.project_ns("p1"), "supabase 401")
    assert hits and hits[0]["verdict"] == "success"
    assert hits[0]["success_count"] >= 1


def test_consolidate_distills_and_prunes(tmp_path):
    store = memory.MemoryStore(str(tmp_path))
    ns = memory.project_ns("p1")
    for i in range(10):
        memory.record_precedent(store, ns, trajectory=f"attempt {i}", verdict="fail" if i % 2 else "success",
                                confidence=i / 10)
    memory.consolidate(store, ns, keep=3)
    remaining = memory.recall_precedent(store, ns, "attempt")
    assert len(remaining) == 3                      # pruned to the top-N
    assert remaining[0]["confidence"] >= remaining[-1]["confidence"]  # distilled by confidence
