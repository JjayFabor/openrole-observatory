import assert from "node:assert/strict";
import test from "node:test";
import { getSiteOrigin } from "../lib/seo/site";
import { buildHomeMetadata, buildJobsMetadata, buildRobots, buildUnavailableJobMetadata } from "../lib/seo/metadata";
import { buildPublicJobMetadata } from "../lib/public-jobs/detail-metadata";
import { publicJobDetail } from "./public-jobs-fixtures";

const site = new URL("https://openrole.test/");

test("canonical origin must be explicit, origin-only and safe for production", () => {
  assert.equal(getSiteOrigin("https://OpenRole.test/", "production")?.href, site.href);
  for (const value of ["", "   ", "broken", "//openrole.test", "ftp://openrole.test", "https://user:password@openrole.test", "https://openrole.test/path", "https://openrole.test/?q=a", "https://openrole.test/#home", "http://openrole.test", "https://localhost", "https://127.0.0.1", "https://[::1]"]) {
    assert.equal(getSiteOrigin(value, "production"), null, String(value));
  }
  assert.equal(getSiteOrigin("http://localhost:3000", "development")?.href, "http://localhost:3000/");
});

test("home and default discovery use the configured canonical origin and factual social metadata", () => {
  const home = buildHomeMetadata(site);
  const jobs = buildJobsMetadata(false, site);
  assert.equal(home.alternates?.canonical, site.href);
  assert.equal(jobs.alternates?.canonical, "https://openrole.test/jobs");
  assert.deepEqual(home.robots, { index: true, follow: true });
  assert.deepEqual(jobs.robots, { index: true, follow: true });
  assert.equal(home.openGraph?.url, site.href);
  assert.equal(jobs.openGraph?.siteName, "OpenRole");
  assert.ok(jobs.openGraph && "type" in jobs.openGraph);
  assert.equal(jobs.openGraph.type, "website");
});

test("filtered discovery is noindex/follow and canonicalizes to the default Jobs page", () => {
  const metadata = buildJobsMetadata(true, site);
  assert.deepEqual(metadata.robots, { index: false, follow: true });
  assert.equal(metadata.alternates?.canonical, "https://openrole.test/jobs");
});

test("detail canonical and indexing follow real identity and lifecycle, including reappearance", () => {
  for (const job of [publicJobDetail(), publicJobDetail({ reappeared_at: "2026-10-12T00:00:00Z", no_longer_observed_at: "2026-10-11T00:00:00Z" })]) {
    const metadata = buildPublicJobMetadata(job, site);
    assert.equal(metadata.alternates?.canonical, `https://openrole.test/jobs/${job.id}`);
    assert.deepEqual(metadata.robots, { index: true, follow: true });
    assert.equal(metadata.openGraph?.title, `${job.title} at ${job.company.name} · OpenRole`);
    assert.equal(metadata.openGraph?.url, metadata.alternates?.canonical);
  }
  const historical = buildPublicJobMetadata(publicJobDetail({ lifecycle_status: "not_observed" }), site);
  assert.deepEqual(historical.robots, { index: false, follow: true });
  assert.match(historical.description ?? "", /Historical listing/);
  assert.doesNotMatch(historical.title as string, /Closed|Expired/);
});

test("sparse and hostile source text stays factual metadata without inferred schema facts", () => {
  const metadata = buildPublicJobMetadata(publicJobDetail({
    title: 'Engineer </script><script>attack()</script>',
    company: { name: 'Employer <img src=x>', domain: null, careers_url: null },
    location_text: null, employment_type: null, workplace_type: null,
  }), site);
  assert.equal(metadata.title, 'Engineer </script><script>attack()</script> at Employer <img src=x>');
  assert.doesNotMatch(JSON.stringify(metadata), /undefined|null|Unknown location|datePosted|validThrough|JobPosting|source_observation_id|content_hash/);
  assert.deepEqual(buildPublicJobMetadata(publicJobDetail({ title: " " }), site).robots, { index: false, follow: true });
});

test("unset origin and unavailable detail never invent canonical URLs or permit indexing", () => {
  for (const metadata of [buildHomeMetadata(null), buildJobsMetadata(false, null), buildPublicJobMetadata(publicJobDetail(), null)]) {
    assert.equal(metadata.alternates, undefined);
    assert.equal(metadata.openGraph?.url, undefined);
    assert.deepEqual(metadata.robots, { index: false, follow: true });
  }
  const unavailable = buildUnavailableJobMetadata();
  assert.deepEqual(unavailable.robots, { index: false, follow: false });
  assert.equal(unavailable.alternates, undefined);
  assert.equal(unavailable.openGraph, undefined);
});

test("metadata preserves company abbreviations without duplicated sentence punctuation", () => {
  const metadata = buildPublicJobMetadata(publicJobDetail({
    company: { name: "Example Inc.", domain: null, careers_url: null },
    location_text: "Washington, D.C.",
  }), site);
  assert.match(metadata.description ?? "", /Example Inc\. Washington, D\.C\. Remote/);
  assert.doesNotMatch(metadata.description ?? "", /Inc\.\.|D\.C\.\./);
});

test("robots advertise only the public sitemap and exclude operational paths; unset sites disallow crawling", () => {
  const rules = buildRobots(site);
  assert.equal(rules.sitemap, "https://openrole.test/sitemap.xml");
  assert.deepEqual(rules.rules, { userAgent: "*", allow: "/", disallow: ["/dashboard", "/dashboard/", "/api", "/api/"] });
  assert.deepEqual(buildRobots(null), { rules: { userAgent: "*", disallow: "/" } });
});
