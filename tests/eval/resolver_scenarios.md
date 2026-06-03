# Resolver eval — does `software-factory` fire on the right prompts?

Dispatch each prompt to a subagent that has the resolver description available and ask
whether the `software-factory` skill should engage. Score against Expected.

| # | Prompt | Expected | Why |
|---|--------|----------|-----|
| R1 | "Build and deploy a guestbook app, budget $100." | FIRE | build + deliver live |
| R2 | "Ship me a working URL shortener I can use." | FIRE | ship + running |
| R3 | "Make a demo todo app I can actually click through." | FIRE | usable deployed app |
| R4 | "Stand up a prototype landing page that collects emails." | FIRE | provision + deploy |
| R5 | "Add pagination to the /users endpoint in this repo." | NO | edit in existing repo |
| R6 | "What's the best stack for a guestbook?" | NO | advice, no execution |
| R7 | "Write a function to validate email addresses." | NO | single unit, no deploy |
| R8 | "Review my PR for security issues." | NO | review, not build |
| R9 | "Research the top 5 guestbook competitors." | NO | research, no app |
| R10 | "Refactor this module to be async." | NO | code edit, no deploy |

**Pass requires:** ≥ 9/10 match Expected, and zero false-FIRE on R5–R10 (a false fire hijacks
ordinary coding work, which is the worst failure mode).
