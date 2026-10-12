# Greenhouse source automation

This requested increment follows Phase 4. It discovers Greenhouse boards and
refreshes active sources without manually copying tokens. It adds no new ATS
provider, database tables, public writes, queue or scheduler framework.

## Run locally

First complete the normal setup: root `.env`, PostgreSQL, `uv sync --locked`,
`uv run alembic upgrade head`, API and frontend. The CLI reads the same root
`.env` as the API. API/frontend processes are needed to browse results; the
automation itself needs only Python, PostgreSQL, network and object storage.

From `backend`, install the current user's systemd timer and begin a cycle:

```bash
uv run python -m app.cli.install_automation_timer --start-now
systemctl --user status openrole-greenhouse-automation.timer
systemctl --user list-timers openrole-greenhouse-automation.timer
journalctl --user -u openrole-greenhouse-automation.service -n 120 --no-pager
```

The timer triggers at **00:00, 06:00, 12:00 and 18:00 Asia/Manila**, independently
of the host's display timezone. `--start-now` starts asynchronously: inspect
the service/journal for completion. Installation preserves unrelated units and
updates only files carrying the OpenRole ownership marker. It uses the absolute
backend virtualenv Python; rerun installation if you move the repository.

The machine must stay on and awake, with PostgreSQL available. User timers
require an active user systemd manager. Check `loginctl show-user "$USER" -p Linger`;
if it is `yes`, the user manager can continue after logout. Otherwise your login
session must remain active, or an administrator can enable lingering for that
user. `Persistent=true` catches a missed calendar activation when the timer starts;
it does not replay every missed six-hour interval. systemd does not start another
copy of an already-running oneshot. Trigger frequency is not a freshness SLA.

Refresh `http://localhost:3000/jobs` after the cycle. Operational runs and
quarantines remain visible under `/dashboard/runs` and `/dashboard/quarantine`.

For one cycle without installing a timer:

```bash
uv run python -m app.cli.automate_greenhouse
# Refresh configured sources without admitting additional boards:
uv run python -m app.cli.automate_greenhouse --max-new-sources 0
```

The default is 25 new sources per cycle and a 0.5-second pause between new board
probes and between source synchronizations. `--max-new-sources` accepts 0–1000;
`--request-delay` accepts 0–60 seconds. Already configured sources are all
considered, including manually registered sources. Admission grows gradually
across cycles; there is no total 25-source coverage limit.

## Data flow and boundaries

1. Acquire a dedicated PostgreSQL advisory lock for the automation cycle.
2. Fetch the CC0 public ATS directory, capped at 2 MB and 20,000 JSONL lines.
   Only HTTPS `raw.githubusercontent.com` URLs ending in `.jsonl` are permitted;
   credentials, query strings, other ports and redirects are rejected.
3. Preserve catalogue bytes through ObjectStorage. Select `provider=greenhouse`,
   `status=ok`, supported default/US region and no site scope. Reject unsafe
   tokens, count malformed rows, deduplicate exact tokens and sort them.
4. For a new candidate, fetch the native Greenhouse board metadata, preserve
   its bytes, and require a usable native company name. Catalogue names/domains
   are not company facts. Metadata parsing is capped at 1 MB.
5. Register Company and SourceConnection together in a short transaction.
   PostgreSQL uniqueness and conflict handling make repeated registration
   idempotent. Existing source/company names, configuration and active state
   are preserved. Missing catalogue entries never disable configured sources.
6. Page through active Greenhouse source IDs in batches of 100 and invoke the
   existing SourceSyncService sequentially. That service retains per-source locks,
   raw job responses, validation, canonical mapping, immutable versions,
   observations, quarantine, and conservative lifecycle reconciliation.
7. Emit a JSON cycle report and release the global lock. Source failures are
   counted and later sources continue. Failed responses do not imply absence.

No database transaction spans an HTTP or object-storage operation. Registration
uses deterministic per-board company slugs because a board's native metadata
does not establish cross-board corporate identity. Case-sensitive tokens remain
distinct; the implementation does not guess whether similarly named boards
are one company. Newly registered sources are active by default.

Discovery evidence uses immutable keys:

```text
bronze/greenhouse/discovery/<cycle UUID>/directory.jsonl
bronze/greenhouse/discovery/<cycle UUID>/boards/<token>.json
```

Private source configuration stores both object keys, SHA-256 hashes, directory
URL and discovery timestamp. These fields remain outside public projections.
The usual RawSnapshot/PipelineRun lineage is still recorded by job ingestion.
No Company/Source row is created when raw evidence cannot be stored.

## Coverage and errors

Greenhouse's public Job Board API reads known board tokens; it does not enumerate
every employer. The directory supplies candidates, not proof of complete global
coverage or current hiring. Unknown boards, regional variants and other ATS
providers are outside this increment. Stale entries may fail verification.
Directory omissions are never job-membership evidence. Existing sources still
sync when catalogue fetching/parsing fails after a usable CLI startup.

