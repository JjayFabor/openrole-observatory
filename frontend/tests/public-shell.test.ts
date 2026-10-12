import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";

type PageMetadata = {
  title:
    | string
    | { default: string; template: string }
    | { absolute: string; template: string };
  description: string;
  openGraph?: { title: string; description: string; type: string };
  alternates?: { canonical: string };
};

type PublicShellFixture = {
  home: string;
  jobs: string;
  missing: string;
  rootMetadata: PageMetadata;
  dashboardMetadata: PageMetadata;
  homeMetadata: PageMetadata;
  jobsMetadata: PageMetadata;
  staticFetchCalls: number;
  jobsFetchCalls: number;
};

const rendered: PublicShellFixture = JSON.parse(
  execFileSync(
    process.execPath,
    ["--import", "tsx", "tests/public-shell-render-fixture.tsx"],
    {
      cwd: process.cwd(),
      encoding: "utf8",
      env: {
        ...process.env,
        OPENROLE_API_BASE_URL: "http://127.0.0.1:1",
        OPENROLE_SITE_URL: "",
      },
    },
  ),
);

function links(markup: string) {
  return [
    ...markup.matchAll(/<a\b[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/g),
  ].map((match) => ({
    href: match[1],
    text: match[2]
      .replace(/<img\b[^>]*alt="([^"]*)"[^>]*>/g, "$1")
      .replace(/<[^>]*>/g, ""),
  }));
}

function textContent(markup: string) {
  return markup.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
}

test("both actual public routes share accessible document landmarks and skip navigation", () => {
  for (const markup of [rendered.home, rendered.jobs]) {
    assert.match(markup, /<html lang="en">/);
    assert.equal([...markup.matchAll(/<main\b/g)].length, 1);
    assert.equal([...markup.matchAll(/<h1\b/g)].length, 1);
    assert.equal([...markup.matchAll(/<footer\b/g)].length, 1);
    assert.match(markup, /<nav aria-label="Public navigation">/);
    assert.match(markup, /href="#public-content"[^>]*>Skip to content<\/a>/);
    assert.match(markup, /<main id="public-content" tabindex="-1"/);
  }
});

test("public header and home calls to action lead to real public routes", () => {
  for (const markup of [rendered.home, rendered.jobs]) {
    const header = markup.match(/<header\b[^>]*>([\s\S]*?)<\/header>/)?.[1];
    assert.ok(header);
    assert.deepEqual(links(header), [
      { href: "/", text: "OpenRole" },
      { href: "/jobs", text: "Jobs" },
    ]);
  }
  const homeLinks = links(rendered.home);
  const browseLinks = homeLinks.filter((link) => link.text === "Browse jobs");
  assert.equal(browseLinks.length, 2);
  assert.ok(browseLinks.every((link) => link.href === "/jobs"));
  assert.ok(
    homeLinks.some(
      (link) => link.text === "How it works" && link.href === "/#how-it-works",
    ),
  );
  assert.match(
    rendered.home,
    /<section id="how-it-works" aria-labelledby="how-it-works-heading"/,
  );
  assert.match(rendered.home, /<h2 id="how-it-works-heading"/);
});

test("public routes omit internal links, actions, and fabricated job results", () => {
  for (const markup of [rendered.home, rendered.jobs]) {
    assert.ok(
      links(markup).every(
        (link) =>
          ["/", "/jobs", "/#how-it-works", "#public-content"].includes(
            link.href,
          ) || /^\/jobs\/[0-9a-f-]+$/i.test(link.href),
      ),
    );
    assert.doesNotMatch(
      markup,
      /\/dashboard|PipelineRun|RawSnapshot|Synchronize|<table\b/,
    );
    const images = [...markup.matchAll(/<img\b[^>]*>/g)].map(
      (match) => match[0],
    );
    assert.equal(images.length, 2);
    assert.deepEqual(
      images.map((image) => image.match(/src="([^"]*)"/)?.[1]),
      [
        "/brand/openrole-logo-v4-accent.svg",
        "/brand/openrole-logo-v4-inverse.svg",
      ],
    );
    for (const image of images) {
      assert.match(image, /alt="OpenRole"/);
      assert.match(image, /width="310"/);
      assert.match(image, /height="78"/);
    }
  }
});

