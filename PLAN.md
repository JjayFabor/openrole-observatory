# PLAN: Stop idle cold starts from breaking the public jobs page

## Goal

The hosted `/jobs` page showed "We couldn't load jobs right now" after the API had been idle.
Render's free plan sleeps a service after ~15 idle minutes, and the frontend gives up on a read
after 4 seconds. Keep the API awake and give slow reads more time.

## Steps

1. Raise the frontend's default read timeout from 4s to 15s (`frontend/lib/api/client.ts`).
   The mutation (sync now) timeout stays at 5 minutes.
2. Add a test that a read is not aborted before 15s and is aborted at 15s
   (`frontend/tests/api-client.test.ts`).
3. Add a scheduled GitHub Actions workflow that GETs the API's `/health` every 10 minutes
   (`.github/workflows/keep-api-warm.yml`). The API origin comes from the repository variable
   `OPENROLE_API_BASE_URL`.
4. Document the workflow and update the outdated "no domain selected" notes now that
   `https://openrole-observatory.jjayfabor.com` exists (`docs/deployment-render-vercel.md`,
   `docs/production-configuration.md`).
5. Run the frontend tests, typecheck and lint.

## Decisions

- **Ping `/health`, not `/ready`.** `/ready` runs `SELECT 1`, which would keep the Neon compute
  awake around the clock and use up free compute hours. `/health` keeps Render awake only; Neon
  wakes in about a second, well inside the new timeout.
  Rejected: pinging `/ready`.
- **GitHub Actions for the schedule.** The repo is public, so Actions minutes are free.
  Rejected: an external uptime monitor (setup lives outside the repo), and a Render cron job
  (billed).
- **15s timeout.** It covers Neon waking and slow responses. It does not cover a full Render
  free-plan cold start (often 30–60s); the keep-warm ping is the main fix for that. A much
  longer timeout would leave visitors on a loading page.
- **Every 10 minutes.** Render sleeps after ~15 idle minutes. GitHub can delay scheduled runs,
  so an occasional cold start is still possible.
- Render free gives 750 instance hours/month; one service awake all month is ~730 hours.

## Not in this task

- Setting `OPENROLE_SITE_URL` in Vercel (a dashboard setting the developer does by hand).
- Changing the Render plan.

## Status

- Done: diagnosis (cold start + 4s timeout; missing `OPENROLE_SITE_URL` causes noindex robots
  and an empty sitemap).
- Done: steps 1–5 (2026-11-06). Frontend 238/238 tests, typecheck and lint pass. The new test
  fails with the old 4s value. The workflow's ping script was run against a local API (HTTP 200)
  and with the variable missing (clear error, exit 1). Not yet run on GitHub or against Render.
- Remaining: developer sets the `OPENROLE_API_BASE_URL` repository variable, pushes, and runs
  the workflow once by hand to confirm it.
