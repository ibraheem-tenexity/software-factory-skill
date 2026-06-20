"""Org knowledge-base documents — BlobStore org-scoped doc index + reuse count (PRD §2.3)."""
import pytest

from software_factory.blobs import BlobStore


@pytest.fixture()
def store():
    return BlobStore()


def test_record_org_doc_with_name_and_tag_returns_id(store):
    bid = store.record("org", "org-1", "org/org-1/kb/pricing.xlsx", name="standard-pricing.xlsx",
                       tag="Price book", kind="xlsx", content_type="application/vnd.ms-excel",
                       size_bytes=142_000)
    assert isinstance(bid, int)
    docs = store.list_org_docs("org-1")
    assert len(docs) == 1
    d = docs[0]
    assert d["id"] == bid
    assert d["name"] == "standard-pricing.xlsx"
    assert d["tag"] == "Price book"
    assert d["kind"] == "xlsx"
    assert d["size_bytes"] == 142_000
    assert d["content_type"] == "application/vnd.ms-excel"
    assert d["used_count"] == 0            # nothing has imported it yet
    assert d["updated"] > 0                 # epoch seconds


def test_list_org_docs_scoped_to_one_org(store):
    store.record("org", "org-1", "k1", name="a")
    store.record("org", "org-2", "k2", name="b")
    store.record("project", "project-x", "k3", name="c")   # project-scoped material, not an org doc
    docs = store.list_org_docs("org-1")
    assert [d["name"] for d in docs] == ["a"]


def test_record_use_counts_distinct_runs(store):
    bid = store.record("org", "org-1", "k1", name="a")
    assert store.record_use(bid, "project-1") == 1
    assert store.record_use(bid, "project-1") == 1     # same project again → still 1 (distinct)
    assert store.record_use(bid, "project-2") == 2
    assert store.list_org_docs("org-1")[0]["used_count"] == 2


def test_delete_org_doc_removes_row_and_its_uses(store):
    bid = store.record("org", "org-1", "k1", name="a")
    store.record_use(bid, "project-1")
    store.delete(bid)
    assert store.list_org_docs("org-1") == []
    assert store.get_blob(bid) is None


def test_get_blob_returns_storage_key_and_scope(store):
    bid = store.record("org", "org-1", "org/org-1/kb/x", name="a")
    b = store.get_blob(bid)
    assert b["storage_key"] == "org/org-1/kb/x"
    assert b["scope"] == "org"
    assert b["scope_id"] == "org-1"
