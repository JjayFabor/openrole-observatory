import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import test from "node:test";

type BrandFixture = {
  primary: string;
  accent: string;
  inverse: string;
  dashboard: string;
};

const rendered: BrandFixture = JSON.parse(
  execFileSync(
    process.execPath,
    ["--import", "tsx", "tests/brand-render-fixture.tsx"],
    { cwd: process.cwd(), encoding: "utf8" },
  ),
);

test("wordmark variants render accessible supplied artwork at a stable aspect ratio", () => {
  for (const [variant, filename] of [
    ["primary", "openrole-logo-v4.svg"],
    ["accent", "openrole-logo-v4-accent.svg"],
    ["inverse", "openrole-logo-v4-inverse.svg"],
  ] as const) {
    const image = rendered[variant].match(/<img\b[^>]*>/)?.[0];
    assert.ok(image);
    assert.match(image, /alt="OpenRole"/);
    assert.match(image, /width="310"/);
    assert.match(image, /height="78"/);
    assert.ok(image.includes(`src="/brand/${filename}"`));
    assert.ok(readFileSync(`public/brand/${filename}`, "utf8").startsWith("<svg"));
  }
});

test("the shared sidebar and mobile drawer brand identifies OpenRole Observatory", () => {
  assert.match(rendered.dashboard, /alt="OpenRole"/);
  assert.match(rendered.dashboard, /src="\/brand\/openrole-logo-v4.svg"/);
  assert.match(rendered.dashboard, />Observatory<\/p>/);
});

test("Next's file-based icon contains the supplied favicon artwork", () => {
  const icon = readFileSync("app/icon.svg", "utf8");
  assert.equal(icon, readFileSync("public/brand/openrole-favicon-v4.svg", "utf8"));
  assert.match(icon, /viewBox="0 0 64 64"/);
  assert.match(icon, /stroke="#0F172A"/);
});
