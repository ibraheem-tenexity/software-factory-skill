-- Agent telemetry for the external dashboard.
-- Append-only event log; the web view reduces events into live state client-side.
-- Run this in the Supabase SQL editor (or via `supabase db push`) once per project.

create table if not exists agent_events (
    id          bigint generated always as identity primary key,
    event       text not null,                 -- 'spawn' | 'record'
    agent_id    text not null,
    run_id      text,
    ticket_id   int,
    role        text,
    model       text,
    outcome     text,                           -- real_diff | no_op | blocked | failed
    cost_usd    numeric default 0,
    pr          int,
    diff_lines  int default 0,
    at          double precision,               -- orchestrator clock
    inserted_at timestamptz default now()
);

create index if not exists agent_events_run_idx on agent_events (run_id, inserted_at);

-- Realtime so the dashboard updates the instant an agent spawns or finishes.
alter publication supabase_realtime add table agent_events;

-- RLS: the factory writes with the service key (bypasses RLS); the dashboard reads with the
-- public anon key. Allow anon SELECT only.
alter table agent_events enable row level security;
create policy "anon can read agent events"
    on agent_events for select
    to anon
    using (true);
