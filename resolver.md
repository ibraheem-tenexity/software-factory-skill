# Resolver — when `software-factory` auto-invokes

The resolver decides whether a user prompt should hand control to the factory. It fires on
intent to **build and ship a working app from a description**, autonomously.

## Fire when the prompt asks to build AND deliver a running app

Signals (any of intent + delivery):
- "build and deploy …", "ship me an app that …", "make a working demo of …",
  "stand up a prototype that …", "get a live app for …"
- A description of an app's behavior plus an expectation that it ends up **running /
  deployed / usable**, not just scaffolded or explained.
- Often paired with a budget ("under $100", "cheap demo") or a deadline.

## Do NOT fire when

- The user wants to **write or explain code** in an existing repo ("add a route", "fix this
  bug", "review this PR") — that's ordinary coding, not a factory run.
- The user wants **advice, a design, or a plan** without execution ("how would I build…",
  "what stack for…").
- The task is a single function/file with no provisioning or deploy ("write a regex",
  "refactor this module").
- No deliverable app is implied (research, data analysis, ops, infra-only changes).

## Litmus test

> Would satisfying this prompt require provisioning a repo, writing code across files, AND
> deploying it to a live URL that a person could use? If yes → fire. If it stops at code or
> advice → do not fire.

## Examples

| Prompt | Fire? | Why |
|--------|-------|-----|
| "Build and deploy a guestbook app, budget $100." | ✅ | build + deliver live |
| "Ship me a working URL shortener." | ✅ | ship + running |
| "Make a demo todo app I can actually click through." | ✅ | usable deployed app |
| "Add pagination to the users endpoint." | ❌ | edit in existing repo |
| "What's the best stack for a guestbook?" | ❌ | advice, no execution |
| "Write a function to validate emails." | ❌ | single unit, no deploy |
| "Review my PR for security issues." | ❌ | review, not build |
