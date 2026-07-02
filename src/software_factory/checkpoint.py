"""Immutable per-node checkpoints — the durable backbone of crash/pause recovery.

A checkpoint records that a pipeline node completed successfully. Once written it is
immutable (INSERT … ON CONFLICT DO NOTHING) so a double-write never corrupts state.
Retrying or rewinding a node deletes its checkpoint and all downstream ones, then the
stage relaunches — upstream nodes whose checkpoints survive are skipped.

NODE_ORDER is the canonical pipeline sequence. Nodes are addressed by their existing
`phases` names (extract / provision / research / product / architect / design / tickets /
build / deploy / test / teardown) plus "stage:1" / "stage:2" / "stage:3" as coarse
stage-boundary markers that are set by the console when it detects stage completion.
"""
from __future__ import annotations

import time

from .repositories._exec import GlobalExec
from .repositories.checkpoint import CheckpointRepository

# All `checkpoint` SQL lives in CheckpointRepository (SQLAlchemy Core, global lane). This module keeps
# the pipeline ordering + invalidation logic and the thin function API its callers already use.
_repo = CheckpointRepository(GlobalExec())

# Ordered pipeline — position is the invalidation key.  A rewind-to or retry-from
# node N deletes checkpoints at positions >= pos(N).
NODE_ORDER: tuple[str, ...] = (
    "stage:1",          # coarse: whole stage 1 done
    "extract",
    "provision",
    "research",
    "product",
    "stage:2",          # coarse: whole stage 2 done
    "architect",
    "design",
    "tickets",
    "stage:3",          # coarse: whole stage 3 done
    "build",
    "deploy",
    "test",
    "teardown",
)


def _node_pos(node: str) -> int:
    """Position in NODE_ORDER, or len(NODE_ORDER) for unknown nodes (ticket:<id> etc.)."""
    try:
        return NODE_ORDER.index(node)
    except ValueError:
        return len(NODE_ORDER)


def write(project_id: str, node: str, output: dict | None = None) -> bool:
    """Record node as done. Idempotent — ON CONFLICT DO NOTHING means a second write
    for the same (project_id, node) is silently ignored, preserving the original.
    Returns True if a new row was inserted, False if it already existed."""
    return _repo.insert_if_absent(project_id, node, output, time.time())


def completed_nodes(project_id: str) -> set[str]:
    """Set of node names that have a checkpoint (= confirmed done)."""
    return {r["node"] for r in _repo.nodes_for(project_id)}


def delete_from(project_id: str, node: str) -> list[str]:
    """Delete the checkpoint for `node` AND all downstream nodes (position >= pos(node)).
    Returns the list of node names deleted. Ticket checkpoints (ticket:<id>) are always
    deleted together when their containing 'build' node is invalidated."""
    pos = _node_pos(node)
    # Nodes at or after `node` in the ordered pipeline
    to_delete_ordered = [n for n in NODE_ORDER if _node_pos(n) >= pos]
    rows = _repo.delete_nodes(project_id, to_delete_ordered)
    return [r["node"] for r in rows]
