import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const repositoryRoot = resolve(import.meta.dirname, "../..");
const modelPath = resolve(repositoryRoot, "qml/models/UpdateViewModel.js");

function loadModel() {
  assert.equal(existsSync(modelPath), true, "Todo 21 update view model must exist");
  const context = vm.createContext({ Array, Math, Number, Object, String });
  vm.runInContext(readFileSync(modelPath, "utf8").replace(".pragma library", ""), context, { filename: modelPath });
  return context;
}

function item(id, source, label, overrides = {}) {
  return {
    id,
    source,
    label,
    installed: "1.0",
    candidate: "1.1",
    watchMode: "off",
    watchable: true,
    provenance: "live",
    ...overrides,
  };
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

function snapshot(items = [], overrides = {}) {
  return {
    generatedAt: "2026-08-26T00:00:00.000Z",
    generationId: "generation-current",
    payload: {
      sources: [source("omarchy"), source("arch"), source("aur"), source("flatpak", {
        scopes: [
          { scope: "user", status: "ok", provenance: "live" },
          { scope: "system", status: "ok", provenance: "live" },
        ],
      }), source("mise")],
      items,
    },
    ...overrides,
  };
}

test("lists only actionable updates for each non-Security tab and labels non-watchable Omarchy rows", () => {
  const model = loadModel();
  const document = snapshot([
    item("omarchy:dev", "omarchy", "Omarchy development checkout", { watchable: false }),
    item("arch:shared", "arch", "Shared"),
    item("aur:shared", "aur", "Shared"),
    item("flatpak:user:org.example.App", "flatpak", "Example App"),
    item("mise:node", "mise", "node"),
  ]);

  assert.deepEqual(JSON.parse(JSON.stringify(model.updateRows(document, "System").map((row) => row.id))), ["arch:shared"]);
  assert.equal(model.updateRows(document, "Omarchy")[0].watchText, "Watch: unavailable");
  assert.equal(model.updateRows(document, "Security").length, 0);
  assert.equal(model.canBrowse("Omarchy"), false);
  assert.equal(model.canBrowse("System"), true);
});

test("builds fixed page-size requests with bounded Unicode queries and deterministic pages", () => {
  const model = loadModel();
  const request = model.inventoryRequest("System", "STRASSE \u041a\u043b\u044e\u0447", 200);

  assert.deepEqual(JSON.parse(JSON.stringify(request)), {
    source: "arch", query: "STRASSE \u041a\u043b\u044e\u0447", limit: 100, offset: 200,
  });
  assert.equal(model.inventoryRequest("Omarchy", "query", 0), null);
  assert.equal(model.inventoryRequest("AUR", "x".repeat(129), 0).query.length, 128);
});

test("reports empty, one, many, and over-page inventory results without conflating duplicate labels", () => {
  const model = loadModel();
  const response = (total, items) => ({
    generationId: "generation-current",
    payload: { source: "arch", total, items },
  });

  assert.equal(model.inventoryState(response(0, []), "arch", "generation-current").summaryText, "No cached packages match this query.");
  assert.equal(model.inventoryState(response(1, [item("arch:one", "arch", "one")]), "arch", "generation-current").summaryText, "1 cached result.");
  assert.equal(model.inventoryState(response(2, [item("arch:a", "arch", "same"), item("arch:b", "arch", "same")]), "arch", "generation-current").summaryText, "2 cached results.");
  assert.equal(model.inventoryState(response(101, [item("arch:a", "arch", "same")]), "arch", "generation-current").summaryText, "101 cached results.");
  assert.deepEqual(JSON.parse(JSON.stringify(model.inventoryState(response(2, [item("arch:a", "arch", "same"), item("arch:b", "arch", "same")]), "arch", "generation-current").rows.map((row) => row.identity))), ["arch:arch:a", "arch:arch:b"]);
});

test("retains a current inventory view when stale or incompatible results arrive", () => {
  const model = loadModel();
  const current = { generationId: "generation-current", payload: { source: "arch", total: 1, items: [item("arch:current", "arch", "current")] } };
  const stale = { generationId: "generation-old", payload: { source: "arch", total: 1, items: [item("arch:old", "arch", "old")] } };

  assert.equal(model.inventoryState(stale, "arch", "generation-current").kind, "stale");
  assert.equal(model.acceptInventory(current, stale, "arch", "generation-current").payload.items[0].id, "arch:current");
  assert.equal(model.inventoryState({ generationId: "generation-current", payload: { source: "aur", total: 0, items: [] } }, "arch", "generation-current").kind, "incompatible");
});

test("builds only eligible fixed footer actions, including independently scoped Flatpak actions", () => {
  const model = loadModel();
  const document = snapshot([
    item("arch:system", "arch", "system"),
    item("flatpak:user:app", "flatpak", "user app"),
    item("flatpak:system:runtime", "flatpak", "system runtime"),
  ]);

  const system = model.footerActions(document, "System", { canOpenOmarchyUpdate: true });
  assert.deepEqual(JSON.parse(JSON.stringify(system)), [{ kind: "omarchy", text: "Open update terminal", enabled: true }]);
  const flatpak = model.footerActions(document, "Flatpak", {
    canOpenFlatpakUserUpdate: true,
    canOpenFlatpakSystemUpdate: false,
  });
  assert.deepEqual(JSON.parse(JSON.stringify(flatpak)), [
    { kind: "flatpak-user", text: "Open update terminal (user)", enabled: true },
    { kind: "flatpak-system", text: "Open update terminal (system)", enabled: false },
  ]);
  assert.equal(model.footerActions(snapshot([], {}), "AUR", { canOpenOmarchyUpdate: true })[0].enabled, false);
});

test("renders source content through plain text and dispatches only fixed service actions", () => {
  const source = readFileSync(resolve(repositoryRoot, "qml/components/SourceContent.qml"), "utf8");
  const row = readFileSync(resolve(repositoryRoot, "qml/components/UpdateRow.qml"), "utf8");

  assert.match(row, /textFormat:\s*Text\.PlainText/g);
  assert.match(source, /case "omarchy": service\.openOmarchyUpdate\(\); break/);
  assert.match(source, /case "flatpak-user": service\.openFlatpakUserUpdate\(\); break/);
  assert.match(source, /case "flatpak-system": service\.openFlatpakSystemUpdate\(\); break/);
  assert.doesNotMatch(source, /setStar|openAction\(|requestRefresh\(/);
});

test("normalizes hostile presentation strings to one bounded plain-text line", () => {
  const model = loadModel();
  const hostile = "$(touch /tmp/opatchy-injection-sentinel)\n\u202e\u4f60\u597d \u0645\u0631\u062d\u0628\u0627\u0000" + "x".repeat(2_000);
  const value = model.presentationText(hostile);

  assert.equal(value.includes("\n"), false);
  assert.equal(value.includes("\u0000"), false);
  assert.ok(value.length <= 256);
  assert.match(value, /opatchy-injection-sentinel/);
});
