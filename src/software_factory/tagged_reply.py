"""SOF-154: the Concierge's tag-delimited final-reply format, and the parser that turns it back
into a `ConciergeTurn`.

With `ToolStrategy(ConciergeTurn)` dropped (see `chat_agent.ChatAgent(use_tagged_output=True)`),
the model's final user-facing turn is plain content instead of forced tool-call JSON — prompted
(see `default_prompt._CONTEXT_FRAMING["intake"]`) to wrap it as:

    <say>Got it — what timeline are you working to?</say>
    <option type="single">This quarter</option>
    <option type="single">Next quarter</option>

`TaggedReplyParser` is fed raw model-output deltas (streaming, one chunk at a time) OR the whole
string at once (`parse_tagged_reply`, used by the non-streaming `/converse` route) — both paths
produce the identical `ConciergeTurn` reconstruction, so persistence/API shape never depends on
whether the caller streamed.

Malformed/untagged output degrades to raw passthrough: every character the model produced still
reaches the user as prose (`response`), it just never becomes chips — never a broken bubble.
"""
from __future__ import annotations

import re

from software_factory.constants import CONCIERGE_SAFE_FALLBACK
from software_factory.data_transfer_objects.chat_agent import ConciergeTurn, SuggestedResponse

_SAY_OPEN = "<say>"
_SAY_CLOSE = "</say>"
_OPTION_OPEN_RE = re.compile(r'<option type="(single|multi)">')
_OPTION_CLOSE = "</option>"

# States: waiting to confirm the leading "<say>"; inside <say>...</say> (streaming prose); between
# tags (whitespace/tag furniture only); inside <option ...>...</option> (buffered, not streamed);
# permanently degraded to raw passthrough (malformed/untagged output detected).
_AWAIT_SAY, _IN_SAY, _BETWEEN_TAGS, _IN_OPTION, _RAW = range(5)

_OPTION_TYPE_MAP = {"single": "single select", "multi": "multi select"}


class TaggedReplyParser:
    """Incremental parser — call `feed()` per chunk, `finish()` once at stream end, then
    `reconstruct()` for the `ConciergeTurn`. Each `feed()`/`finish()` call returns a list of
    event dicts: `{"type": "token", "text": ...}` (prose delta) or
    `{"type": "option", "option_type": "single"|"multi", "text": ...}` (one whole chip)."""

    def __init__(self):
        self._state = _AWAIT_SAY
        self._buf = ""
        self._response_parts: list[str] = []
        self._options: list[dict] = []
        self._pending_option_type: str | None = None

    def feed(self, delta: str) -> list[dict]:
        if not delta:
            return []
        self._buf += delta
        events: list[dict] = []
        progress = True
        while progress:
            progress = False
            if self._state == _AWAIT_SAY:
                progress = self._step_await_say(events)
            elif self._state == _IN_SAY:
                progress = self._step_in_say(events)
            elif self._state == _BETWEEN_TAGS:
                progress = self._step_between_tags()
            elif self._state == _IN_OPTION:
                progress = self._step_in_option(events)
            elif self._state == _RAW:
                progress = self._step_raw(events)
        return events

    def _step_await_say(self, events: list[dict]) -> bool:
        # Tolerate arbitrary leading whitespace before the real "<say>" open tag.
        probe = self._buf.lstrip()
        if probe.startswith(_SAY_OPEN):
            self._buf = probe[len(_SAY_OPEN):]
            self._state = _IN_SAY
            return True
        if probe and not _SAY_OPEN.startswith(probe):
            # Real, non-whitespace content that can never become "<say>" — malformed/untagged
            # output. Degrade permanently: everything seen so far (and everything from here on)
            # streams as plain prose, zero chips.
            events.append({"type": "token", "text": self._buf})
            self._response_parts.append(self._buf)
            self._buf = ""
            self._state = _RAW
            return True
        return False  # empty/whitespace-only, or still a valid partial prefix — wait for more

    def _step_in_say(self, events: list[dict]) -> bool:
        idx = self._buf.find(_SAY_CLOSE)
        if idx != -1:
            text = self._buf[:idx]
            if text:
                events.append({"type": "token", "text": text})
                self._response_parts.append(text)
            self._buf = self._buf[idx + len(_SAY_CLOSE):]
            self._state = _BETWEEN_TAGS
            return True
        # Hold back a tail long enough to catch a "</say>" split across chunk boundaries.
        hold = len(_SAY_CLOSE) - 1
        if len(self._buf) > hold:
            emit, self._buf = self._buf[:-hold], self._buf[-hold:]
            events.append({"type": "token", "text": emit})
            self._response_parts.append(emit)
        return False

    def _step_between_tags(self) -> bool:
        # Only whitespace or the next <option ...> tag is expected here — tag furniture, discarded.
        m = _OPTION_OPEN_RE.search(self._buf)
        if m and m.start() == 0:
            self._pending_option_type = m.group(1)
            self._buf = self._buf[m.end():]
            self._state = _IN_OPTION
            return True
        if m:
            self._buf = self._buf[m.start():]  # drop whitespace before the tag, keep the tag
            return True
        if len(self._buf) > 64 and self._buf.strip():
            self._buf = ""  # junk that's never resolving into a tag — drop it, don't show it
        return False

    def _step_in_option(self, events: list[dict]) -> bool:
        idx = self._buf.find(_OPTION_CLOSE)
        if idx == -1:
            return False  # still accumulating this option's text — buffered, never streamed
        text = self._buf[:idx].strip()
        if text:
            events.append({"type": "option", "option_type": self._pending_option_type, "text": text})
            self._options.append({"type": self._pending_option_type, "text": text})
        self._buf = self._buf[idx + len(_OPTION_CLOSE):]
        self._pending_option_type = None
        self._state = _BETWEEN_TAGS
        return True

    def _step_raw(self, events: list[dict]) -> bool:
        if self._buf:
            events.append({"type": "token", "text": self._buf})
            self._response_parts.append(self._buf)
            self._buf = ""
        return False

    def finish(self) -> list[dict]:
        """Call once the model's stream is exhausted. Flushes any still-buffered prose (including
        a `<say>` that never closed — real prose the user already saw stays). Silently drops a
        still-open, unclosed `<option>` — never surface a half-formed chip."""
        events: list[dict] = []
        if self._state in (_AWAIT_SAY, _IN_SAY, _RAW) and self._buf:
            events.append({"type": "token", "text": self._buf})
            self._response_parts.append(self._buf)
        self._buf = ""
        return events

    def reconstruct(self) -> ConciergeTurn:
        response = "".join(self._response_parts).strip()
        suggested = [
            SuggestedResponse(response=o["text"], type=_OPTION_TYPE_MAP[o["type"]])
            for o in self._options
        ]
        return ConciergeTurn(response=response or CONCIERGE_SAFE_FALLBACK, suggested_responses=suggested)


def parse_tagged_reply(text: str) -> ConciergeTurn:
    """One-shot parse of a complete tag-formatted reply (used by the non-streaming `/converse`
    route) — same reconstruction the streaming path produces incrementally."""
    parser = TaggedReplyParser()
    parser.feed(text or "")
    parser.finish()
    return parser.reconstruct()