test("public footer preserves an accessible home link with the inverse wordmark", () => {
  for (const markup of [rendered.home, rendered.jobs]) {
    const footer = markup.match(/<footer\b[^>]*>([\s\S]*?)<\/footer>/)?.[1];
    assert.ok(footer);
    assert.deepEqual(links(footer), [{ href: "/", text: "OpenRole" }]);
    assert.match(footer, /src="\/brand\/openrole-logo-v4-inverse.svg"/);
    assert.match(textContent(footer), /Direct-source job intelligence\./);
  }
});

test("landing copy explains observations and current coverage without hiring or cadence guarantees", () => {
  const text = textContent(rendered.home);
  assert.match(text, /coverage.*limited.*configured Greenhouse/i);
  assert.match(text, /Last observed.*listing.*seen.*source check/i);
  assert.doesNotMatch(text, /checks.*manually/i);
  assert.match(text, /timestamp.*evidence.*collected/i);
  assert.match(text, /not confirmation.*hiring/i);
  assert.match(text, /observed.*distinct.*posting or update date/i);
  assert.match(text, /Recent listing changes.*public Job Detail/i);
  assert.doesNotMatch(
    text,
    /verified open|actively hiring|periodically|automatically|continuously|most recent successful check|Lever|Ashby/i,
  );
});

test("Jobs uses the public shell for real discovery and keeps the home return path", () => {
  const text = textContent(rendered.jobs);
  assert.match(text, /Find jobs with visible source freshness/);
  assert.match(rendered.jobs, /<form\b[^>]*action="\/jobs"/);
  assert.match(text, /1 job found/);
  assert.ok(
    links(rendered.jobs).some(
      (link) => link.href === "/" && link.text === "OpenRole",
    ),
  );
  assert.doesNotMatch(text, /Task \d+|API|Pipeline|forthcoming|Verified jobs/i);
});

test("the root missing page is neutral and returns to the public home", () => {
  assert.match(textContent(rendered.missing), /Page not found/);
  assert.deepEqual(links(rendered.missing), [
    { href: "/", text: "Back to home" },
  ]);
  assert.doesNotMatch(rendered.missing, /dashboard|overview/i);
});

test("metadata separates public meaning from existing internal dashboard titles", () => {
  assert.deepEqual(rendered.rootMetadata.title, {
    default: "OpenRole",
    template: "%s · OpenRole",
  });
  assert.doesNotMatch(rendered.rootMetadata.description, /Internal|dashboard/i);
  assert.deepEqual(rendered.dashboardMetadata.title, {
    absolute: "OpenRole Observatory",
    template: "%s · OpenRole",
  });
  assert.match(rendered.dashboardMetadata.description, /Internal dashboard/);
  assert.equal(rendered.rootMetadata.openGraph, undefined);
  assert.equal(rendered.dashboardMetadata.openGraph, undefined);
  assert.equal(rendered.jobsMetadata.title, "Jobs");
  assert.match(rendered.jobsMetadata.description, /currently observed/);
  assert.match(String(rendered.homeMetadata.title), /source freshness/);
  assert.equal(rendered.homeMetadata.openGraph?.type, "website");
  assert.match(
    rendered.homeMetadata.openGraph?.description ?? "",
    /observations/,
  );
  for (const metadata of [
    rendered.rootMetadata,
    rendered.homeMetadata,
    rendered.jobsMetadata,
    rendered.dashboardMetadata,
  ]) {
    assert.equal(metadata.alternates?.canonical, undefined);
    assert.doesNotMatch(JSON.stringify(metadata), /https?:\/\//);
  }
});

test("landing and root missing page stay backend-independent while discovery fetches only public jobs", () => {
  assert.equal(rendered.staticFetchCalls, 0);
  assert.equal(rendered.jobsFetchCalls, 1);
});
