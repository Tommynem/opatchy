import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const repositoryRoot = resolve(import.meta.dirname, "../..");
const modelPath = resolve(repositoryRoot, "qml/models/BarStatusModel.js");

function loadModel() {
  assert.equal(existsSync(modelPath), true, "Todo 24 bar status model must exist");
  const context = vm.createContext({ Array, Math, Number, Object, String });
  vm.runInContext(readFileSync(modelPath, "utf8").replace(".pragma library", ""), context, { filename: modelPath });
  return context;
}

function source(name, status = "ok") {
  return { source: name, status, provenance: status === "stale" ? "last_good" : "live" };
}

function snapshot(summary, sourceStatuses = {}) {
  return {
    payload: {
      summary,
      sources: ["security", "omarchy", "arch", "aur", "flatpak", "mise"].map((name) => source(name, sourceStatuses[name])),
      findings: Array.from({ length: summary.securityFindings || 0 }, (_, index) => ({
        findings: [{
          severity: index % 2 === 0 ? "high" : "critical",
          fixedVersion: "1.2.3",
          status: "Fixed",
        }],
      })),
    },
  };
}

test("selects the five bar states from one precedence seam while retaining simultaneous counts", () => {
  const model = loadModel();
  const cases = [
    {
      name: "security",
      document: snapshot({ securityFindings: 2, watchedUpdates: 3, totalUpdates: 7, degradedSources: 1 }, { arch: "stale" }),
      kind: "security",
      glyph: "!",
      badge: "2",
      active: true,
      stale: true,
    },
    {
      name: "watched",
      document: snapshot({ securityFindings: 0, watchedUpdates: 3, totalUpdates: 7, degradedSources: 1 }),
      kind: "watched",
      glyph: "*",
      badge: "3",
      active: false,
      stale: false,
    },
    {
      name: "updates",
      document: snapshot({ securityFindings: 0, watchedUpdates: 0, totalUpdates: 7, degradedSources: 1 }),
      kind: "updates",
      glyph: "^",
      badge: "7",
      active: false,
      stale: false,
    },
    {
      name: "degraded",
      document: snapshot({ securityFindings: 0, watchedUpdates: 0, totalUpdates: 0, degradedSources: 1 }, { arch: "stale" }),
      kind: "degraded",
      glyph: "~",
      badge: "1",
      active: false,
      stale: true,
    },
    {
      name: "clear",
      document: snapshot({ securityFindings: 0, watchedUpdates: 0, totalUpdates: 0, degradedSources: 0 }),
      kind: "clear",
      glyph: "O",
      badge: "",
      active: false,
      stale: false,
    },
  ];

  for (const fixture of cases) {
    const view = model.status(fixture.document, false, true);
    assert.equal(view.kind, fixture.kind, fixture.name);
    assert.equal(view.glyph, fixture.glyph, fixture.name);
    assert.equal(view.badge, fixture.badge, fixture.name);
    assert.equal(view.active, fixture.active, fixture.name);
    assert.equal(view.stale, fixture.stale, fixture.name);
    if (fixture.stale) assert.match(view.label, /~/, fixture.name);
    assert.match(view.tooltip, /watched updates/);
    assert.match(view.tooltip, /other updates/);
  }
});

test("marks refresh activity without replacing the selected state and exposes unavailable service truthfully", () => {
  const model = loadModel();
  const updates = snapshot({ securityFindings: 0, watchedUpdates: 0, totalUpdates: 2, degradedSources: 0 });

  const refreshing = model.status(updates, true, true);
  assert.equal(refreshing.kind, "updates");
  assert.equal(refreshing.spinner, true);
  assert.equal(refreshing.label, "^2 …");

  const unavailable = model.status(null, false, false);
  assert.equal(unavailable.kind, "unavailable");
  assert.equal(unavailable.glyph, "?");
  assert.equal(unavailable.badge, "");
  assert.match(unavailable.tooltip, /service unavailable/);
});

test("selects security only for high or critical findings with an available fix and Fixed status", () => {
  const model = loadModel();
  const noFix = snapshot({ securityFindings: 1, watchedUpdates: 2, totalUpdates: 2, degradedSources: 0 });
  noFix.payload.findings[0].findings[0].fixedVersion = null;
  const notFixed = snapshot({ securityFindings: 1, watchedUpdates: 2, totalUpdates: 2, degradedSources: 0 });
  notFixed.payload.findings[0].findings[0].status = "Vulnerable";

  assert.equal(model.status(noFix, false, true).kind, "watched");
  assert.equal(model.status(notFixed, false, true).kind, "watched");
  assert.equal(model.status(snapshot({ securityFindings: 1, watchedUpdates: 2, totalUpdates: 2, degradedSources: 0 }), false, true).kind, "security");
});

test("does not elevate optional source failures to a mandatory-source degradation", () => {
  const model = loadModel();
  const document = snapshot(
    { securityFindings: 0, watchedUpdates: 0, totalUpdates: 0, degradedSources: 1 },
    { aur: "offline" },
  );

  assert.equal(model.status(document, false, true).kind, "clear");
  document.payload.sources.find((entry) => entry.source === "arch").status = "offline";
  assert.equal(model.status(document, false, true).kind, "degraded");
});
