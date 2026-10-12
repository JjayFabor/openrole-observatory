# ADR 0002: Internal dashboard reads through FastAPI

Date: 2026-10-09 (Asia/Manila)

Status: Accepted for the developer-requested Phase 3 Task 34 foundation.

## Context

Phases 1 and 2 provide a Greenhouse ingestion backend and administrative read
APIs. The developer replaced the proposed Multi-ATS Phase 3 roadmap with an
internal dashboard. Task 34 needs a small, understandable frontend foundation
without duplicating the backend or implementing subsequent data pages.

## Decision

Place a standalone Next.js App Router application in `frontend/`, beside
`backend/`. Use pnpm, TypeScript, Tailwind, and a small shadcn/ui-compatible base.
Keep pages and read-only fetching in server components. Use client components
only where browser state or interaction requires them.

Centralize native fetch calls in a server-only typed client configured with
`OPENROLE_API_BASE_URL`. Requests have a bounded timeout; status checks use
`cache: no-store`. Validate the consumed health/readiness payloads at runtime.
Known database unavailability differs from an unavailable readiness check.
Each check can fail independently without taking down the dashboard shell.

FastAPI owns application rules and database access. Next.js has no database
credentials, direct PostgreSQL/object-storage calls, or duplicate API routes.

## Consequences

- The Python backend, transaction boundaries, and schema remain unchanged.
- Server-side calls avoid introducing browser CORS configuration.
- The backend URL stays on the Next.js server; it is not a `NEXT_PUBLIC_` value.
- The overview is rendered on request so status is not baked into a build.
- The shell is useful during an outage, though checks require a page reload;
  polling and broader overview data are future tasks.
- No frontend authentication is added. Existing administrative surfaces retain
  their external access-control requirement.
- Greenhouse remains the only implemented provider.

## Verification

Focused API tests cover URL construction, transport/HTTP/JSON failures, payload
validation, health/readiness mapping, independent failures, and uncached calls.
Lint, TypeScript, production build, and desktop/mobile browser checks verify the
foundation. The outage check stops only the locally started FastAPI process.
