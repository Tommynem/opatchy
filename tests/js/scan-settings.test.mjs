import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const repositoryRoot = resolve(import.meta.dirname, "../..");
const settingsPath = resolve(repositoryRoot, "qml/models/ScanSettings.js");
const servicePath = resolve(repositoryRoot, "Service.qml");

function scanArguments(settings) {
  const context = vm.createContext({ Object, String });
  const source = readFileSync(settingsPath, "utf8").replace(".pragma library", "");
  vm.runInContext(source, context, { filename: settingsPath });
  return JSON.parse(JSON.stringify(context.scanArguments(settings)));
}

test("Service scan settings use manifest defaults when settings are absent", () => {
  assert.deepEqual(scanArguments({}), [
    "--notify-permanent", "true",
    "--notify-security", "true",
    "--security-minimum-severity", "high",
    "--enable-cisa-kev", "true",
  ]);
});

test("Service scan settings preserve changed manifest values in closed argv order", () => {
  assert.deepEqual(scanArguments({
    notifyPermanent: false,
    notifySecurity: false,
    securityMinimumSeverity: "critical",
    enableCisaKev: false,
  }), [
    "--notify-permanent", "false",
    "--notify-security", "false",
    "--security-minimum-severity", "critical",
    "--enable-cisa-kev", "false",
  ]);
  assert.match(
    readFileSync(servicePath, "utf8"),
    /scanArguments:\s*function\(\)\s*\{\s*return ScanSettings\.scanArguments\(root\.settings\)\s*\}/,
  );
});
