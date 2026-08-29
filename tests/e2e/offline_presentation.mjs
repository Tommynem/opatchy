import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import vm from "node:vm";

const root = resolve(import.meta.dirname, "../..");
const modelPath = (name) => resolve(root, "qml/models", name);
const raw = readFileSync(0, "utf8");

function context() {
  return vm.createContext({ Array, Date, JSON, Math, Number, Object, RegExp, String });
}

function load(path, target) {
  const value = context();
  vm.runInContext(readFileSync(path, "utf8").replace(".pragma library", ""), value, { filename: path });
  return value[target];
}

function loadController() {
  const value = context();
  const validationPath = modelPath("RequestValidation.js");
  vm.runInContext(readFileSync(validationPath, "utf8").replace(".pragma library", ""), value, { filename: validationPath });
  value.RequestValidation = {
    hasSecurityWatchRequest: value.hasSecurityWatchRequest,
    operationIdentity: value.operationIdentity,
    validInventoryRequest: value.validInventoryRequest,
    validStarRequest: value.validStarRequest,
  };
  const source = readFileSync(modelPath("ServiceController.js"), "utf8")
    .replace(".pragma library", "")
    .replace('.import "RequestValidation.js" as RequestValidation', "");
  vm.runInContext(source, value, { filename: modelPath("ServiceController.js") });
  return value.createController;
}

function validator() {
  const value = context();
  vm.runInContext(readFileSync(modelPath("StrictJson.js"), "utf8").replace(".pragma library", ""), value);
  value.StrictJson = { hasDuplicateObjectKey: value.hasDuplicateObjectKey };
  const source = readFileSync(modelPath("ProtocolValidator.js"), "utf8")
    .replace(".pragma library", "")
    .replace('.import "StrictJson.js" as StrictJson', "");
  vm.runInContext(source, value, { filename: modelPath("ProtocolValidator.js") });
  return value.parseResponse;
}

const parseResponse = validator();
const parsed = parseResponse(raw);
if (process.argv.includes("--reject")) {
  assert.equal(parsed.ok, false);
  process.exit(0);
}

assert.equal(parsed.ok, true, parsed.error);
const createController = loadController();
const updateRows = load(modelPath("UpdateViewModel.js"), "updateRows");
const securityView = load(modelPath("SecurityViewModel.js"), "securityView");
const started = [];
const controller = createController({
  now: () => Date.parse("2026-08-26T12:00:00.000Z"),
  random: () => 0,
  refreshIntervalMs: 60_000,
  onStart: (operation) => started.push(operation),
  onState: () => {},
  onResponse: () => {},
  parseResponse,
});
controller.start();
controller.complete(started[0].id, { exitCode: 0, outputTooLarge: false, stdout: raw, timedOut: false });
assert.equal(controller.state.lastSnapshot.generationId, parsed.value.generationId);
assert.ok(Array.isArray(updateRows(controller.state.lastSnapshot, "System")));
assert.ok(["clean", "findings", "last_known", "unknown"].includes(securityView(controller.state.lastSnapshot, Date.parse("2026-08-26T12:00:00.000Z")).kind));
