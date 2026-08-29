import assert from "node:assert/strict";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const repositoryRoot = resolve(import.meta.dirname, "../..");
const modelPath = resolve(repositoryRoot, "qml/models/SecurityViewModel.js");
const linkPolicyPath = resolve(repositoryRoot, "qml/models/SecurityLinkPolicy.js");

function load(path, message) {
  assert.equal(existsSync(path), true, message);
  const context = vm.createContext({ Array, Date, Math, Number, Object, RegExp, String });
  vm.runInContext(readFileSync(path, "utf8").replace(".pragma library", ""), context, { filename: path });
  return context;
}

function source(name, overrides = {}) {
  return {
    source: name,
    status: "ok",
    provenance: "live",
    observedAt: "2026-08-26T00:00:00.000Z",
    freshUntil: "2026-08-26T01:00:00.000Z",
    cause: null,
    ...overrides,
  };
}

function finding(id, overrides = {}) {
  return {
    id,
    itemId: "arch:openssl",
    advisoryId: id,
    cveIds: ["CVE-2026-1000"],
    severity: "high",
    fixedVersion: "3.1.2",
    installedVersion: "3.1.1",
    knownExploited: false,
    kevStatus: "not_listed",
    kevProvenance: "live",
    provenance: "live",
    status: "Fixed",
    type: "security",
    ...overrides,
  };
}

function snapshot(groups = [], overrides = {}) {
  return {
    generatedAt: "2026-08-26T00:00:00.000Z",
    generationId: "security-current",
    payload: {
      sources: [source("security"), source("cisa-kev")],
      findings: groups,
    },
    ...overrides,
  };
}

function group(itemId, findings) {
  return { itemId, findings };
}

test("shows the exact clean sentence only for current valid Arch security evidence", () => {
  const model = load(modelPath, "Todo 22 security view model must exist");
  const view = model.securityView(snapshot(), Date.parse("2026-08-26T00:02:00.000Z"));

  assert.equal(view.kind, "clean");
  assert.equal(view.statusText, "No known matching advisories in the current Arch data");
  assert.equal(view.groups.length, 0);
  assert.equal(view.archCoverage.text, "Arch security data: current");
});

test("accepts fresh fallback and cache provenance as current Arch and KEV evidence", () => {
  const model = load(modelPath, "Todo 22 security view model must exist");
  const currentTime = Date.parse("2026-08-26T00:02:00.000Z");

  for (const provenance of ["fallback", "cache"]) {
    const clean = snapshot([], { payload: { sources: [source("security", { provenance }), source("cisa-kev", { provenance })], findings: [] } });
    const findings = snapshot([group("arch:openssl", [finding("AVG-89", { provenance, kevProvenance: provenance })])], { payload: { sources: [source("security", { provenance }), source("cisa-kev", { provenance })], findings: [group("arch:openssl", [finding("AVG-89", { provenance, kevProvenance: provenance })])] } });

    assert.equal(model.securityView(clean, currentTime).kind, "clean", provenance);
    assert.equal(model.securityView(clean, currentTime).archCoverage.text, "Arch security data: current", provenance);
    assert.equal(model.securityView(clean, currentTime).kevCoverage.text, "CISA KEV data: current", provenance);
    assert.equal(model.securityView(findings, currentTime).kind, "findings", provenance);
  }
});

test("rejects misleading ok last-good, missing, and unknown Arch provenance", () => {
  const model = load(modelPath, "Todo 22 security view model must exist");
  const currentTime = Date.parse("2026-08-26T00:02:00.000Z");

  for (const provenance of ["last_good", null, "unexpected"]) {
    const document = snapshot([], { payload: { sources: [source("security", { provenance }), source("cisa-kev")], findings: [] } });
    assert.equal(model.securityView(document, currentTime).kind, "unknown", String(provenance));
  }
});

