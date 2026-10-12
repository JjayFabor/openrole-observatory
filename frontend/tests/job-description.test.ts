import assert from "node:assert/strict";
import { encodeXML } from "entities";
import test from "node:test";
import { sanitizeJobDescription } from "../lib/jobs/description-html";

test("entity-encoded source descriptions render block structure, lists and entities", () => {
  const encoded = encodeXML(
    '<div class="content-intro"><div>Employer &amp; team</div><div>Build <strong>systems</strong>.</div></div><h2>Responsibilities</h2><ul><li>Help&nbsp;people</li></ul>',
  );
  const html = sanitizeJobDescription(encoded);
  assert.equal(
    html,
    "<div><div>Employer &amp; team</div><div>Build <strong>systems</strong>.</div></div><h3>Responsibilities</h3><ul><li>Help\u00a0people</li></ul>",
  );
  assert.doesNotMatch(html, /&lt;div|&amp;nbsp|class=/);
});

test("decimal and hexadecimal encoded markup is decoded before sanitization", () => {
  for (const encoded of [
    "&#60;p&#62;Role&#60;/p&#62;",
    "&#x3c;p&#x3e;Role&#x3c;/p&#x3e;",
    "\n&lt;p&gt;Role&lt;/p&gt;",
  ]) {
    assert.equal(sanitizeJobDescription(encoded).trim(), "<p>Role</p>");
  }
});

test("decoded descriptions still remove scripts, handlers, embeds and unsafe links", () => {
  const html = sanitizeJobDescription(
    encodeXML(
      '<div class="content-intro" onclick="attack()" style="position:fixed">Safe<script>privateScript()</script><img src=x onerror=attack()><iframe src="https://attack.test"></iframe><svg><text>attack()</text></svg><form><input onfocus=attack()></form><a href="jav&#x61;script:attack()">Bad</a><a href="https://user:secret@example.test">Credentials</a><a href="https://example.test/details">Details</a></div>',
    ),
  );
  assert.match(html, /^<div>Safe<a>Bad<\/a><a>Credentials<\/a>/);
  assert.match(
    html,
    /href="https:\/\/example.test\/details" target="_blank" rel="noopener noreferrer"/,
  );
  assert.doesNotMatch(
    html,
    /script|privateScript|onerror|onclick|onfocus|style=|iframe|svg|form|secret|attack|&lt;/,
  );
});

test("native HTML and ordinary text retain deliberately escaped tag examples", () => {
  const example = "<p>Use &lt;strong&gt;text&lt;/strong&gt; for emphasis.</p>";
  assert.equal(sanitizeJobDescription(example), example);
  assert.equal(
    sanitizeJobDescription("Example: &lt;p&gt;text&lt;/p&gt;"),
    "Example: &lt;p&gt;text&lt;/p&gt;",
  );
  const encodedExample = encodeXML("<p>Use &lt;strong&gt;text&lt;/strong&gt;.</p>");
  assert.equal(
    sanitizeJobDescription(encodedExample),
    "<p>Use &lt;strong&gt;text&lt;/strong&gt;.</p>",
  );
});
test("sanitizer retains semantic text/headings/lists and protects external links", () => {
  const html = sanitizeJobDescription(
    '<h1>Role</h1><p>Hello <strong>world</strong>.</p><ul><li>Build pipelines</li></ul><a href="https://example.test/jobs" target="_self" rel="opener">Details</a>',
  );
  assert.match(html, /<h3>Role<\/h3>/);
  assert.match(html, /<ul><li>Build pipelines<\/li><\/ul>/);
  assert.match(
    html,
    /href="https:\/\/example.test\/jobs" target="_blank" rel="noopener noreferrer"/,
  );
});
test("sanitizer removes scripts, styling, handlers, dangerous embeds and form markup", () => {
  const html = sanitizeJobDescription(
    '<p style="position:fixed" onclick="attack()">Valid</p><script>attack()</script><style>body{display:none}</style><img src=x onerror=attack()><iframe src="https://attack.test"></iframe><svg><a href="javascript:attack()">attack()</a></svg><math><mtext>attack()</mtext></math><form><input autofocus onfocus=attack()></form>',
  );
  assert.equal(html, "<p>Valid</p>");
  assert.doesNotMatch(
    html,
    /script|style|onclick|onerror|onfocus|iframe|svg|math|form|attack/,
  );
});
test("sanitizer rejects encoded/obfuscated unsafe protocols, relative links and credentials", () => {
  for (const href of [
    "javascript:attack()",
    "jav&#x61;script:attack()",
    "java&#10;script:attack()",
    "data:text/html,attack",
    "//attack.test",
    "/relative",
    "#anchor",
    "https://user:password@example.test",
    "ftp://example.test/file",
  ]) {
    const html = sanitizeJobDescription(`<a href="${href}">safe text</a>`);
    assert.equal(html, "<a>safe text</a>");
  }
});
test("all provider heading levels become h3 below the page description heading", () => {
  const html = sanitizeJobDescription(
    "<h1>One</h1><h2>Two</h2><h3>Three</h3><h4>Four</h4><h5>Five</h5><h6>Six</h6>",
  );
  assert.equal([...html.matchAll(/<h3>/g)].length, 6);
  assert.doesNotMatch(html, /<\/?h[12456]>/);
  assert.match(html, /<h3>Six<\/h3>/);
});
test("plain text and broken markup are escaped by the maintained sanitizer", () => {
  assert.equal(
    sanitizeJobDescription("Salary < 100000 & benefits"),
    "Salary &lt; 100000 &amp; benefits",
  );
  const html = sanitizeJobDescription("<p>Safe <strong>content<p>More");
  assert.match(html, /Safe/);
  assert.doesNotMatch(html, /script|onerror/);
});
