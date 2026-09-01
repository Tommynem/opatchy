import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const repositoryRoot = resolve(import.meta.dirname, "../..");
const controllerPath = resolve(repositoryRoot, "qml/models/ServiceController.js");
const requestValidationPath = resolve(repositoryRoot, "qml/models/RequestValidation.js");
const strictJsonPath = resolve(repositoryRoot, "qml/models/StrictJson.js");
const validatorPath = resolve(repositoryRoot, "qml/models/ProtocolValidator.js");

function loadController() {
  const context = vm.createContext({ JSON, Math, Number, Object, String });
  const requestValidation = readFileSync(requestValidationPath, "utf8").replace(".pragma library", "");
  vm.runInContext(requestValidation, context, { filename: requestValidationPath });
  context.RequestValidation = {
    hasSecurityWatchRequest: context.hasSecurityWatchRequest,
    operationIdentity: context.operationIdentity,
    validInventoryRequest: context.validInventoryRequest,
    validStarRequest: context.validStarRequest,
  };
  const source = readFileSync(controllerPath, "utf8")
    .replace(".pragma library", "")
    .replace('.import "RequestValidation.js" as RequestValidation', "");
  vm.runInContext(source, context, { filename: controllerPath });
  return context.createController;
}

function loadValidator() {
  const context = vm.createContext({ JSON, Math, Number, Object, String });
  const strictJson = readFileSync(strictJsonPath, "utf8").replace(".pragma library", "");
  vm.runInContext(strictJson, context, { filename: strictJsonPath });
  context.StrictJson = { hasDuplicateObjectKey: context.hasDuplicateObjectKey };
  const source = readFileSync(validatorPath, "utf8")
    .replace(".pragma library", "")
    .replace('.import "StrictJson.js" as StrictJson', "");
  vm.runInContext(source, context, { filename: validatorPath });
  return context.parseResponse;
}

function pythonAccepts(raw) {
  const python = process.env.OPATCHY_TEST_PYTHON || "/usr/bin/python3";
  const result = spawnSync(python, ["-c", [
    "import sys",
    "from opatchy_helper.models import ProtocolError",
    "from opatchy_helper.protocol import decode_response",
    "try:",
    "    decode_response(sys.stdin.buffer.read())",
    "except ProtocolError:",
    "    raise SystemExit(1)",
  ].join("\n")], {
    input: raw,
    encoding: "utf8",
    env: { ...process.env, PYTHONPATH: resolve(repositoryRoot, "helper") },
  });
  return result.status === 0;
}

function source(name, freshUntil) {
  const health = {
    source: name,
    status: "ok",
    provenance: "live",
    observedAt: "2026-08-26T00:00:00.000Z",
    freshUntil,
    cause: null,
  };
  if (name === "flatpak") {
    health.scopes = ["user", "system"].map((scope) => ({
      scope,
      status: "ok",
      provenance: "live",
      observedAt: "2026-08-26T00:00:00.000Z",
      freshUntil,
      cause: null,
    }));
  }
  return health;
}

function snapshotDocument(generationId, freshUntil = "2026-08-26T00:05:00.000Z") {
  return {
    protocolVersion: 1,
    kind: "snapshot",
    generatedAt: "2026-08-26T00:00:00.000Z",
    generationId,
    payload: {
      scanState: "complete",
      sources: ["security", "cisa-kev", "omarchy", "arch", "aur", "flatpak", "mise"].map(
        (name) => source(name, freshUntil),
      ),
      summary: {
        totalUpdates: 1,
        watchedUpdates: 0,
        securityFindings: 1,
        degradedSources: 0,
      },
      items: [{
        id: "arch:demo",
        source: "arch",
        label: "demo",
        installed: "1.0",
        candidate: "2.0",
        watchMode: "off",
        watchArmed: false,
        watchable: true,
        provenance: "live",
      }],
      findings: [{
        itemId: "arch:demo",
        findings: [{
          id: "AVG-1",
          itemId: "arch:demo",
          advisoryId: "AVG-1",
          cveIds: ["CVE-2026-0001"],
          severity: "high",
          fixedVersion: "2.0",
          installedVersion: "1.0",
          knownExploited: false,
          kevStatus: "unavailable",
          kevProvenance: null,
          provenance: "live",
          status: "Fixed",
          type: "security",
        }],
      }],
      notifications: [{ fingerprint: "watch:arch:demo", status: "delivered" }],
    },
  };
}

