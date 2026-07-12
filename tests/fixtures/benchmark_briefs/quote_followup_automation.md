# Product Requirements Document — Quote Follow-Up Automation

**Fictional reference brief for the SOF-92 benchmark harness.** This is an invented scenario
(company, people, and figures are made up) modeled on a common industrial-distributor pattern —
not a real client engagement. It exists purely so an LLM customer-simulator has enough concrete,
consistent detail to answer the onboarding concierge's interview questions realistically.

## Company

Meridian Industrial Supply is a ~60-location industrial distributor (fluid power, fasteners,
belts and hose, safety equipment) with about 800 employees, grown through acquisition and run on
a "coordinated autonomy" model — branches own their P&L, the parent coordinates shared systems.
Meridian runs Epicor Prophet 21 (P21) as its ERP and is completing a data-warehouse project that
will make cross-branch reporting straightforward. Primary sponsor: Dana Whitfield, VP of Sales
Operations.

## The problem

In a representative month, Meridian quotes roughly $40M and books roughly $28M, and only part of
that booked revenue can be traced back to a specific quote — much of it is repeat/walk-in
business. Reps quote in P21, export a PDF, and email it to the customer; quotes and the orders
they become aren't reliably linked in the ERP. Follow-up is a low-priority chore reps deprioritize
against live customer calls, so most quotes never get a second touch. Nobody at Meridian can
currently see, by branch or rep, how much of that quote-to-booking gap is recoverable.

## What's wanted

1. **Analysis** — reconstruct win/loss from P21 + the data warehouse, quantify the real
   opportunity by branch, rep, and customer tier.
2. **Engine** — qualify which open quotes are actually worth chasing, and pre-generate a
   follow-up draft so a rep can send with one click instead of writing from scratch.
3. **Management** — let managers configure the qualification rules, review/approve follow-ups,
   and track results.

## Rollout

Start with one small, willing pilot group of reps at a single branch (branch TBD, Dana's call) —
prove a measurable lift in booked revenue from the follow-ups before rolling out to the full
~60-branch network. A "concrete win" means measurable incremental booked revenue traceable to a
follow-up, scaling to a low-single-digit percentage of the quote-to-booking gap if it holds
network-wide.

## Systems

P21 is the source of truth for quotes, orders, bookings, and rep/branch/customer IDs, reachable
through the nearly-complete data warehouse. No customer portal exists; customers receive quotes
by email only. The follow-up CRM is used unevenly branch-to-branch and isn't integrated with
Outlook.

## Qualification rule (v1)

A quote makes the daily follow-up list if: it isn't already won or a dead alternate; the customer
is in good standing (not on credit hold); and it's large enough, or from a high-tier (A/B)
customer, to justify a rep's time chasing it.

## First-rollout users

Rep-facing: a short, ranked daily follow-up queue, one-click send. Manager-facing: a dashboard
showing the quote-to-booking gap and follow-up activity across branches, once the pilot proves
out.

## Notes for the concierge interview

Reps do not currently use single sign-on for this workflow; the simplest v1 auth is per-rep
Microsoft SSO if the platform supports it, otherwise a simple login is acceptable for the pilot.
Real customer emails should be sent as generated-but-reviewed drafts during the pilot, not fully
automated sends, until the qualification rule is proven.
