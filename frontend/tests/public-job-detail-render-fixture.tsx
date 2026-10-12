import assert from "node:assert/strict";
import Module, { createRequire } from "node:module";
import { encodeXML } from "entities";
import { renderToStaticMarkup } from "react-dom/server";
import PublicLayout from "../app/(public)/layout";
import JobLoading from "../app/(public)/(job-detail)/jobs/[jobId]/loading";
import JobNotFound from "../app/(public)/(job-detail)/jobs/not-found";
import JobError from "../app/(public)/(job-detail)/jobs/[jobId]/error";
import { publicJobDetail } from "./public-jobs-fixtures";
import type { PublicJobDetail as PublicJobData } from "../lib/api/public-jobs-types";

async function render() {
  // Production still enforces the server-only boundary; this fixture uses ordinary ReactDOMServer.
  const require = createRequire(import.meta.url);
  const serverOnly = require.resolve("server-only");
  const sentinel = new Module(serverOnly);
  sentinel.exports = {};
  sentinel.loaded = true;
  require.cache[serverOnly] = sentinel;
  process.env.OPENROLE_API_BASE_URL = "http://backend.test";
  const { default: JobPage, generateMetadata } =
    await import("../app/(public)/(job-detail)/jobs/[jobId]/page");
  const { default: JobLayout } =
    await import("../app/(public)/(job-detail)/jobs/[jobId]/layout");
  const { PublicJobDetail } =
    await import("../components/public/jobs/public-job-detail");
  const { JobDescription } = await import("../components/jobs/job-description");
  const markup = (content: React.ReactNode) =>
    renderToStaticMarkup(<PublicLayout>{content}</PublicLayout>);
  const unexpectedRequests: string[] = [];
  function mockResponse(body: unknown, status = 200) {
    globalThis.fetch = async (input, options) => {
      const url = new URL(String(input));
      const endpoint = `/api/v1/public/jobs/${publicJobDetail().id}`;
      if (url.pathname === `${endpoint}/changes`) {
        assert.equal(url.searchParams.get("limit"), "10");
        return Response.json({
          job_id: publicJobDetail().id,
          items: [],
          limit: 10,
        });
      }
      if (url.pathname !== endpoint) unexpectedRequests.push(url.pathname);
      assert.equal(url.pathname, endpoint);
      assert.equal(options?.cache, "no-store");
      return Response.json(body, { status });
    };
  }
  async function renderPage(jobId: string) {
    const params = Promise.resolve({ jobId });
    const children = await JobPage({ params });
    return markup(await JobLayout({ params, children }));
  }
  async function renderJob(job: PublicJobData) {
    mockResponse({
      ...job,
      pipeline_run_id: "private-run-id",
      content_hash: "private-hash",
      consecutive_absent_runs: 2,
    });
    return renderPage(job.id);
  }
  async function missingOutcome(
    jobId: string,
    target: "metadata" | "page" | "layout",
  ) {
    mockResponse({ error: { code: "JOB_NOT_FOUND" } }, 404);
    try {
      const props = { params: Promise.resolve({ jobId }) };
      if (target === "metadata") await generateMetadata(props);
      else if (target === "layout")
        await JobLayout({
          ...props,
          children: <p>Unavailable listing content</p>,
        });
      else await JobPage(props);
      throw new Error("Expected not-found");
    } catch (error) {
      if (error instanceof Error && "digest" in error)
        return String(error.digest);
      throw error;
    }
  }

  const description =
    '<h1>About this role</h1><h6>Responsibilities</h6><p onclick="attack()" style="position:fixed">Safe <strong>work</strong>.</p><ul><li>Build systems</li></ul><script>privateScript()</script><iframe src="https://attack.test"></iframe><img src=x onerror=attack()><a href="javascript:attack()">Bad link</a><a href="https://example.test/details" target="_self" rel="opener">Read more</a>';
  const observed = await renderJob(
    publicJobDetail({
      title: "Backend <img src=x onerror=attack()> Engineer",
      company: {
        name: "Employer <script>nameAttack()</script>",
        domain: "javascript:domainAttack()",
        careers_url: null,
      },
      location_text: "L".repeat(400),
      description,
    }),
  );
  const sparse = await renderJob(
    publicJobDetail({
      location_text: null,
      workplace_type: "unknown_workplace",
      employment_type: null,
      salary_min: null,
      salary_max: null,
      company: { name: "Employer", domain: null, careers_url: null },
      description: null,
    }),
  );
  const absent = await renderJob(
    publicJobDetail({
      lifecycle_status: "not_observed",
      no_longer_observed_at: "2026-10-11T00:00:00Z",
    }),
  );
  const reappeared = await renderJob(
    publicJobDetail({
      reappeared_at: "2026-10-12T00:00:00Z",
      no_longer_observed_at: "2026-10-11T00:00:00Z",
    }),
  );
  const tentative = await renderJob(
    publicJobDetail({ absence_first_detected_at: "2026-10-11T00:00:00Z" }),
  );
  const partialSalary = await renderJob(
    publicJobDetail({
      salary_min: "0.00",
      salary_max: null,
      salary_currency: null,
      salary_period: null,
    }),
  );
  const plain = await renderJob(
    publicJobDetail({
      description: "First line\nSecond line\nSalary < 100000 & benefits",
    }),
  );
  const encodedDescription = encodeXML(
    '<div class="content-intro"><div>Employer introduction.</div><div>Build safe <strong>systems</strong>.</div></div><h2>Responsibilities</h2><ul><li>Help people</li></ul><script>privateScript()</script><a href="jav&#x61;script:attack()">Bad link</a>',
  );
  const encoded = await renderJob(
    publicJobDetail({ description: encodedDescription }),
  );
  const dashboardEncoded = renderToStaticMarkup(
    <JobDescription description={encodedDescription} />,
  );
  const emptyDescriptions = [
    null,
    "   ",
    "<p>&nbsp;<br></p>",
    "<script>privateScript()</script>",
    "&lt;div&gt;&amp;nbsp;&lt;/div&gt;",
    "&lt;script&gt;privateScript()&lt;/script&gt;",
  ].map((value) =>
    renderToStaticMarkup(
      <JobDescription
        description={value}
        emptyText="No description is available for this listing."
      />,
    ),
  );
  const dashboardEmpty = renderToStaticMarkup(
    <JobDescription description={null} />,
  );
  const dashboardHeadings = renderToStaticMarkup(
    <JobDescription description={description} />,
  );
  const unsafeComponentLinks = [
    "javascript:attack()",
    "https://user:secret@example.test",
    "//example.test",
  ].map((source_url) =>
    markup(<PublicJobDetail job={publicJobDetail({ source_url })} />),
  );
  const httpSource = markup(
    <PublicJobDetail
      job={publicJobDetail({ source_url: "http://example.test/jobs/123" })}
    />,
  );

  mockResponse(publicJobDetail());
  const availableLayout = markup(
    await JobLayout({
      params: Promise.resolve({ jobId: publicJobDetail().id }),
      children: <p>Existing listing content</p>,
    }),
  );
  const metadata = await generateMetadata({
    params: Promise.resolve({ jobId: publicJobDetail().id }),
  });
  const missingMetadata = await missingOutcome(
    publicJobDetail().id,
    "metadata",
  );
  const malformedMetadata = await missingOutcome("invalid", "metadata");
  const missingPage = await missingOutcome(publicJobDetail().id, "page");
  const missingLayout = await missingOutcome(publicJobDetail().id, "layout");
  const malformedLayout = await missingOutcome("invalid", "layout");
  mockResponse(
    {
      error: {
        code: "PRIVATE_DATABASE_ERROR",
        message: "postgres private-token",
      },
    },
    500,
  );
  const failure = await renderPage(publicJobDetail().id);
  const unavailableLayout = markup(
    await JobLayout({
      params: Promise.resolve({ jobId: publicJobDetail().id }),
      children: <p>Public unavailable feedback</p>,
    }),
  );
  const unavailableMetadata = await generateMetadata({
    params: Promise.resolve({ jobId: publicJobDetail().id }),
  });
  mockResponse(publicJobDetail({ source_url: "javascript:attack()" }));
  const unsafeApi = await renderPage(publicJobDetail().id);

  assert.deepEqual(unexpectedRequests, []);
  process.stdout.write(
    JSON.stringify({
      observed,
      sparse,
      absent,
      reappeared,
      tentative,
      partialSalary,
      plain,
      encoded,
      dashboardEncoded,
      emptyDescriptions,
      dashboardEmpty,
      dashboardHeadings,
      unsafeComponentLinks,
      httpSource,
      metadata,
      missingMetadata,
      malformedMetadata,
      missingPage,
      availableLayout,
      missingLayout,
      malformedLayout,
      unavailableLayout,
      failure,
      unavailableMetadata,
      unsafeApi,
      loading: markup(<JobLoading />),
      missing: markup(<JobNotFound />),
      boundary: markup(
        <JobError
          error={new Error("private-token stack trace")}
          reset={() => {}}
        />,
      ),
    }),
  );
}

void render();