function snapshot(generationId, freshUntil) {
  return JSON.stringify(snapshotDocument(generationId, freshUntil));
}

function invalidSnapshot(mutate) {
  const document = snapshotDocument("invalid");
  mutate(document);
  return JSON.stringify(document);
}

function inventory(generationId) {
  return JSON.stringify({
    protocolVersion: 1,
    kind: "inventory",
    generatedAt: "2026-08-26T00:00:00.000Z",
    generationId,
    payload: { source: "arch", total: 0, items: [] },
  });
}

function starResult(generationId) {
  return JSON.stringify({
    protocolVersion: 1,
    kind: "star-result",
    generatedAt: "2026-08-26T00:00:00.000Z",
    generationId,
    payload: { itemId: "arch:demo", mode: "temporary", watchArmed: true },
  });
}

function helperError(generationId) {
  return JSON.stringify({
    protocolVersion: 1,
    kind: "error",
    generatedAt: "2026-08-26T00:00:00.000Z",
    generationId,
    error: { code: "STATE_UNAVAILABLE", message: "validated state is unavailable" },
  });
}

function fixture(now = 0, scanArguments) {
  const starts = [];
  const states = [];
  const options = {
    now: () => now,
    random: () => 0,
    refreshIntervalMs: 60_000,
    onStart: (operation) => starts.push(operation),
    onState: (state) => states.push(state),
    onResponse: () => {},
    parseResponse: loadValidator(),
  };
  if (scanArguments !== undefined) options.scanArguments = scanArguments;
  const controller = loadController()(options);
  return { controller, starts, states };
}

test("includes Service scan settings in forced and scheduled helper argv", () => {
  const settings = [
    "--notify-permanent", "false",
    "--notify-security", "false",
    "--security-minimum-severity", "critical",
    "--enable-cisa-kev", "false",
  ];
  const { controller, starts } = fixture(0, settings);
  controller.start();
  complete(controller, starts[0], snapshot("settings"));

  controller.requestRefresh();
  const forced = starts[1];
  complete(controller, forced, snapshot("settings-forced"));
  controller.wake(60_000);

  assert.deepEqual(JSON.parse(JSON.stringify(starts.slice(1).map((operation) => operation.argv))), [
    ["scan", "--force", ...settings],
    ["scan", ...settings],
  ]);
});

test("resolves scan settings when each scan is queued", () => {
  let settings = ["--enable-cisa-kev", "true"];
  const { controller, starts } = fixture(0, () => settings);
  controller.start();
  complete(controller, starts[0], snapshot("initial"));

  settings = ["--enable-cisa-kev", "false"];
  controller.requestRefresh();
  settings[1] = "true";

  assert.deepEqual(JSON.parse(JSON.stringify(starts[1].argv)), [
    "scan", "--force", "--enable-cisa-kev", "false",
  ]);
});

test("uses copied array scan settings for the enqueued operation", () => {
  const settings = ["--enable-cisa-kev", "false"];
  const { controller, starts } = fixture(0, settings);
  controller.start();
  complete(controller, starts[0], snapshot("array-settings"));

  controller.requestRefresh();
  settings[1] = "true";

  assert.deepEqual(JSON.parse(JSON.stringify(starts[1].argv)), [
    "scan", "--force", "--enable-cisa-kev", "false",
  ]);
});

test("uses legacy scan argv when settings are absent or invalid", () => {
  const providers = [undefined, null, "invalid", () => "invalid"];

  for (const provider of providers) {
    const { controller, starts } = fixture(0, provider);
    controller.start();
    complete(controller, starts[0], snapshot("legacy"));
    controller.requestRefresh();

    assert.deepEqual(JSON.parse(JSON.stringify(starts[1].argv)), ["scan", "--force"]);
  }
});

function complete(controller, operation, stdout, result = {}) {
  controller.complete(operation.id, {
    exitCode: 0,
    stdout,
    stderr: "",
    timedOut: false,
    outputTooLarge: false,
    ...result,
  });
}

