"""Proposal §4 — pull-not-push memory + ReasoningBank precedent loop.

Namespaces match the proposal: project/<id>, run/<id>, tickets/<id>, coordination. Agents PULL
the slice they need (never a pushed bundle). The ReasoningBank loop records each agent's
trajectory→verdict, recalls precedent by similarity (with confidence/success counts), and
consolidates (distill + prune) between phases so memory stays small.

In production this binds to ruflo over MCP (memory_usage / retrieveWithReasoning); here it is the
namespace + precedent convention plus a local JSON fallback store, so the behaviour is
deterministic and unit-testable and the skill degrades gracefully if ruflo is absent.
"""
from __future__ import annotations

import json
import os
import time

COORDINATION = "coordination"


def project_ns(pid: str) -> str:
    return f"project/{pid}"


def run_ns(rid: str) -> str:
    return f"run/{rid}"


def ticket_ns(tid) -> str:
    return f"tickets/{tid}"


class MemoryStore:
    """Local fallback brain: one JSON file per namespace. (ruflo AgentDB in production.)"""

    def __init__(self, path: str):
        self._dir = path
        os.makedirs(path, exist_ok=True)

    def _file(self, namespace: str) -> str:
        safe = namespace.replace("/", "__")
        return os.path.join(self._dir, f"{safe}.json")

    def _load(self, namespace: str) -> dict:
        try:
            with open(self._file(namespace)) as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _save(self, namespace: str, data: dict) -> None:
        with open(self._file(namespace), "w") as f:
            json.dump(data, f, indent=2)

    def write(self, namespace: str, key: str, value) -> None:
        data = self._load(namespace)
        data[key] = value
        self._save(namespace, data)

    def read(self, namespace: str, key: str):
        return self._load(namespace).get(key)

    def search(self, namespace: str, query: str) -> list:
        """Relevance pull — substring fallback for ruflo's vector+BM25+RRF+rerank."""
        q = query.lower()
        return [v for v in self._load(namespace).values() if q in json.dumps(v).lower()]


_PRECEDENT_KEY = "__reasoningbank__"


def record_precedent(store: MemoryStore, namespace: str, trajectory: str, verdict: str,
                     confidence: float = 0.5) -> None:
    """Write a trajectory→verdict entry (ReasoningBank). Repeated similar successes raise count."""
    bank = store.read(namespace, _PRECEDENT_KEY) or []
    bank.append({
        "trajectory": trajectory,
        "verdict": verdict,
        "confidence": confidence,
        "success_count": 1 if verdict == "success" else 0,
        "ts": time.time(),
    })
    store.write(namespace, _PRECEDENT_KEY, bank)


def recall_precedent(store: MemoryStore, namespace: str, query: str) -> list:
    """Recall precedent by similarity (substring fallback), best-confidence first."""
    bank = store.read(namespace, _PRECEDENT_KEY) or []
    q = query.lower()
    hits = [e for e in bank if any(w in e["trajectory"].lower() for w in q.split())]
    return sorted(hits, key=lambda e: e["confidence"], reverse=True)


def consolidate(store: MemoryStore, namespace: str, keep: int = 20) -> None:
    """Distill + prune between phases: keep the top-N by confidence (then recency)."""
    bank = store.read(namespace, _PRECEDENT_KEY) or []
    bank.sort(key=lambda e: (e["confidence"], e["ts"]), reverse=True)
    store.write(namespace, _PRECEDENT_KEY, bank[:keep])
