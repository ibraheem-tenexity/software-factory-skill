# PRD — Meridian Quote Follow-Up Assistant (v1)

> Fictional fixture (NDA-clean) for the SOF-102 eval judge. "Meridian Industrial Supply" is an
> invented company; nothing here derives from any real customer. Pairs with
> `quote_followup_automation.md` (the ground-truth brief the customer-sim answers from).

## Problem & research

Meridian's inside-sales reps send quotes and lose ~30% of winnable deals by never following up.
Research: reps track quotes in spreadsheets; no reminder exists; follow-up quality is inconsistent.
Sources: https://example.com/meridian-sales-notes, https://example.com/quote-conversion-study,
https://example.com/followup-cadence-benchmarks

## Screen catalog

| ID | Screen | V1? |
|----|--------|-----|
| QUOTE_LIST | Needs-follow-up list | Yes |
| QUOTE_DETAIL | Quote detail + drafted follow-up | Yes |
| FOLLOWUP_COMPOSER | Follow-up composer | Yes |
| ANALYTICS | Conversion analytics | Future |

## Acceptance criteria

Given a sales rep with open quotes, when they open the dashboard, then every quote past its
follow-up threshold appears in the "Needs follow-up" list sorted by days-overdue.

Given a quote in the needs-follow-up list, when the rep clicks it, then the quote detail shows the
line items, the customer contact, and a drafted follow-up message.

Given a drafted follow-up on the quote detail, when the rep clicks Send, then the message is
recorded against the quote and the quote leaves the needs-follow-up list.

## Ticket seeds

- QUOTE_LIST: threshold query + days-overdue sort
- QUOTE_DETAIL: line-items + contact + draft render
- FOLLOWUP_COMPOSER: send action + quote-state transition
