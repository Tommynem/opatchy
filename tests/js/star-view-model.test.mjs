import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const repositoryRoot = resolve(import.meta.dirname, "../..");
const modelPath = resolve(repositoryRoot, "qml/models/StarViewModel.js");

function loadModel() {
  assert.equal(existsSync(modelPath), true, "Todo 23 star view model must exist");
  const context = vm.createContext({ Array, Object, String });
  vm.runInContext(readFileSync(modelPath, "utf8").replace(".pragma library", ""), context, { filename: modelPath });
  return context;
}

test("maps each watch mode to one explicit next mode and distinct accessible presentation", () => {
  const model = loadModel();
  const cases = [
    ["off", "temporary", "Not watched"],
    ["temporary", "permanent", "Watching until one observed update installs"],
    ["permanent", "off", "Watching permanently with notifications"],
  ];

  for (const [mode, nextMode, label] of cases) {
    const presentation = model.presentation(mode, true, true, false);
    assert.equal(presentation.mode, mode);
    assert.equal(presentation.nextMode, nextMode);
    assert.equal(presentation.label, label);
    assert.notEqual(presentation.glyph, "");
    assert.notEqual(presentation.tooltip, "");
    assert.notEqual(presentation.accessibleName, "");
  }
});

test("explains disabled permanent notifications and never arms an unavailable off row", () => {
  const model = loadModel();

  assert.match(model.presentation("permanent", false, false, false).label, /notifications disabled in settings/i);
  const unavailable = model.presentation("off", true, false, false);
  assert.equal(unavailable.enabled, false);
  assert.equal(unavailable.nextMode, null);
  assert.match(model.presentation("temporary", true, true, true).label, /last-known/i);
});

test("builds a watched source view from validated rows including permanent missing inventory", () => {
  const model = loadModel();
  const watched = model.watchedRows([
    { target: "arch:temporary", watchMode: "temporary", watchable: true, label: "Temporary" },
    { target: "arch:missing", watchMode: "permanent", watchable: false, label: "Missing" },
    { target: "arch:off", watchMode: "off", watchable: true, label: "Off" },
  ]);

  assert.deepEqual(JSON.parse(JSON.stringify(watched.map((row) => row.target))), ["arch:temporary", "arch:missing"]);
  assert.equal(watched[1].missing, true);
});
