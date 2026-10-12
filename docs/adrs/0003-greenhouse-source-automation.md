# ADR 0003: Greenhouse discovery and external source scheduling

Status: Accepted for the user-requested automation increment (2026-10-12).

## Context

The developer explicitly requested automatic Greenhouse board discovery and
six-hour synchronization after Phase 4. Earlier manual-only delivery records
remain historical. Architecture section 18 already allows a simple external
scheduler while requiring ingestion behavior to stay inside the application.

The public Job Board API operates on known board tokens; it is not a global
company enumeration endpoint. Harvest's organization-scoped board list requires
credentials and is not suitable for discovering unrelated employers.

## Decision

Use the CC0 `moonie0201/ats-directory` JSONL catalogue as candidate evidence.
Process only live, supported Greenhouse entries; validate names through the
official Greenhouse board-metadata endpoint before registration. Retain catalogue
and native metadata responses through ObjectStorage before creating companies/
sources, and record their immutable object keys in private source configuration.
Directory job data or company labels are never treated as canonical job facts.

Register at most 25 new boards per normal cycle to grow coverage gradually.
Existing sources, including manually disabled ones, are not renamed/reactivated.
All active Greenhouse sources are then synchronized using SourceSyncService.
An external systemd timer triggers this CLI at 00:00/06:00/12:00/18:00 Asia/Manila.
Scheduling stays outside FastAPI. A reserved PostgreSQL advisory-lock scope
prevents overlapping automation cycles; existing per-source locks still protect
manual/scheduled sync overlap. Individual source failures do not stop later
sources and never become negative membership evidence.

There is no schema migration, queue, worker framework, provider expansion or
unbounded web crawler. Coverage is the growing verified candidate catalogue,
not a claim to know every Greenhouse employer. Network failures, invalid
candidates and deferred admission remain visible in the cycle report.

## Consequences

The installed host/user timer requires a running machine, available PostgreSQL,
network access and persistent raw storage. Six hours is the trigger interval,
not a monitoring SLA; an active long-running oneshot is not launched again.
Missing catalogue entries do not disable sources or remove jobs. Additional
sources increase database/raw-storage usage. The catalogue is a replaceable,
untrusted discovery input; the official ATS remains the source of listing facts.

References: https://docs.greenhouse.io/job-board.html;
https://harvestdocs.greenhouse.io/reference/get_v3-job-boards;
https://github.com/moonie0201/ats-directory (CC0);
docs/architecture.md#18-scheduling.