test("Service lifecycle trusts only the injected source directory and owns valid state", () => {
  const service = readFileSync(resolve(repositoryRoot, "Service.qml"), "utf8");

  assert.match(service, /manifest\.__sourceDir/);
  assert.doesNotMatch(service, /Qt\.createComponent|ensureService/);
  assert.match(service, /readonly property var lastSnapshot/);
});

test("rejects duplicate JSON keys with Python decoder parity", () => {
  const parseResponse = loadValidator();
  const base = '"kind":"error","generatedAt":"2026-08-26T00:00:00.000Z","generationId":"generation","error":{"code":"STATE_UNAVAILABLE","message":"x"}';
  const cases = [
    `{"protocolVersion":1,"protocolVersion":1,${base}}`,
    `{"protocolVersion":1,${base.replace('"code":"STATE_UNAVAILABLE"', '"code":"STATE_UNAVAILABLE","code":"STATE_UNAVAILABLE"')}}`,
    `{"protocolVersion":1,"kind":"error","generatedAt":"2026-08-26T00:00:00.000Z","generationId":"generation","error":{"code":"STATE_UNAVAILABLE","message":"x","\\u006dessage":"x"}}`,
    `{"protocolVersion":1,"kind":"error","generatedAt":"2026-08-26T00:00:00.000Z","generationId":"\\uD800","error":{"code":"STATE_UNAVAILABLE","message":"x"}}`,
    `{"protocolVersion":1,"kind":"error","generatedAt":"2026-08-26T00:00:00.000Z","generationId":"\\uDC00","error":{"code":"STATE_UNAVAILABLE","message":"x"}}`,
  ];
  const validEscapes = '{"protocolVersion":1,"kind":"error","generatedAt":"2026-08-26T00:00:00.000Z","generation\\u0049d":"\\u0067eneration","error":{"code":"STATE_UNAVAILABLE","message":"quote: \\" slash: \\/ unicode: \\uD83D\\uDE00"}}';
  const literalUnpairedHigh = `{"protocolVersion":1,"kind":"error","generatedAt":"2026-08-26T00:00:00.000Z","generationId":"${String.fromCharCode(0xD800)}","error":{"code":"STATE_UNAVAILABLE","message":"x"}}`;
  const literalUnpairedLow = `{"protocolVersion":1,"kind":"error","generatedAt":"2026-08-26T00:00:00.000Z","generationId":"${String.fromCharCode(0xDC00)}","error":{"code":"STATE_UNAVAILABLE","message":"x"}}`;

  for (const raw of cases) {
    assert.equal(parseResponse(raw).ok, pythonAccepts(raw), raw);
    assert.equal(parseResponse(raw).ok, false, raw);
  }
  assert.equal(parseResponse(validEscapes).ok, pythonAccepts(validEscapes));
  assert.equal(parseResponse(validEscapes).ok, true);
  assert.equal(parseResponse(literalUnpairedHigh).ok, false);
  assert.equal(parseResponse(literalUnpairedLow).ok, false);
});

test("coalesces repeated manual refreshes into one forced follow-up", () => {
  const { controller, starts } = fixture();
  controller.start();
  const initial = starts[0];

  assert.equal(controller.requestRefresh(), true);
  assert.equal(controller.requestRefresh(), false);
  assert.equal(controller.requestRefresh(), false);
  complete(controller, initial, snapshot("generation-1"));

  assert.deepEqual(JSON.parse(JSON.stringify(starts.map((operation) => operation.argv))), [
    ["snapshot"],
    ["scan", "--force"],
  ]);
  const scan = starts[1];
  assert.equal(controller.requestRefresh(), true);
  assert.equal(controller.requestRefresh(), false);
  assert.equal(controller.requestRefresh(), false);
  complete(controller, scan, snapshot("generation-2"));

  assert.deepEqual(JSON.parse(JSON.stringify(starts.map((operation) => operation.argv))), [
    ["snapshot"],
    ["scan", "--force"],
    ["scan", "--force"],
  ]);
});

