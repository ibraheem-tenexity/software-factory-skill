// displayContext.ts — the shared "what the customer is looking at right now" store (SOF-245).
//
// The Factory Outputs peer writes the currently-selected artifact + its producing stage here; the
// Concierge reads it and passes it as EPHEMERAL display context on the next chat turn (the backend
// injects it into that one turn only — it is never persisted and never alters memory retrieval).
// A tiny module-level store (not a React context) so the peer and the Concierge stay decoupled
// from the shell that mounts them — it survives the SOF-239 shell restructure untouched.
import { useSyncExternalStore } from "react";

export type DisplayContext = {
  projectId: string;
  artifactId?: number;
  title: string;
  stageLabel: string;   // "Research" | "Design" | "Build & Ship" | "Other factory outputs"
  kindLabel: string;
  // A single human-readable sentence sent to the concierge as this turn's display context.
  summary: string;
};

let current: DisplayContext | null = null;
const listeners = new Set<() => void>();

export function setDisplayContext(next: DisplayContext | null): void {
  current = next;
  listeners.forEach((l) => l());
}

export function getDisplayContext(): DisplayContext | null {
  return current;
}

export function useDisplayContext(): DisplayContext | null {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    getDisplayContext,
    getDisplayContext,
  );
}
