import assert from "node:assert/strict";
import Module, { createRequire } from "node:module";
import { renderToStaticMarkup } from "react-dom/server";
import PublicLayout from "../app/(public)/layout";
import JobsLoading from "../app/(public)/jobs/loading";
import ListingLoading from "../app/(public)/(job-detail)/jobs/[jobId]/loading";
import ListingNotFound from "../app/(public)/(job-detail)/jobs/not-found";
import JobsError from "../app/(public)/jobs/error";
import { PublicJobsPagination } from "../components/public/jobs/public-jobs-pagination";
import {
  MAX_PUBLIC_JOBS_PAGE,
  type PublicJobsSearchParams,
} from "../lib/public-jobs/query-state";
import { publicJob, publicJobDetail } from "./public-jobs-fixtures";

async function render() {
  // Node renders components directly; production keeps the server-only bundler boundary.
  const require = createRequire(import.meta.url);
  const serverOnly = require.resolve("server-only");
  const sentinel = new Module(serverOnly);
  sentinel.exports = {};
  sentinel.loaded = true;
  require.cache[serverOnly] = sentinel;
  process.env.OPENROLE_API_BASE_URL = "http://backend.test";

  const { default: JobsPage } = await import("../app/(public)/jobs/page");
  const { default: DetailPage } =
    await import("../app/(public)/(job-detail)/jobs/[jobId]/page");
  const markup = (content: React.ReactNode) =>
    renderToStaticMarkup(<PublicLayout>{content}</PublicLayout>);

  let requests = 0;
  const unexpectedRequests: string[] = [];
  function mockPublicResponse(body: unknown, status = 200) {
    requests = 0;
    globalThis.fetch = async (input) => {
      const url = new URL(String(input));
      const changes = /^\/api\/v1\/public\/jobs\/([0-9a-f-]+)\/changes$/i.exec(
        url.pathname,
      );
      if (changes) {
        assert.equal(url.searchParams.get("limit"), "10");
        return Response.json({ job_id: changes[1], items: [], limit: 10 });
      }
      if (!/^\/api\/v1\/public\/jobs(?:\/[0-9a-f-]+)?$/i.test(url.pathname))
        unexpectedRequests.push(url.pathname);
      assert.match(url.pathname, /^\/api\/v1\/public\/jobs(?:\/[0-9a-f-]+)?$/i);
      requests += 1;
      return Response.json(body, { status });
    };
  }
  async function list(
    params: PublicJobsSearchParams,
    items: unknown[],
    total: number,
    offset = 0,
  ) {
    mockPublicResponse({ items, total, limit: 25, offset });
    return markup(await JobsPage({ searchParams: Promise.resolve(params) }));
  }
  async function routeOutcome(params: PublicJobsSearchParams, total: number) {
    mockPublicResponse({
      items: [],
      total,
      limit: 25,
      offset: (Number(params.page ?? 1) - 1) * 25,
    });
    try {
      await JobsPage({ searchParams: Promise.resolve(params) });
      throw new Error("Expected redirect");
    } catch (error) {
      if (
        error instanceof Error &&
        "digest" in error &&
        String(error.digest).startsWith("NEXT_REDIRECT")
      ) {
        return { digest: String(error.digest), requests };
      }
      throw error;
    }
  }

  const adversarialJob = {
    ...publicJob({
      title: "<img src=x onerror=attack()>Backend Engineer",
      company: { name: "<script>companyAttack()</script>", domain: null },
      location_text: "L".repeat(400),
    }),
    description: "<script>privateDescription()</script>",
    pipeline_run_id: "private-run-id",
    configuration: { secret: "private-token" },
  };
  const unknownJob = publicJob({
    id: "44444444-4444-4444-8444-444444444444",
    workplace_type: "unknown_workplace",
    employment_type: "unknown_employment",
    location_text: null,
    salary_currency: null,
  });
  const populated = await list(
    { q: "backend", workplace: "remote", employment: "full_time" },
    [adversarialJob, unknownJob],
    51,
  );
  const middle = await list(
    { q: "backend", workplace: "remote", page: "2" },
    [publicJob()],
    51,
    25,
  );
  const last = await list({ page: "3" }, [publicJob()], 51, 50);
  const empty = await list({}, [], 0);
  const filtered = await list({ q: "no-match" }, [], 0);
  const changingPage = await list({ q: "backend", page: "2" }, [], 40, 25);
  const clamp = await routeOutcome({ q: "backend", page: "9" }, 40);
  const zeroClamp = await routeOutcome({ q: "missing", page: "2" }, 0);
  const normalization = await routeOutcome(
    {
      q: " backend ",
      workplace: "remote",
      employment: "",
      page: "1",
      internal: "private-token",
    },
    0,
  );

  mockPublicResponse(
    {
      error: {
        code: "PRIVATE_DATABASE_FAILURE",
        message: "postgres private-token",
      },
    },
    500,
  );
  const failure = markup(
    await JobsPage({
      searchParams: Promise.resolve({ q: "backend", workplace: "remote" }),
    }),
  );
  mockPublicResponse(
    publicJobDetail({
      title: "<script>titleAttack()</script>",
      description: "<script>privateDescription()</script>",
    }),
  );
  const detail = markup(
    await DetailPage({ params: Promise.resolve({ jobId: publicJob().id }) }),
  );
  mockPublicResponse(publicJobDetail({ lifecycle_status: "not_observed" }));
  const historicalDetail = markup(
    await DetailPage({ params: Promise.resolve({ jobId: publicJob().id }) }),
  );
  mockPublicResponse(
    { error: { code: "PRIVATE_ERROR", message: "private-token" } },
    500,
  );
  const detailFailure = markup(
    await DetailPage({ params: Promise.resolve({ jobId: publicJob().id }) }),
  );

  assert.deepEqual(unexpectedRequests, []);
  process.stdout.write(
    JSON.stringify({
      populated,
      middle,
      last,
      empty,
      filtered,
      changingPage,
      clamp,
      zeroClamp,
      normalization,
      failure,
      detail,
      historicalDetail,
      detailFailure,
      loading: markup(<JobsLoading />),
      detailLoading: markup(<ListingLoading />),
      missing: markup(<ListingNotFound />),
      boundary: markup(
        <JobsError
          error={new Error("private-token stack trace")}
          reset={() => {}}
        />,
      ),
      maximum: markup(
        <PublicJobsPagination
          query={{ page: MAX_PUBLIC_JOBS_PAGE }}
          total={Number.MAX_SAFE_INTEGER}
        />,
      ),
    }),
  );
}

void render();