test("upgrades an ordinary queued refresh to force and never downgrades a manual one", () => {
  const freshUntil = "1970-01-01T00:05:00.000Z";
  const ordinaryThenManual = fixture();
  ordinaryThenManual.controller.start();
  complete(ordinaryThenManual.controller, ordinaryThenManual.starts[0], snapshot("ordinary", freshUntil));
  ordinaryThenManual.controller.requestInventory({ source: "arch", query: "", limit: 20, offset: 0 });
  const ordinaryThenManualInventory = ordinaryThenManual.starts[1];
  ordinaryThenManual.controller.wake(300_000);
  assert.equal(ordinaryThenManual.controller.requestRefresh(), false);
  complete(ordinaryThenManual.controller, ordinaryThenManualInventory, inventory("ordinary-inventory"));

  assert.deepEqual(JSON.parse(JSON.stringify(ordinaryThenManual.starts.map((operation) => operation.argv))), [
    ["snapshot"],
    ["inventory", "--source", "arch", "--query", "", "--limit", "20", "--offset", "0"],
    ["scan", "--force"],
  ]);

  const manualThenOrdinary = fixture();
  manualThenOrdinary.controller.start();
  complete(manualThenOrdinary.controller, manualThenOrdinary.starts[0], snapshot("manual", freshUntil));
  manualThenOrdinary.controller.requestInventory({ source: "arch", query: "", limit: 20, offset: 0 });
  const manualThenOrdinaryInventory = manualThenOrdinary.starts[1];
  assert.equal(manualThenOrdinary.controller.requestRefresh(), true);
  manualThenOrdinary.controller.wake(300_000);
  complete(manualThenOrdinary.controller, manualThenOrdinaryInventory, inventory("manual-inventory"));

  assert.deepEqual(JSON.parse(JSON.stringify(manualThenOrdinary.starts.map((operation) => operation.argv))), [
    ["snapshot"],
    ["inventory", "--source", "arch", "--query", "", "--limit", "20", "--offset", "0"],
    ["scan", "--force"],
  ]);
});

test("records only source scans as attempts and uses the snapshot generation time as success", () => {
  const { controller, starts } = fixture(120_000);
  controller.start();
  const cachedSnapshot = starts[0];

  assert.equal(controller.state.lastAttemptAt, null);
  complete(controller, cachedSnapshot, snapshot("cached"));
  assert.equal(controller.state.lastSuccessAt, Date.parse("2026-08-26T00:00:00.000Z"));

  controller.requestRefresh();
  assert.equal(starts[1].kind, "scan");
  assert.equal(controller.state.lastAttemptAt, 120_000);
});

test("reports refreshing only while a source scan is active or queued", () => {
  const { controller, starts } = fixture();
  controller.start();
  assert.equal(controller.state.refreshing, false);
  complete(controller, starts[0], snapshot("initial"));

  controller.requestInventory({ source: "arch", query: "", limit: 20, offset: 0 });
  assert.equal(controller.state.refreshing, false);
  controller.setStar({ itemId: "arch:demo", mode: "temporary" });
  assert.equal(controller.state.refreshing, false);

  complete(controller, starts[1], inventory("inventory"));
  controller.requestRefresh();
  assert.equal(controller.state.refreshing, true);
  complete(controller, starts[2], starResult("star"));
  assert.equal(controller.state.refreshing, true);
  complete(controller, starts[3], snapshot("refreshed"));
  assert.equal(controller.state.refreshing, false);
});

test("preserves FIFO ordering for inventory and set-star operations", () => {
  const { controller, starts } = fixture();
  controller.start();
  complete(controller, starts[0], snapshot("generation-1"));

  controller.requestInventory({ source: "arch", query: "demo", limit: 20, offset: 0 });
  controller.setStar({ itemId: "arch:demo", mode: "temporary" });
  complete(controller, starts[1], inventory("inventory-1"));
  complete(controller, starts[2], starResult("star-1"));

  assert.deepEqual(JSON.parse(JSON.stringify(starts.map((operation) => operation.argv))), [
    ["snapshot"],
    ["inventory", "--source", "arch", "--query", "demo", "--limit", "20", "--offset", "0"],
    ["set-star", "--item-id", "arch:demo", "--mode", "temporary"],
  ]);
});

