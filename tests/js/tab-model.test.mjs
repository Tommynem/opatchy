import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const repositoryRoot = resolve(import.meta.dirname, "../..");
const modelPath = resolve(repositoryRoot, "qml/models/TabModel.js");

function loadModel() {
  assert.equal(existsSync(modelPath), true, "Todo 20 tab model must exist");
  const source = readFileSync(modelPath, "utf8").replace(".pragma library", "");
  const context = vm.createContext({ Array, Date, Math, Number, Object, String });
  vm.runInContext(source, context, { filename: modelPath });
  return context;
}

function source(name, status = "ok") {
  return {
    source: name,
    status,
    provenance: status === "stale" ? "last_good" : "live",
    observedAt: "2026-08-26T00:00:00.000Z",
    freshUntil: "2026-08-26T00:05:00.000Z",
    cause: status === "ok" || status === "not_applicable" ? null : {
      code: "SOURCE_UNAVAILABLE",
      message: "fixture failure",
    },
  };
}

function snapshot(overrides = {}) {
  return {
    generatedAt: "2026-08-26T00:00:00.000Z",
    payload: {
      scanState: "complete",
      sources: [
        source("security"),
        source("cisa-kev"),
        source("omarchy"),
        source("arch"),
        source("aur"),
        source("flatpak"),
        source("mise"),
      ],
      summary: {
        totalUpdates: 6,
        watchedUpdates: 1,
        securityFindings: 2,
        degradedSources: 0,
      },
      items: [
        { source: "omarchy" },
        { source: "arch" },
        { source: "arch" },
        { source: "aur" },
        { source: "flatpak" },
        { source: "mise" },
      ],
    },
    ...overrides,
  };
}

test("builds the six approved tabs in stable order with source counts", () => {
  const model = loadModel();
  const view = model.buildPanelState(snapshot(), {}, Date.parse("2026-08-26T00:01:00.000Z"));

  assert.deepEqual(JSON.parse(JSON.stringify(view.tabs.map((tab) => tab.name))), [
    "Security", "Omarchy", "System", "AUR", "Flatpak", "mise",
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(view.tabs.map((tab) => tab.count))), [2, 1, 2, 1, 1, 1]);
  assert.equal(view.summaryText, "6 updates, 2 security findings, 0 sources need attention");
});

test("renders every supported source health with visible text, glyph, and tooltip", () => {
  const model = loadModel();
  const cases = [
    ["ok", "Current"],
    ["not_applicable", "Not applicable"],
    ["missing_dependency", "Unavailable"],
    ["offline", "Unavailable"],
    ["timeout", "Unavailable"],
    ["error", "Unavailable"],
    ["invalid", "Incompatible"],
    ["stale", "Last known"],
    ["future-status", "Incompatible"],
  ];

  for (const [status, text] of cases) {
    const health = model.healthForStatus(status);
    assert.equal(health.text, text, status);
    assert.notEqual(health.glyph, "", status);
    assert.match(health.tooltip, new RegExp(text), status);
  }
});

test("restores only valid tab selections and deterministically falls back to Security", () => {
  const model = loadModel();

  assert.equal(model.restoreSelection("Flatpak", false), "Flatpak");
  assert.equal(model.restoreSelection("missing", false), "Security");
  assert.equal(model.restoreSelection("missing", true), "Security");
  assert.equal(model.restoreSelection(null, true), "Security");

  const urgent = snapshot();
  urgent.payload.findings = [{ findings: [{ severity: "high" }] }];
  assert.equal(model.hasUrgentSecurity(urgent), true);
  urgent.payload.findings[0].findings[0].severity = "medium";
  assert.equal(model.hasUrgentSecurity(urgent), false);
});

test("persists only a valid UI tab selection through the host inline settings path", () => {
  const model = loadModel();
  const calls = [];
  const shell = {
    updateEntryInline(moduleName, settings) {
      calls.push({ moduleName, settings });
      return true;
    },
  };

  assert.equal(model.persistSelection(shell, "io.github.tomge.opatchy", { notifySecurity: true }, "AUR"), true);
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [{
    moduleName: "io.github.tomge.opatchy",
    settings: { notifySecurity: true, lastSelectedTab: "AUR" },
  }]);
  assert.equal(model.persistSelection(shell, "io.github.tomge.opatchy", {}, "future-tab"), false);
  assert.equal(calls.length, 1);
});

test("reports scan running, stale, partial, and typed failures without treating data as current", () => {
  const model = loadModel();
  const stale = snapshot();
  stale.payload.scanState = "partial";
  stale.payload.sources[2] = source("omarchy", "stale");
  stale.payload.summary.degradedSources = 1;
  const view = model.buildPanelState(stale, {
    busy: true,
    lastAttemptAt: Date.parse("2026-08-26T00:00:30.000Z"),
    lastSuccessAt: Date.parse("2026-08-26T00:00:00.000Z"),
    lastFailureKind: "timeout",
    lastError: "helper operation timed out",
  }, Date.parse("2026-08-26T00:01:00.000Z"));

  assert.equal(view.refreshText, "Refreshing");
  assert.match(view.bannerText, /Partial scan/);
  assert.match(view.bannerText, /Last known data/);
  assert.match(view.failureText, /timed out/);
  assert.equal(view.tabs[1].health.text, "Last known");
  assert.equal(view.lastAttemptText, "30 seconds ago");
  assert.equal(view.lastSuccessText, "1 minute ago");
});

test("keeps unavailable tabs visible with their explanation", () => {
  const model = loadModel();
  const unavailable = snapshot();
  unavailable.payload.sources[4] = source("aur", "missing_dependency");
  const view = model.buildPanelState(unavailable, {}, Date.parse("2026-08-26T00:01:00.000Z"));
  const aur = view.tabs.find((tab) => tab.name === "AUR");

  assert.equal(view.tabs.length, 6);
  assert.equal(aur.count, 1);
  assert.equal(aur.healthText, "Unavailable");
  assert.match(aur.tooltip, /Unavailable/);
});

test("shows incompatibility while retaining the validated last-good tab data", () => {
  const model = loadModel();
  const lastGood = snapshot();
  const view = model.buildPanelState(lastGood, {
    busy: false,
    lastFailureKind: "incompatible",
    lastError: "helper snapshot is invalid",
  }, Date.parse("2026-08-26T00:01:00.000Z"));

  assert.equal(view.tabs[2].count, 2);
  assert.match(view.failureText, /Incompatible data/);
  assert.match(view.failureText, /last known result/);
  assert.equal(model.healthForStatus("unknown-future").text, "Incompatible");
});
