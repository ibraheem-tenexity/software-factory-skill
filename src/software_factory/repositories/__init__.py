"""Data-access repositories: pure, parameterized CRUD built with SQLAlchemy Core against the existing
`models.py` Table objects. One repository owns one table's queries (same-table access stays together,
never split across modules). Repositories emit SQL via `_compile.to_sql` and run it through the
existing `dbshim` connection pool via the lanes in `_exec` — the tuned pool/retry/reaper and the
Supabase-pooler settings are unchanged. See docs/ARCHITECTURE.md §3."""