test("rejects obsolete callbacks after a newer generation is published", () => {
  const { controller, starts } = fixture();
  controller.start();
  const first = starts[0];
  complete(controller, first, snapshot("generation-1"));
  controller.requestRefresh();
  const second = starts[1];
  complete(controller, second, snapshot("generation-2"));
  complete(controller, first, snapshot("generation-0"));

  assert.equal(controller.state.lastSnapshot.generationId, "generation-2");
});

test("keeps last valid state for transport and protocol failures", () => {
  const cases = [
    { name: "malformed JSON", stdout: "{" },
    { name: "future protocol", stdout: snapshot("future").replace('"protocolVersion":1', '"protocolVersion":2') },
    { name: "wrong kind", stdout: inventory("wrong-kind") },
    { name: "nonzero exit", stdout: snapshot("nonzero"), result: { exitCode: 1 } },
    { name: "oversize stdout", stdout: snapshot("oversize"), result: { outputTooLarge: true } },
    { name: "timeout", stdout: snapshot("timeout"), result: { timedOut: true } },
  ];

  for (const failure of cases) {
    const { controller, starts } = fixture();
    controller.start();
    complete(controller, starts[0], snapshot("valid"));
    controller.requestRefresh();
    complete(controller, starts[1], failure.stdout, failure.result);

    assert.equal(controller.state.lastSnapshot.generationId, "valid", failure.name);
    assert.notEqual(controller.state.lastError, "", failure.name);
  }
});

test("rejects every malformed typed snapshot field while retaining the last valid snapshot", () => {
  const cases = [
    ["unknown scan state", (document) => { document.payload.scanState = "unknown"; }],
    ["unknown source", (document) => { document.payload.sources[0].source = "unknown"; }],
    ["unknown source status", (document) => { document.payload.sources[0].status = "unknown"; }],
    ["unknown source provenance", (document) => { document.payload.sources[0].provenance = "unknown"; }],
    ["malformed source scope", (document) => { document.payload.sources[5].scopes[0].scope = "unknown"; }],
    ["malformed source cause", (document) => { document.payload.sources[0].cause = { code: "UNKNOWN", message: "x" }; }],
    ["malformed item", (document) => { document.payload.items[0].watchable = "true"; }],
    ["duplicate item", (document) => { document.payload.items.push({ ...document.payload.items[0] }); }],
    ["malformed finding", (document) => { document.payload.findings[0].findings[0].severity = "unknown-value"; }],
    ["malformed Arch group identity", (document) => { document.payload.findings[0].itemId = "arch:"; }],
    ["dot-prefixed Arch group identity", (document) => { document.payload.findings[0].findings[0].itemId = document.payload.findings[0].itemId = "arch:.hidden"; }],
    ["hyphen-prefixed Arch group identity", (document) => { document.payload.findings[0].findings[0].itemId = document.payload.findings[0].itemId = "arch:-option"; }],
    ["control-character Arch group identity", (document) => { document.payload.findings[0].itemId = "arch:bad\npkg"; }],
    ["whitespace Arch group identity", (document) => { document.payload.findings[0].itemId = "arch:bad pkg"; }],
    ["traversal Arch group identity", (document) => { document.payload.findings[0].itemId = "arch:../pkg"; }],
    ["URL-like Arch group identity", (document) => { document.payload.findings[0].itemId = "arch:https://example.invalid"; }],
    ["oversized Arch group identity", (document) => { document.payload.findings[0].itemId = "arch:" + "a".repeat(124); }],
    ["mismatched finding group identity", (document) => { document.payload.findings[0].findings[0].itemId = "arch:other"; }],
    ["oversized advisory", (document) => { document.payload.findings[0].findings[0].id = document.payload.findings[0].findings[0].advisoryId = "AVG-" + "1".repeat(125); }],
    ["oversized CVE", (document) => { document.payload.findings[0].findings[0].cveIds = ["CVE-2026-" + "1".repeat(20)]; }],
    ["duplicate finding group", (document) => { document.payload.findings.push({ ...document.payload.findings[0] }); }],
    ["duplicate finding", (document) => { document.payload.findings[0].findings.push({ ...document.payload.findings[0].findings[0] }); }],
    ["malformed notification", (document) => { document.payload.notifications[0].status = "unknown"; }],
    ["duplicate notification", (document) => { document.payload.notifications.push({ ...document.payload.notifications[0] }); }],
    ["wrong summary fields", (document) => { document.payload.summary.extra = 1; }],
  ];

  for (const [name, mutate] of cases) {
    const { controller, starts } = fixture();
    controller.start();
    complete(controller, starts[0], snapshot("valid"));
    controller.requestRefresh();
    complete(controller, starts[1], invalidSnapshot(mutate));

    assert.equal(controller.state.lastSnapshot.generationId, "valid", name);
    assert.notEqual(controller.state.lastError, "", name);
  }
});

