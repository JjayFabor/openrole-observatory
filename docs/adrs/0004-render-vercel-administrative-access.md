# ADR 0004: Render/Vercel deployment and administrative access

Status: accepted for the requested deployment preparation increment.

## Context

The user selected Render for FastAPI and Vercel for Next.js. The Ubuntu/Nginx
guide was an example, not the chosen hosting platform. Vercel cannot ordinarily
reach Render's private network. A public API web service therefore needs its
own administrative access check. Project-wide Vercel Deployment Protection is
not a path-specific dashboard policy and can also restrict the public product.

Earlier phase reports describe the access-control requirement at their delivery
time. This increment implements that boundary without introducing user accounts,
a database authentication model, sessions or a new identity provider.

## Decision

- Render runs the API and a separate cron process using the same backend modules,
  production PostgreSQL database and private R2 bucket.
- Vercel reaches the API's public HTTPS origin through server-only requests.
- `/dashboard/*` uses HTTP Basic authentication with one operator credential
  pair supplied through server environment variables. Passwords need at least
  32 characters. Production without usable credentials fails closed.
- The Next proxy challenges dashboard requests and any request with a Next
  Server Action header; the only current action is administrative. The dashboard
  layout, every
  administrative API read, and the manual sync Server Action also authorize
  inside their server execution path, including actions posted to another route.
- Each operational FastAPI router has a bearer-token dependency. The separate
  service token is required in production, masked in Settings, and never sent
  to public job or health endpoints. Production OpenAPI/docs routes are disabled.
- Development/test without configured credentials preserve existing local access.
  Supplying credentials opts into protection in those environments too.
- Existing pipeline locks, transaction boundaries, raw lineage, idempotency and
  conservative lifecycle behavior remain unchanged. Cron calls the existing CLI.

## Consequences

The operator uses a browser password prompt over HTTPS. There is no account
registration, password reset, MFA, role management, audit identity or logout UI.
Close the authenticated browser session to clear cached Basic credentials.
Rotate the dashboard password and API token independently; update both services
when rotating the API token. Do not log authorization headers or environment dumps.

The guards are a narrow single-operator deployment boundary. They do not add
rate limiting or prove actual hosted configuration. Before launch, verify direct
Render URL access, Vercel dashboard/action access, HTTPS, production DB/R2,
backups and restore. If multi-operator access is needed, replace this boundary
with a deliberate identity-provider design in a separate task.

## References

- [Render private networking](https://render.com/docs/private-network)
- [Vercel Deployment Protection](https://vercel.com/docs/deployment-protection)
- [Next.js authorization](https://nextjs.org/docs/app/guides/authentication)
- [Server Function authorization](https://nextjs.org/docs/app/getting-started/mutating-data)