test("does not turn expired current-looking Arch metadata into a clean result", () => {
  const model = load(modelPath, "Todo 22 security view model must exist");
  const currentTime = Date.parse("2026-08-26T00:02:00.000Z");
  const document = snapshot([], { payload: { sources: [source("security", { freshUntil: "2026-08-26T00:01:00.000Z" }), source("cisa-kev")], findings: [] } });

  assert.equal(model.securityView(document, currentTime).kind, "unknown");
});

test("keeps fixed and no-fix findings with installed, advisory, and canonical watch evidence", () => {
  const model = load(modelPath, "Todo 22 security view model must exist");
  const view = model.securityView(snapshot([group("arch:openssl", [
    finding("AVG-20"),
    finding("AVG-21", { fixedVersion: null, installedVersion: "3.1.0", status: "Vulnerable" }),
  ])]), Date.parse("2026-08-26T00:02:00.000Z"));

  assert.equal(view.kind, "findings");
  assert.equal(view.groups[0].watchTarget, "arch:openssl");
  assert.equal(view.groups[0].packageName, "openssl");
  assert.equal(view.groups[0].findings[0].versionText, "Installed 3.1.1; fixed in 3.1.2");
  assert.equal(view.groups[0].findings[1].versionText, "Installed 3.1.0; no fixed version reported");
  assert.equal(view.groups[0].findings[0].advisoryId, "AVG-20");
});

test("exposes only bounded canonical fixed-version watch request identity", () => {
  const model = load(modelPath, "Todo 27 security view model must exist");
  const currentTime = Date.parse("2026-08-26T00:02:00.000Z");
  const qualified = model.securityView(snapshot([group("arch:openssl", [
    finding("AVG-20", { cveIds: ["CVE-2026-1001", "CVE-2026-1000"] }),
  ])]), currentTime).groups[0].findings[0];

  assert.deepEqual(JSON.parse(JSON.stringify(qualified.watchRequest)), {
    itemId: "arch:openssl",
    securityAdvisory: "AVG-20",
    fixedVersion: "3.1.2",
    cveIds: ["CVE-2026-1001", "CVE-2026-1000"],
  });

  for (const overrides of [
    { cveIds: [] },
    { cveIds: ["CVE-2026-1000", "CVE-2026-1000"] },
    { cveIds: Array.from({ length: 17 }, (_, index) => `CVE-2026-${1000 + index}`) },
    { fixedVersion: "3.1.2\nnot-a-version" },
    { fixedVersion: "x".repeat(257) },
  ]) {
    const row = model.securityView(snapshot([group("arch:openssl", [finding("AVG-21", overrides)])]), currentTime).groups[0].findings[0];
    assert.equal(row.watchRequest, null, JSON.stringify(overrides));
  }
});

test("retains multiple advisories and CVEs with exact KEV meanings", () => {
  const model = load(modelPath, "Todo 22 security view model must exist");
  const view = model.securityView(snapshot([group("arch:openssl", [
    finding("AVG-3", { cveIds: ["CVE-2026-1000", "CVE-2026-1001"], knownExploited: true, kevStatus: "listed" }),
    finding("AVG-4", { cveIds: ["CVE-2026-1002"], kevStatus: "not_listed" }),
    finding("AVG-5", { cveIds: [], kevStatus: "unavailable", kevProvenance: null }),
  ])]), Date.parse("2026-08-26T00:02:00.000Z"));

  assert.deepEqual(JSON.parse(JSON.stringify(view.groups[0].findings[0].cveIds)), ["CVE-2026-1000", "CVE-2026-1001"]);
  assert.equal(view.groups[0].findings[0].kevText, "The matched CVE is listed in the CISA Known Exploited Vulnerabilities Catalog for prioritization.");
  assert.equal(view.groups[0].findings[1].kevText, "The CVE is not listed in the current catalog data.");
  assert.equal(view.groups[0].findings[2].kevText, "KEV listing status is unknown or unavailable.");
});

