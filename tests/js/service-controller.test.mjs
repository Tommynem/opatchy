import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const repositoryRoot = resolve(import.meta.dirname, "../..");
const controllerPath = resolve(repositoryRoot, "qml/models/ServiceController.js");
const validatorPath = resolve(repositoryRoot, "qml/models/ProtocolValidator.js");

function loadController() {
  const source = readFileSync(controllerPath, "utf8").replace(".pragma library", "");
  const context = vm.createContext({ JSON, Math, Number, Object, String });
  vm.runInContext(source, context, { filename: controllerPath });
  return context.createController;
}

function loadValidator() {
  const source = readFileSync(validatorPath, "utf8").replace(".pragma library", "");
  const context = vm.createContext({ JSON, Math, Number, Object, String });
  vm.runInContext(source, context, { filename: validatorPath });
  return context.parseResponse;
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
        watchable: true,
        provenance: "live",
      }],
      findings: [{
        itemId: "arch:demo",
        findings: [{
          id: "AVG-1",
          itemId: "arch:demo",
          advisoryId: "AVG-1",
          cveIds: ["CVE-2026-1"],
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
    payload: { itemId: "arch:demo", mode: "temporary" },
  });
}

function fixture(now = 0) {
  const starts = [];
  const states = [];
  const controller = loadController()({
    now: () => now,
    random: () => 0,
    refreshIntervalMs: 60_000,
    onStart: (operation) => starts.push(operation),
    onState: (state) => states.push(state),
    onResponse: () => {},
    parseResponse: loadValidator(),
  });
  return { controller, starts, states };
}

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

test("coalesces simultaneous refreshes into one queued rescan", () => {
  const { controller, starts } = fixture();
  controller.start();
  const initial = starts[0];

  controller.requestRefresh();
  controller.requestRefresh();
  controller.requestRefresh();
  complete(controller, initial, snapshot("generation-1"));

  assert.deepEqual(starts.map((operation) => operation.kind), ["snapshot", "scan"]);
  const scan = starts[1];
  controller.requestRefresh();
  controller.requestRefresh();
  controller.requestRefresh();
  complete(controller, scan, snapshot("generation-2"));

  assert.deepEqual(starts.map((operation) => operation.kind), ["snapshot", "scan", "scan"]);
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

test("schedules initial, earliest-source, and post-handoff scans deterministically", () => {
  const { controller, starts } = fixture();
  controller.start();
  assert.equal(controller.state.nextWakeAt, 30_000);

  controller.wake(30_000);
  complete(controller, starts[0], snapshot("generation-1", "1970-01-01T00:05:00.000Z"));
  assert.equal(controller.state.nextWakeAt, 300_000);

  controller.schedulePostHandoffScan(0);
  assert.equal(controller.state.nextWakeAt, 300_000);
  controller.wake(300_000);
  assert.deepEqual(starts.map((operation) => operation.kind), ["snapshot", "scan"]);
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
