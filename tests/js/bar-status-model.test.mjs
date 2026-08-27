import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const repositoryRoot = resolve(import.meta.dirname, "../..");
const modelPath = resolve(repositoryRoot, "qml/models/BarStatusModel.js");
const iconPath = resolve(repositoryRoot, "qml/components/BarStatusIcon.qml");
const barWidgetPath = resolve(repositoryRoot, "BarWidget.qml");
const contextCapturePath = resolve(repositoryRoot, "tests/qml/BarStatusContextCapture.qml");
const contextCaptureScriptPath = resolve(repositoryRoot, "scripts/capture_bar_status_context.sh");

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
      icon: "shield",
      badge: "2",
      active: true,
      stale: true,
    },
    {
      name: "watched",
      document: snapshot({ securityFindings: 0, watchedUpdates: 3, totalUpdates: 7, degradedSources: 1 }),
      kind: "watched",
      glyph: "*",
      icon: "bookmark",
      badge: "3",
      active: false,
      stale: false,
    },
    {
      name: "updates",
      document: snapshot({ securityFindings: 0, watchedUpdates: 0, totalUpdates: 7, degradedSources: 1 }),
      kind: "updates",
      glyph: "^",
      icon: "update",
      badge: "7",
      active: false,
      stale: false,
    },
    {
      name: "degraded",
      document: snapshot({ securityFindings: 0, watchedUpdates: 0, totalUpdates: 0, degradedSources: 1 }, { arch: "stale" }),
      kind: "degraded",
      glyph: "~",
      icon: "warning",
      badge: "1",
      active: false,
      stale: true,
    },
    {
      name: "clear",
      document: snapshot({ securityFindings: 0, watchedUpdates: 0, totalUpdates: 0, degradedSources: 0 }),
      kind: "clear",
      glyph: "O",
      icon: "check",
      badge: "",
      active: false,
      stale: false,
    },
  ];

  for (const fixture of cases) {
    const view = model.status(fixture.document, false, true);
    assert.equal(view.kind, fixture.kind, fixture.name);
    assert.equal(view.glyph, fixture.glyph, fixture.name);
    assert.equal(view.icon, fixture.icon, fixture.name);
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

test("reserves the urgent token for the actionable-security shield", () => {
  const iconSource = readFileSync(iconPath, "utf8");

  assert.equal([...iconSource.matchAll(/root\.urgent/g)].length, 1);
  assert.match(iconSource, /icon === "shield" \? root\.urgent : root\.foreground/);
});

test("uses host-scale MDI glyphs without custom status geometry", () => {
  const iconSource = readFileSync(iconPath, "utf8");
  const barWidgetSource = readFileSync(barWidgetPath, "utf8");
  const contextCaptureSource = readFileSync(contextCapturePath, "utf8");
  const contextCaptureScript = readFileSync(contextCaptureScriptPath, "utf8");
  const retiredShieldGlyph = String.fromCodePoint(984421);
  const staleGlyph = String.fromCodePoint(0xf0150);
  const refreshGlyph = String.fromCodePoint(0xf0450);
  const glyphs = [
    ["shield", "󰻌", "f0ecc"],
    ["bookmark", "󰃀", "f00c0"],
    ["update", "󰏖", "f03d6"],
    ["warning", "󰀦", "f0026"],
    ["check", "󰗠", "f05e0"],
  ];

  assert.doesNotMatch(iconSource, /QtQuick\.Shapes|\b(?:Canvas|Shape|ShapePath|Path|PathLine|Rectangle|Image)\b/);
  assert.doesNotMatch(iconSource, new RegExp(retiredShieldGlyph));
  for (const [icon, glyph, codepoint] of glyphs) {
    assert.equal(glyph.codePointAt(0).toString(16), codepoint);
    if (icon === "check") assert.match(iconSource, new RegExp(`return "${glyph}"`));
    else assert.match(iconSource, new RegExp(`currentIcon === "${icon}".*return "${glyph}"`));
  }
  assert.match(iconSource, /renderType: Text\.NativeRendering/);
  assert.match(iconSource, new RegExp(`text: "${staleGlyph}"`));
  assert.match(iconSource, new RegExp(`text: "${refreshGlyph}"`));
  assert.match(iconSource, /readonly property real secondaryFontSize: Math\.max\(9, Math\.round\(root\.fontSize \* \.69\)\)/);
  assert.match(iconSource, /running: root\.refreshing && !root\.reducedMotion/);
  assert.match(barWidgetSource, /fontFamily: button\.fontFamily/);
  assert.match(barWidgetSource, /fontSize: button\.fontSize/);
  assert.match(barWidgetSource, /reducedMotion: root\.settings && root\.settings\.reducedMotion === true/);
  assert.doesNotMatch(contextCaptureSource, /text: "Opatchy"/);
  assert.match(contextCaptureSource, /fontFamily: root\.productionIconFont/);
  assert.match(contextCaptureSource, /property string productionIconFont: "monospace"/);
  assert.match(contextCaptureSource, /name: "security-stale-dark-horizontal", state: "security", dark: true, vertical: false, stale: true/);
  assert.match(contextCaptureSource, /name: "security-refresh-dark-horizontal", state: "security", dark: true, vertical: false, refreshing: true/);
  assert.match(contextCaptureSource, /name: "security-stale-refresh-dark-horizontal", state: "security", dark: true, vertical: false, stale: true, refreshing: true/);
  assert.match(contextCaptureSource, /name: "security-stale-refresh-transparent-horizontal", state: "security", transparent: true, vertical: false, stale: true, refreshing: true/);
  assert.match(contextCaptureSource, /snapshot\(currentFixture\.state, currentFixture\.stale === true\)/);
  assert.match(contextCaptureScript, /context\.sha256/);
  assert.match(contextCaptureScript, /\*transparent\*\.png/);
  assert.match(contextCaptureScript, /expected transparent pixels/);
  assert.match(contextCaptureScript, /sha256sum .*BarStatusIcon\.qml.*BarStatusPresentation\.qml.*BarStatusModel\.js.*BarStatusContextCapture\.qml/);
  assert.match(contextCaptureSource, /root\.currentFixture\.transparent \? "transparent"/);
  assert.match(contextCaptureSource, /root\.currentFixture\.transparent \? "#cc343a46"/);
});

test("keeps one-digit badges legible and separated from the primary glyph", () => {
  const iconSource = readFileSync(iconPath, "utf8");

  assert.match(iconSource, /readonly property real badgeFontSize: Math\.max\(9, root\.fontSize \* \.69\)/);
  assert.match(iconSource, /anchors\.rightMargin: -4\.5/);
  assert.match(iconSource, /anchors\.bottomMargin: -4\.5/);
  assert.match(iconSource, /font\.pixelSize: root\.badgeFontSize/);
});
