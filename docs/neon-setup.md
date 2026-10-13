# Neon project setup — 13 October 2026

The user selected the existing Neon project `sweet-boat-68377250`, named
`openrole-observatory`, and its `production` branch. Project metadata reports
`aws-ap-southeast-1` (Singapore), PostgreSQL 18. Select a nearby Render region
when provisioning the API and cron. The application's Python/FastAPI backend,
Vercel frontend, private R2 storage and Alembic migrations remain the architecture.

## Installed and verified

- Global Neon CLI: `8.4.1`; the existing authenticated profile was reused.
- The requested Neon skills were installed in the ignored agent directories;
  `skills-lock.json` records their public source and hashes.
- Neon MCP setup succeeded, and the Codex user configuration contains the server.
- `.neon` pins this directory to the selected project and branch. It is ignored.
- Root `package.json` and `package-lock.json` supply `@neon/config` and `@neon/env`
  for CLI configuration only. The root package is private. Backend `uv` and
  frontend `pnpm` dependency files are unchanged.
- `neon.ts` is the user's exact empty `defineConfig({})` policy. Both the dry run
  and deployment succeeded and reported **no changes**, with Postgres utilized.

## Reproduce the project link

After authenticating the Neon CLI on your own machine, run from the repository root:

```bash
npm ci
neon link --project-id sweet-boat-68377250 --branch production -y --no-env-pull --no-config
neon config plan
neon deploy --no-env-pull
```

The empty policy requests no new Neon Functions, Auth, Data API, Object Storage,
AI Gateway or compute overrides. `neon deploy` applies Neon branch configuration;
it does not deploy FastAPI to Render, Next.js to Vercel, or run Alembic.

The explicit `--no-env-pull` matters: CLI linking and applying otherwise write
Neon database variables into local dotenv files. The backend reads the root
`.env`, which currently targets the existing development PostgreSQL database.
The local file was preserved and no production connection string was printed.
The ignored `.neon` context does not itself change the backend's database target.

## Still required for the application deployment

Obtain the production branch's direct connection string privately and adapt it
to the existing SQLAlchemy/asyncpg driver in Render's environment. A direct
connection is required for OpenRole's session-level advisory locks. Verify
connectivity and apply the existing Alembic chain as part of the infrastructure
verification/deployment task; this setup did not create application tables.

Provision the separate private R2 bucket and credentials, configure both Render
services, and complete hosted access, readiness, synchronization and backup/restore
checks. See the [Render/Vercel guide](deployment-render-vercel.md).

## Checks performed

`neon config plan`, `neon deploy --no-env-pull` and `npm ls --depth=0` succeeded.
The two environment-template tests passed, including the new `.neon` exclusion.
Git ignore checks passed. File hashes confirm that `.env`, `AGENTS.md`, and the
backend/frontend dependency manifests and lockfiles remained unchanged.

References: [Neon infrastructure configuration](https://neon.com/blog/introducing-neon-ts),
[Neon setup skill source](https://github.com/neondatabase/agent-skills/blob/main/skills/neon/SKILL.md),
[PostgreSQL skill source](https://github.com/neondatabase/agent-skills/blob/main/skills/neon-postgres/SKILL.md).