test("accepts canonical Arch package-name punctuation in security finding groups", () => {
  const parseResponse = loadValidator();

  for (const itemId of ["arch:0ad", "arch:lib32-openssl", "arch:foo.bar", "arch:foo_bar", "arch:foo+bar", "arch:foo@bar"]) {
    const document = snapshotDocument("package-name");
    document.payload.findings[0].itemId = itemId;
    document.payload.findings[0].findings[0].itemId = itemId;
    assert.equal(parseResponse(JSON.stringify(document)).ok, true, itemId);
  }
});

test("rejects helper requests outside the exact CLI bounds", () => {
  const { controller } = fixture();
  const invalidInventoryRequests = [
    { source: "omarchy", query: "", limit: 1, offset: 0 },
    { source: "security", query: "", limit: 1, offset: 0 },
    { source: "arch", query: "", limit: 101, offset: 0 },
    { source: "arch", query: "", limit: 1, offset: 100_001 },
    { source: "arch", query: "x".repeat(129), limit: 1, offset: 0 },
  ];

  for (const request of invalidInventoryRequests) {
    assert.equal(controller.requestInventory(request), false, JSON.stringify(request));
  }
  assert.equal(controller.setStar({ itemId: "x".repeat(129), mode: "temporary" }), false);
  assert.equal(controller.setStar({ itemId: "arch:demo", mode: "unknown" }), false);
});

test("emits exact conditional temporary-watch argv and retains request identity", () => {
  const { controller, starts } = fixture();
  controller.start();
  complete(controller, starts[0], snapshot("generation-1"));

  assert.equal(controller.setStar({
    itemId: "arch:demo",
    mode: "temporary",
    securityAdvisory: "AVG-20260001",
    fixedVersion: "2.0-1",
    cveIds: ["CVE-2026-1001", "CVE-2026-1000"],
  }), true);

  assert.deepEqual(JSON.parse(JSON.stringify(starts[1])), {
    id: starts[1].id,
    kind: "set-star",
    argv: [
      "set-star", "--item-id", "arch:demo", "--mode", "temporary",
      "--security-advisory", "AVG-20260001", "--fixed-version", "2.0-1",
      "--cve-ids", "CVE-2026-1001,CVE-2026-1000",
    ],
    expectedKind: "star-result",
    itemId: "arch:demo",
    mode: "temporary",
    securityAdvisory: "AVG-20260001",
    fixedVersion: "2.0-1",
    cveIds: ["CVE-2026-1001", "CVE-2026-1000"],
  });
});

test("rejects malformed conditional watch combinations without changing ordinary stars", () => {
  const { controller, starts } = fixture();
  const invalid = [
    { itemId: "aur:demo", mode: "temporary", securityAdvisory: "AVG-1", fixedVersion: "2.0", cveIds: ["CVE-2026-1000"] },
    { itemId: "arch:demo", mode: "permanent", securityAdvisory: "AVG-1", fixedVersion: "2.0", cveIds: ["CVE-2026-1000"] },
    { itemId: "arch:demo", mode: "temporary", securityAdvisory: "AVG-invalid", fixedVersion: "2.0", cveIds: ["CVE-2026-1000"] },
    { itemId: "arch:demo", mode: "temporary", securityAdvisory: "AVG-1", fixedVersion: "2.0\n", cveIds: ["CVE-2026-1000"] },
    { itemId: "arch:demo", mode: "temporary", securityAdvisory: "AVG-1", fixedVersion: "2.0", cveIds: [] },
    { itemId: "arch:demo", mode: "temporary", securityAdvisory: "AVG-1", fixedVersion: "2.0", cveIds: ["CVE-2026-1000", "CVE-2026-1000"] },
    { itemId: "arch:demo", mode: "temporary", securityAdvisory: "AVG-1", fixedVersion: "2.0", cveIds: Array.from({ length: 17 }, (_, index) => `CVE-2026-${1000 + index}`) },
    { itemId: "arch:demo", mode: "temporary", securityAdvisory: "AVG-1", fixedVersion: "2.0" },
  ];

  for (const request of invalid) assert.equal(controller.setStar(request), false, JSON.stringify(request));
  assert.equal(starts.length, 0);
  assert.equal(controller.setStar({ itemId: "aur:demo", mode: "temporary" }), true);
  assert.deepEqual(JSON.parse(JSON.stringify(starts[0].argv)), ["set-star", "--item-id", "aur:demo", "--mode", "temporary"]);
});