The normal cycle report distinguishes created/existing/deferred boards,
malformed/excluded/duplicate rows, completed and partially completed runs,
busy/inactive skips, new/changed/unchanged jobs and failures. Exit 1 means some
discovery/synchronization errors or record errors occurred; it does not mean
every source failed. A competing whole cycle prints `AUTOMATION_ALREADY_RUNNING`
and exits 0. Pipeline records provide detailed per-source outcomes.
Database/startup failures can stop the whole cycle. No automatic reactivation,
retry queue or manual recovery of interrupted running pipeline records is added.

Directory failures: `DIRECTORY_REQUEST_FAILED`, `DIRECTORY_TOO_LARGE`,
`DIRECTORY_TOO_MANY_ROWS`, `DIRECTORY_INVALID_ENCODING`, `DIRECTORY_URL_INVALID`.
Board/storage failures include `BOARD_REQUEST_FAILED`, `BOARD_METADATA_INVALID`,
`BOARD_METADATA_TOO_LARGE`, `DISCOVERY_STORAGE_FAILED` and registration conflicts.
Unexpected individual sync failures are visible as `AUTOMATION_SYNC_FAILED`.

## Deploy the schedule

Production uses the Render Cron Job in `render.yaml`, with the same production
PostgreSQL database and private R2 bucket as the API. Create it after API migrations
and readiness pass. The UTC schedule `0 4,10,16,22 * * *` matches the local
00:00/06:00/12:00/18:00 Asia/Manila calendar. It runs
`uv run --no-sync python -m app.cli.automate_greenhouse` from `backend`.

Render cron cannot access persistent disks. Do not use the local filesystem
storage backend or the systemd installer for this production topology. The local
timer remains available for local development. See the
[Render/Vercel deployment guide](deployment-render-vercel.md) and
[Word guide](OpenRole-Deployment-Guide.docx) for ordered setup and environment values.

Suspend future cron scheduling and wait for an active cycle to finish before
migrations or source/build replacement. Render's manual Trigger Run cancels an
active invocation, so trigger only when idle. Scheduled runs wait for an existing
invocation. Preserve PostgreSQL and Bronze objects independently of releases.
See [Render cron documentation](https://render.com/docs/cronjobs).

To stop future **local** cycles (a running cycle continues):

```bash
systemctl --user disable --now openrole-greenhouse-automation.timer
```

## Verification and review

Normal tests mock HTTP and use PostgreSQL rollback fixtures; they do not contact
live Greenhouse or the directory, and do not install systemd units. Discovery,
registration/raw lineage, repeat ingestion, admission growth, disabled sources,
failure isolation, pagination, whole-cycle locking and timer ownership/calendar
are covered. There is no migration because the existing constraints/configuration
support this task. See [ADR 0003](adrs/0003-greenhouse-source-automation.md).

Primary references: [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html),
[ATS directory and CC0 licence](https://github.com/moonie0201/ats-directory),
[systemd timers](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html).

## Verified local delivery — 12 October 2026

The current user's timer is enabled and waiting at the six-hour Manila calendar.
Lingering is already enabled for this user. The first actual cycle found 382
supported candidates, registered 25 company boards and completed 25 pipeline
runs with 1,264 new listings and no failures/quarantine. Another cycle using
`--max-new-sources 0` completed all 25 runs with 1,264 unchanged listings, no
new/changed jobs and no failures. The remaining 357 candidates are deferred to
later normal cycles. These counts describe delivery verification, not permanent
coverage or future employer availability.

The real public API and `/jobs` report 1,264 results; landing, discovery and
Sources return HTTP 200. The frontend remains on localhost:3000 and API on
localhost:8000. This is a local installation; no production host was deployed.

| Check | Result |
|---|---|
| Full backend `uv run pytest -q` | 813 passed, 2 optional live tests skipped; existing Starlette deprecation warning |
| Focused discovery/client/timer/PostgreSQL automation suite, including added systemd parser test | 50 passed |
| `uv run ruff check app tests` and `uv run mypy` | Passed |
| Frontend `pnpm test` | 220 passed |
| Frontend `pnpm lint`, `pnpm typecheck`, `pnpm build` | Passed; build used disabled site indexing and an unavailable API |
| Installed systemd unit verification/calendar | Valid units; enabled timer; successful initial service exit |
| Updated Word deployment guide | Valid ZIP/XML; opened and exported by LibreOffice as 15 pages; inspected rendered setup/schedule pages |

Initial systemd validation caught quoted `WorkingDirectory` syntax that this
directive does not accept. The installer now writes an unquoted absolute path;
the new parser test covers spaces and percent specifiers without activating a
service. No unresolved automation test or live-source failure remains.

For code review, read `app/sources/greenhouse/discovery.py` for input boundaries,
`app/sources/discovery_registry.py` for transactions/conflicts,
`app/ingestion/source_automation.py` for failure isolation and source paging,
`app/cli/automate_greenhouse.py` for composition/whole-cycle locking, and
`app/cli/install_automation_timer.py` for scheduler ownership and the calendar.
