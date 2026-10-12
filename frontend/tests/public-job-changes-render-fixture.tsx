import assert from "node:assert/strict";
import Module, { createRequire } from "node:module";
import { renderToStaticMarkup } from "react-dom/server";
import PublicLayout from "../app/(public)/layout";
import { publicJobDetail } from "./public-jobs-fixtures";

async function render() {
  const require = createRequire(import.meta.url);
  const serverOnly = require.resolve("server-only");
  const sentinel = new Module(serverOnly);
  sentinel.exports = {};
  sentinel.loaded = true;
  require.cache[serverOnly] = sentinel;
  process.env.OPENROLE_API_BASE_URL = "http://backend.test";
  const { PublicJobChangesSection, PublicJobChangesLoading } =
    await import("../components/public/jobs/public-job-changes");
  const { PublicJobDetail } =
    await import("../components/public/jobs/public-job-detail");
  const { default: JobPage, generateMetadata } =
    await import("../app/(public)/(job-detail)/jobs/[jobId]/page");
  const job = publicJobDetail();
  const endpoint = `/api/v1/public/jobs/${job.id}`;
  const markup = (content: React.ReactNode) =>
    renderToStaticMarkup(<PublicLayout>{content}</PublicLayout>);
  let requests: string[] = [];
  function mockResponse(body: unknown, status = 200, primaryStatus = 200) {
    requests = [];
    globalThis.fetch = async (input) => {
      const url = new URL(String(input));
      requests.push(url.pathname);
      if (url.pathname === `${endpoint}/changes`) {
        assert.equal(url.searchParams.get("limit"), "10");
        return Response.json(body, { status });
      }
      assert.equal(url.pathname, endpoint);
      return Response.json(
        primaryStatus === 200
          ? job
          : {
              error: {
                code: "PRIVATE_PRIMARY_ERROR",
                message: "private-token",
              },
            },
        { status: primaryStatus },
      );
    };
  }
  const groups = [
    {
      observed_at: "2026-10-12T00:00:00Z",
      from_version_id: "private-version",
      changes: [
        {
          field: "title",
          change_type: "modified",
          old_value: "<img src=x onerror=attack()>Engineer",
          new_value: "T".repeat(450),
          pipeline_run_id: "private-run",
        },
        {
          field: "workplace_type",
          change_type: "modified",
          old_value: "remote",
          new_value: "hybrid",
        },
        {
          field: "salary",
          change_type: "added",
          old_value: null,
          new_value: {
            min: "0.00",
            max: "9007199254740993.01",
            currency: "USD",
            period: "year",
            content_hash: "private-hash",
          },
        },
        {
          field: "description",
          change_type: "modified",
          old_value: "<script>private-old()</script>",
          new_value: "<p>private-new</p>",
        },
      ],
    },
    {
      observed_at: "2026-10-12T00:00:00Z",
      changes: [
        {
          field: "salary",
          change_type: "modified",
          old_value: { min: null, max: null, currency: "USD", period: "year" },
          new_value: { min: null, max: null, currency: "EUR", period: "month" },
        },
        { field: "description", change_type: "added" },
      ],
    },
    {
      observed_at: "2026-10-11T00:00:00Z",
      changes: [
        {
          field: "location_text",
          change_type: "removed",
          old_value: "Berlin",
          new_value: null,
        },
        {
          field: "workplace_type",
          change_type: "modified",
          old_value: "future_workplace",
          new_value: "remote",
        },
        { field: "description", change_type: "removed" },
      ],
    },
  ];
  mockResponse({
    job_id: job.id,
    items: groups,
    limit: 10,
    canonical_metadata: "private-metadata",
  });
  const populated = markup(await PublicJobChangesSection({ jobId: job.id }));
  mockResponse({ job_id: job.id, items: [], limit: 10 });
  const empty = markup(await PublicJobChangesSection({ jobId: job.id }));
  mockResponse(
    {
      error: {
        code: "PRIVATE_SECONDARY_ERROR",
        message: "postgres private-token",
      },
    },
    500,
  );
  const failure = markup(
    <>
      <PublicJobDetail job={job} />
      {await PublicJobChangesSection({ jobId: job.id })}
    </>,
  );
  mockResponse({ error: { code: "JOB_NOT_FOUND" } }, 404);
  const missingSecondary = markup(
    await PublicJobChangesSection({ jobId: job.id }),
  );
  mockResponse({
    job_id: job.id,
    items: [
      {
        ...groups[0],
        changes: [
          {
            field: "canonical_metadata",
            change_type: "modified",
            old_value: "private-metadata",
            new_value: "private-metadata",
          },
        ],
      },
    ],
    limit: 10,
  });
  const malformedSecondary = markup(
    await PublicJobChangesSection({ jobId: job.id }),
  );
  mockResponse({ job_id: job.id, items: [], limit: 10 });
  const page = markup(
    await JobPage({ params: Promise.resolve({ jobId: job.id }) }),
  );
  const pageRequests = [...requests];
  mockResponse({ job_id: job.id, items: groups, limit: 10 });
  const metadata = await generateMetadata({
    params: Promise.resolve({ jobId: job.id }),
  });
  const metadataRequests = [...requests];
  mockResponse({ job_id: job.id, items: groups, limit: 10 }, 200, 500);
  const primaryFailure = markup(
    await JobPage({ params: Promise.resolve({ jobId: job.id }) }),
  );
  const primaryFailureRequests = [...requests];

  process.stdout.write(
    JSON.stringify({
      populated,
      empty,
      failure,
      missingSecondary,
      malformedSecondary,
      page,
      pageRequests,
      metadata,
      metadataRequests,
      primaryFailure,
      primaryFailureRequests,
      loading: markup(<PublicJobChangesLoading />),
    }),
  );
}

void render();
