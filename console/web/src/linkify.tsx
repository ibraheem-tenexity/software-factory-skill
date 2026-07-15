// linkify.tsx — SOF-168: URLs in free chat/feed text render as clickable links. Splits on a
// conservative http(s) regex and maps to React nodes (never dangerouslySetInnerHTML), so message
// content can't inject HTML. Link style matches markdown.tsx's inline links.
import React from "react";
import { T } from "./theme";

const URL_RE = /(https?:\/\/[^\s<>"')]+)/g;

export function linkify(text: string): React.ReactNode {
  const parts = text.split(URL_RE);
  if (parts.length === 1) return text;
  return parts.map((p, i) => (i % 2 === 1
    ? <a key={i} href={p} target="_blank" rel="noopener noreferrer" style={{ color: T.brandDeep, textDecoration: "underline", overflowWrap: "anywhere" }}>{p}</a>
    : p));
}