test("presents stale, unavailable, and invalid Arch evidence as unknown or last-known rather than clean", () => {
  const model = load(modelPath, "Todo 22 security view model must exist");
  const currentTime = Date.parse("2026-08-26T00:02:00.000Z");
  const stale = snapshot([], { payload: { sources: [source("security", { status: "stale", provenance: "last_good", observedAt: "2026-08-26T00:00:00.000Z" }), source("cisa-kev", { status: "stale", provenance: "last_good" })], findings: [] } });
  const unavailable = snapshot([], { payload: { sources: [source("security", { status: "offline", provenance: "live" }), source("cisa-kev")], findings: [] } });
  const invalid = snapshot([], { payload: { sources: [source("security", { status: "invalid", provenance: "live" }), source("cisa-kev")], findings: [] } });

  assert.equal(model.securityView(stale, currentTime).kind, "last_known");
  assert.match(model.securityView(stale, currentTime).statusText, /last known/i);
  assert.equal(model.securityView(unavailable, currentTime).kind, "unknown");
  assert.equal(model.securityView(invalid, currentTime).kind, "unknown");
  assert.equal(model.securityView(stale, currentTime).archCoverage.ageText, "2 minutes ago");
});

test("reports CISA KEV coverage independently from current Arch advisory evidence", () => {
  const model = load(modelPath, "Todo 22 security view model must exist");
  const currentTime = Date.parse("2026-08-26T00:02:00.000Z");
  const document = snapshot([], { payload: { sources: [source("security"), source("cisa-kev", { status: "stale", provenance: "last_good" })], findings: [] } });

  const view = model.securityView(document, currentTime);
  assert.equal(view.kind, "clean");
  assert.equal(view.archCoverage.text, "Arch security data: current");
  assert.equal(view.kevCoverage.text, "CISA KEV data: last known");
});

test("uses only canonical Arch finding groups and inert bounded external text", () => {
  const model = load(modelPath, "Todo 22 security view model must exist");
  const hostile = "$(touch /tmp/opatchy-injection-sentinel)\n\u202e\u4f60\u597d\u0000" + "x".repeat(2_000);
  const view = model.securityView(snapshot([
    group("arch:openssl", [finding("AVG-10", { type: hostile, status: hostile })]),
  ]), Date.parse("2026-08-26T00:02:00.000Z"));

  assert.equal(view.groups.length, 1);
  assert.equal(view.groups[0].watchTarget, "arch:openssl");
  assert.equal(view.groups[0].findings[0].status.length <= 256, true);
  assert.equal(view.groups[0].findings[0].status.includes("\n"), false);
  assert.deepEqual(JSON.parse(JSON.stringify(view.groups[0].findings[0].cveIds)), ["CVE-2026-1000"]);
  for (const itemId of ["arch:0ad", "arch:lib32-openssl", "arch:foo.bar", "arch:foo_bar", "arch:foo+bar", "arch:foo@bar"]) {
    assert.equal(model.securityView(snapshot([group(itemId, [finding("AVG-11", { itemId })])]), Date.parse("2026-08-26T00:02:00.000Z")).kind, "findings", itemId);
  }
});

test("rejects malformed current Arch groups and findings instead of showing clean", () => {
  const model = load(modelPath, "Todo 22 security view model must exist");
  const currentTime = Date.parse("2026-08-26T00:02:00.000Z");
  const invalidGroups = ["aur:openssl", "arch:", "arch:.hidden", "arch:-option", "arch:bad\npkg", "arch:bad pkg", "arch:../pkg", "arch:https://example.invalid", "arch:" + "a".repeat(124)];

  for (const itemId of invalidGroups) assert.equal(model.securityView(snapshot([group(itemId, [finding("AVG-1", { itemId })])]), currentTime).kind, "unknown", itemId);
  for (const overrides of [{ itemId: "arch:other" }, { id: "AVG-" + "1".repeat(125), advisoryId: "AVG-" + "1".repeat(125) }, { cveIds: ["CVE-2026-" + "1".repeat(20)] }]) {
    assert.equal(model.securityView(snapshot([group("arch:openssl", [finding("AVG-1", overrides)])]), currentTime).kind, "unknown");
  }
});

