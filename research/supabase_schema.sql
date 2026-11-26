-- Execute in Supabase SQL Editor. Server-only access; do not expose service_role key in browser.
create table if not exists public.xhs_notes (
 note_id text primary key, title text, description text, url text, keyword text,
 author_name text, author_followers bigint, published_at timestamptz,
 likes bigint, collects bigint,
 comments bigint, shares bigint,
  raw jsonb not null default '{}'::jsonb,
 last_seen_at timestamptz not null default now(), created_at timestamptz not null default now()
);
create table if not exists public.xhs_analyses (
 note_id text primary key references public.xhs_notes(note_id) on delete cascade,
 gpt_analysis text, claude_analysis text,
 analysis_scope text not null default 'metadata_only',
 analyzed_at timestamptz not null default now()
);
create table if not exists public.xhs_metric_snapshots (
 id bigint generated always as identity primary key,
 note_id text not null references public.xhs_notes(note_id) on delete cascade,
 observed_at timestamptz not null default now(), likes bigint, collects bigint, comments bigint, shares bigint
);
create index if not exists idx_xhs_notes_keyword on public.xhs_notes(keyword);
alter table public.xhs_notes enable row level security;
alter table public.xhs_analyses enable row level security;
alter table public.xhs_metric_snapshots enable row level security;
-- No anon/authenticated policies: only service_role backend calls can access.
-- Allow unknown metrics for installations of the original MVP.
alter table public.xhs_notes
 alter column likes drop not null,
 alter column likes drop default,
 alter column collects drop not null,
 alter column collects drop default,
 alter column comments drop not null,
 alter column comments drop default,
 alter column shares drop not null,
 alter column shares drop default;
