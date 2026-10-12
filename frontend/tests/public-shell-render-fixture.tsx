import Module, { createRequire } from "node:module";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import PublicLayout from "../app/(public)/layout";
import PublicHome, { metadata as homeMetadata } from "../app/(public)/page";
import NotFound from "../app/not-found";
import { publicJob } from "./public-jobs-fixtures";

// The production bundler owns CSS; this Node rendering fixture only needs markup.
const require = createRequire(import.meta.url);
require.extensions[".css"] = () => {};
const serverOnly = require.resolve("server-only");
const sentinel = new Module(serverOnly);
sentinel.exports = {};
sentinel.loaded = true;
require.cache[serverOnly] = sentinel;

let fetchCalls = 0;
globalThis.fetch = async () => {
  fetchCalls += 1;
  throw new Error("Public shell rendering must not depend on the backend.");
};

async function renderPublicShell() {
  const { default: RootLayout, metadata: rootMetadata } =
    await import("../app/layout");
  const { metadata: dashboardMetadata } =
    await import("../app/dashboard/layout");
  const home = renderToStaticMarkup(
    <RootLayout>
      <PublicLayout>
        <PublicHome />
      </PublicLayout>
    </RootLayout>,
  );
  const missing = renderToStaticMarkup(
    <RootLayout>
      <NotFound />
    </RootLayout>,
  );
  const staticFetchCalls = fetchCalls;
  globalThis.fetch = async (input) => {
    assert.equal(new URL(String(input)).pathname, "/api/v1/public/jobs");
    fetchCalls += 1;
    return Response.json({
      items: [publicJob()],
      total: 1,
      limit: 25,
      offset: 0,
    });
  };
  const { default: PublicJobs, generateMetadata: generateJobsMetadata } =
    await import("../app/(public)/jobs/page");
  const jobsMetadata = await generateJobsMetadata({ searchParams: Promise.resolve({}) });
  const jobs = await PublicJobs({ searchParams: Promise.resolve({}) });

  process.stdout.write(
    JSON.stringify({
      home,
      jobs: renderToStaticMarkup(
        <RootLayout>
          <PublicLayout>{jobs}</PublicLayout>
        </RootLayout>,
      ),
      missing,
      rootMetadata,
      dashboardMetadata,
      homeMetadata,
      jobsMetadata,
      staticFetchCalls,
      jobsFetchCalls: fetchCalls - staticFetchCalls,
    }),
  );
}

void renderPublicShell();
