create table if not exists interviews (
  id uuid primary key,
  owner_hash text not null,
  context jsonb not null,
  state jsonb not null,
  status text not null check (status in ('ready', 'active', 'ended', 'completed')),
  call_id uuid unique,
  evaluation jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists interview_turns (
  interview_id uuid not null references interviews(id) on delete cascade,
  sequence integer not null,
  role text not null check (role in ('assistant', 'user')),
  content text not null,
  topic integer not null check (topic between 0 and 6),
  assessment jsonb,
  request_key text unique,
  created_at timestamptz not null default now(),
  primary key (interview_id, sequence)
);

alter table interviews enable row level security;
alter table interview_turns enable row level security;