test("correlates set-star failures to the requested canonical target and mode", () => {
  const { controller, starts } = fixture();
  controller.start();
  complete(controller, starts[0], snapshot("generation-1"));

  controller.setStar({ itemId: "arch:demo", mode: "temporary" });
  const star = starts[1];
  complete(controller, star, "", { exitCode: 1 });

  assert.deepEqual(JSON.parse(JSON.stringify(controller.state.lastFailureOperation)), {
    id: star.id, kind: "set-star", itemId: "arch:demo", mode: "temporary",
  });
  assert.equal(controller.state.lastStarResult, null);
});

test("surfaces a typed helper error even when the helper exits with status two", () => {
  const { controller, starts } = fixture();
  controller.start();
  complete(controller, starts[0], snapshot("generation-1"));

  controller.setStar({ itemId: "arch:demo", mode: "temporary" });
  complete(controller, starts[1], helperError("star-error"), { exitCode: 2 });

  assert.equal(controller.state.lastFailureKind, "helper");
  assert.equal(controller.state.lastError, "STATE_UNAVAILABLE: validated state is unavailable");
});

test("keeps initial, periodic, retry, and post-handoff scans ordinary", () => {
  const { controller, starts } = fixture();
  controller.start();
  assert.equal(controller.state.nextWakeAt, 30_000);

  controller.wake(30_000);
  complete(controller, starts[0], snapshot("generation-1", "1970-01-01T00:05:00.000Z"));
  const initial = starts[1];
  complete(controller, initial, snapshot("generation-2", "1970-01-01T00:05:00.000Z"));
  controller.wake(60_000);
  const periodic = starts[2];
  controller.wake(300_000);
  complete(controller, periodic, snapshot("generation-3", "1970-01-01T00:05:00.000Z"));

  assert.deepEqual(JSON.parse(JSON.stringify(starts.map((operation) => operation.argv))), [
    ["snapshot"],
    ["scan"],
    ["scan"],
    ["scan"],
  ]);

  const handoff = fixture();
  handoff.controller.start();
  handoff.controller.wake(30_000);
  complete(handoff.controller, handoff.starts[0], snapshot("handoff", "1970-01-01T00:00:00.000Z"));
  const initialHandoffScan = handoff.starts[1];
  handoff.controller.recordHandoff(0);
  handoff.controller.wake(600_000);
  complete(handoff.controller, initialHandoffScan, snapshot("handoff-initial", "1970-01-01T00:00:00.000Z"));

  assert.deepEqual(JSON.parse(JSON.stringify(handoff.starts.map((operation) => operation.argv))), [
    ["snapshot"],
    ["scan"],
    ["scan"],
  ]);
});

test("shutdown drops queued work and invalidates the active callback", () => {
  const { controller, starts } = fixture();
  controller.start();
  const active = starts[0];
  controller.requestRefresh();
  controller.requestInventory({ source: "arch", query: "", limit: 20, offset: 0 });
  controller.shutdown();
  complete(controller, active, snapshot("late"));

  assert.equal(controller.state.activeOperation, null);
  assert.equal(controller.state.queuedOperations, 0);
  assert.equal(controller.state.lastSnapshot, null);
  assert.equal(starts.length, 1);
});