test("sorts known-exploited, severity, fix availability, and canonical identities deterministically", () => {
  const model = load(modelPath, "Todo 22 security view model must exist");
  const view = model.securityView(snapshot([
    group("arch:zeta", [finding("AVG-30", { itemId: "arch:zeta", severity: "critical" })]),
    group("arch:alpha", [finding("AVG-20", { itemId: "arch:alpha", severity: "high", fixedVersion: null })]),
    group("arch:beta", [finding("AVG-10", { itemId: "arch:beta", severity: "high", knownExploited: true, kevStatus: "listed" })]),
    group("arch:gamma", [finding("AVG-15", { itemId: "arch:gamma", severity: "high" })]),
  ]), Date.parse("2026-08-26T00:02:00.000Z"));

  assert.deepEqual(JSON.parse(JSON.stringify(view.groups.map((entry) => entry.watchTarget))), ["arch:beta", "arch:zeta", "arch:gamma", "arch:alpha"]);
});

test("constructs allowlisted HTTPS links solely from canonical AVG and CVE identifiers", () => {
  const links = load(linkPolicyPath, "Todo 22 security link policy must exist");

  assert.equal(links.linkFor("arch-advisory", "AVG-123"), "https://security.archlinux.org/AVG-123");
  assert.equal(links.linkFor("cve", "CVE-2026-12345"), "https://www.cve.org/CVERecord?id=CVE-2026-12345");
  for (const value of ["AVG-1#fragment", "https://security.archlinux.org/AVG-1", "AVG-1@evil", "AVG-" + "1".repeat(125), "CVE-2026-1", "CVE-2026-1234#x", "CVE-2026-1234@evil", "CVE-2026-" + "1".repeat(20), "$(touch /tmp/opatchy-injection-sentinel)"]) {
    assert.equal(links.linkFor("arch-advisory", value), null);
    assert.equal(links.linkFor("cve", value), null);
  }
});

test("keeps hostile link and display input inert without creating a sentinel", () => {
  const sentinel = "/tmp/opatchy-injection-sentinel";
  const hostile = "$(touch /tmp/opatchy-injection-sentinel)";
  rmSync(sentinel, { force: true });
  const links = load(linkPolicyPath, "Todo 22 security link policy must exist");
  const model = load(modelPath, "Todo 22 security view model must exist");

  assert.equal(links.linkFor("cve", hostile), null);
  model.securityView(snapshot([group("arch:demo", [finding("AVG-88", { type: hostile })])]), Date.parse("2026-08-26T00:02:00.000Z"));
  assert.equal(existsSync(sentinel), false);
});

test("security presentation stays plain text and contains no assurance or local-exploitation copy", () => {
  const source = readFileSync(resolve(repositoryRoot, "qml/components/SecurityView.qml"), "utf8");
  const row = readFileSync(resolve(repositoryRoot, "qml/components/SecurityFindingRow.qml"), "utf8");
  const integration = readFileSync(resolve(repositoryRoot, "qml/components/SourceContent.qml"), "utf8");
  const link = readFileSync(resolve(repositoryRoot, "qml/components/SafeExternalLink.qml"), "utf8");

  assert.match(source, /textFormat:\s*Text\.PlainText/g);
  assert.match(source, /SecurityClock\s*\{/);
  assert.match(row, /textFormat:\s*Text\.PlainText/g);
  assert.match(integration, /SecurityView\s*\{/);
  assert.match(link, /SecurityLinkPolicy\.linkFor\(linkKind, identifier\)/);
  assert.doesNotMatch(link, /function\s+openUrl\s*\(/);
  const visibleCopy = (source + row + integration).match(/"[^"\n]*"/g).join("\n").toLowerCase();
  for (const forbidden of ["safe", "secure", "not exploitable", "exploited on this system"]) {
    assert.doesNotMatch(visibleCopy, new RegExp(`\\b${forbidden}\\b`));
  }
});
