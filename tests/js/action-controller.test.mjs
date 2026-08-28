import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const repositoryRoot = resolve(import.meta.dirname, "../..");
const servicePath = resolve(repositoryRoot, "Service.qml");
const policyPath = resolve(repositoryRoot, "qml/models/ActionPolicy.js");
const controllerPath = resolve(repositoryRoot, "qml/models/ServiceController.js");
const handoffPath = resolve(repositoryRoot, "qml/models/TerminalHandoff.qml");

function loadPolicy() {
  assert.equal(existsSync(policyPath), true, "Todo 18 action policy must exist");
  const context = vm.createContext({ Array, Object, String });
  const source = readFileSync(policyPath, "utf8").replace(".pragma library", "");
  vm.runInContext(source, context, { filename: policyPath });
  return context;
}

function loadController() {
  const source = readFileSync(controllerPath, "utf8").replace(".pragma library", "");
  const context = vm.createContext({ JSON, Math, Number, Object, String });
  vm.runInContext(source, context, { filename: controllerPath });
  return context.createController;
}

function source(name, status = "ok", provenance = "live") {
  const health = {
    source: name,
    status,
    provenance,
    observedAt: "2026-08-26T00:00:00.000Z",
    freshUntil: "2026-08-26T00:05:00.000Z",
    cause: null,
  };
  if (name === "flatpak") {
    health.scopes = ["user", "system"].map((scope) => ({
      scope,
      status: "ok",
      provenance: "live",
      observedAt: "2026-08-26T00:00:00.000Z",
      freshUntil: "2026-08-26T00:05:00.000Z",
      cause: null,
    }));
  }
  return health;
}

function snapshot(items, sources = [source("omarchy"), source("flatpak")]) {
  return { payload: { sources, items } };
}

function capabilities(overrides = {}) {
  return { launcher: true, omarchyUpdate: true, flatpak: true, ...overrides };
}

test("exposes only the three typed service action methods", () => {
  const service = readFileSync(servicePath, "utf8");
  const handoff = readFileSync(handoffPath, "utf8");

  assert.match(service, /function openOmarchyUpdate\(/);
  assert.match(service, /function openFlatpakUserUpdate\(/);
  assert.match(service, /function openFlatpakSystemUpdate\(/);
  assert.doesNotMatch(service, /function open[A-Z][A-Za-z]+\([^)]*command/);
  assert.doesNotMatch(handoff, /function start\(argv\)/);
});

test("builds the three native handoffs from fixed argv constants", () => {
  const policy = loadPolicy();

  assert.deepEqual(JSON.parse(JSON.stringify(policy.actionFor("omarchy").argv)), [
    "/usr/bin/omarchy-launch-floating-terminal-with-presentation",
    "/usr/bin/omarchy-update",
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(policy.actionFor("flatpak-user").argv)), [
    "/usr/bin/omarchy-launch-floating-terminal-with-presentation",
    "/usr/bin/flatpak",
    "--user",
    "update",
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(policy.actionFor("flatpak-system").argv)), [
    "/usr/bin/omarchy-launch-floating-terminal-with-presentation",
    "/usr/bin/flatpak",
    "--system",
    "update",
  ]);
});

test("enables only current applicable sources and matching update scopes", () => {
  const policy = loadPolicy();
  const updates = [
    { id: "omarchy:omarchy", source: "omarchy", candidate: "0.2" },
    { id: "flatpak:user:app/org.example.App/x86_64/stable", source: "flatpak", candidate: "2" },
    { id: "flatpak:system:app/org.example.Tool/x86_64/stable", source: "flatpak", candidate: "3" },
  ];
  const state = snapshot(updates);

  assert.equal(policy.isEligible(state, "omarchy", capabilities()), true);
  assert.equal(policy.isEligible(state, "flatpak-user", capabilities()), true);
  assert.equal(policy.isEligible(state, "flatpak-system", capabilities()), true);
});

test("orders update-all as a closed set and rechecks each action's current eligibility", () => {
  const policy = loadPolicy();
  const updates = [
    { id: "omarchy:omarchy", source: "omarchy", candidate: "0.2" },
    { id: "flatpak:user:app/org.example.App/x86_64/stable", source: "flatpak", candidate: "2" },
    { id: "flatpak:system:app/org.example.Tool/x86_64/stable", source: "flatpak", candidate: "3" },
  ];
  const state = snapshot(updates);

  assert.deepEqual(JSON.parse(JSON.stringify(policy.UPDATE_ALL_ACTIONS)), ["omarchy", "flatpak-user", "flatpak-system"]);
  assert.deepEqual(JSON.parse(JSON.stringify(policy.eligibleUpdateActions(state, capabilities()))), ["omarchy", "flatpak-user", "flatpak-system"]);
  state.payload.sources.find((entry) => entry.source === "flatpak").scopes[0].status = "stale";
  assert.deepEqual(JSON.parse(JSON.stringify(policy.eligibleUpdateActions(state, capabilities()))), ["omarchy", "flatpak-system"]);
});

test("routes System, AUR, mise, and Omarchy updates through the full native workflow", () => {
  const policy = loadPolicy();

  for (const sourceName of ["omarchy", "arch", "aur", "mise"]) {
    const state = snapshot(
      [{ id: `${sourceName}:fixture`, source: sourceName, candidate: "2" }],
      [source("omarchy"), source("flatpak"), source(sourceName)],
    );
    assert.deepEqual(JSON.parse(JSON.stringify(policy.actionFor("omarchy").argv)), [
      "/usr/bin/omarchy-launch-floating-terminal-with-presentation",
      "/usr/bin/omarchy-update",
    ]);
    assert.equal(policy.isEligible(state, "omarchy", capabilities()), true, sourceName);
  }
});

test("rejects unavailable executables, absent updates, and uncurrent source evidence", () => {
  const policy = loadPolicy();
  const omarchyUpdate = { id: "omarchy:omarchy", source: "omarchy", candidate: "0.2" };
  const userUpdate = { id: "flatpak:user:app/org.example.App/x86_64/stable", source: "flatpak", candidate: "2" };

  assert.equal(policy.isEligible(snapshot([omarchyUpdate]), "omarchy", capabilities({ launcher: false })), false);
  assert.equal(policy.isEligible(snapshot([omarchyUpdate]), "omarchy", capabilities({ omarchyUpdate: false })), false);
  assert.equal(policy.isEligible(snapshot([userUpdate]), "flatpak-user", capabilities({ flatpak: false })), false);
  assert.equal(policy.isEligible(snapshot([], [source("omarchy"), source("flatpak")]), "omarchy", capabilities()), false);

  for (const status of ["not_applicable", "error", "stale"]) {
    assert.equal(policy.isEligible(snapshot([omarchyUpdate], [source("omarchy", status), source("flatpak")]), "omarchy", capabilities()), false, status);
  }

  const scoped = source("flatpak");
  scoped.scopes[0].status = "stale";
  assert.equal(policy.isEligible(snapshot([userUpdate], [source("omarchy"), scoped]), "flatpak-user", capabilities()), false);
  assert.equal(policy.isEligible(null, "omarchy", capabilities()), false);
  assert.equal(policy.isEligible({ payload: { sources: [], items: "malformed" } }, "omarchy", capabilities()), false);
});

test("does not turn hostile snapshot data into argv or mutate the validated snapshot", () => {
  const policy = loadPolicy();
  const hostile = "$(touch /tmp/opatchy-injection-sentinel)";
  const state = snapshot([
    { id: `flatpak:user:${hostile}`, source: "flatpak", label: hostile, candidate: hostile, remote: hostile },
  ]);
  const before = JSON.stringify(state);
  const action = policy.actionFor("flatpak-user");

  assert.equal(policy.isEligible(state, "flatpak-user", capabilities()), true);
  assert.equal(JSON.stringify(state), before);
  assert.doesNotMatch(JSON.stringify(action.argv), new RegExp(hostile.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.equal("watches" in state, false);
});

test("rejects all mutation and fixture-derived argv tokens", () => {
  const policy = loadPolicy();
  const argv = ["omarchy", "flatpak-user", "flatpak-system"]
    .flatMap((name) => policy.actionFor(name).argv)
    .join("\u0000");
  const fixtureToken = "fixture-remote-token";

  for (const forbidden of ["pacman", "yay", "paru", "sudo", "pkexec", "-y", "--assumeyes", fixtureToken]) {
    assert.equal(argv.includes(forbidden), false, forbidden);
  }
});

test("records only the latest handoff and coalesces it into one delayed scan", () => {
  const starts = [];
  const controller = loadController()({
    now: () => 0,
    random: () => 0,
    refreshIntervalMs: 3_600_000,
    onStart: (operation) => starts.push(operation),
    onState: () => {},
    onResponse: () => {},
    parseResponse: (stdout) => ({ ok: true, value: JSON.parse(stdout) }),
  });
  controller.start();
  const initial = starts[0];
  controller.complete(initial.id, {
    exitCode: 0,
    stdout: JSON.stringify({ kind: "snapshot", payload: { sources: [] } }),
    stderr: "",
    timedOut: false,
    outputTooLarge: false,
  });
  controller.wake(30_000);
  const initialScan = starts[1];
  controller.complete(initialScan.id, {
    exitCode: 0,
    stdout: JSON.stringify({ kind: "snapshot", payload: { sources: [] } }),
    stderr: "",
    timedOut: false,
    outputTooLarge: false,
  });
  const snapshotBeforeHandoff = controller.state.lastSnapshot;

  controller.recordHandoff(1);
  controller.recordHandoff(2);

  assert.equal(controller.state.handoffAt, 2);
  assert.equal(controller.state.lastSnapshot, snapshotBeforeHandoff);
  assert.equal(controller.state.lastStarResult, null);
  assert.equal(controller.state.activeOperation, null);
  assert.equal(controller.state.queuedOperations, 0);
  controller.wake(600_002);
  assert.equal(starts.length, 3);
  controller.wake(600_002);
  assert.equal(starts.length, 3);
});

test("connects update-all sequencing only to terminal completion without shell composition", () => {
  const service = readFileSync(servicePath, "utf8");
  const handoff = readFileSync(handoffPath, "utf8");

  assert.match(service, /function requestUpdateAll\(/);
  assert.match(service, /ActionPolicy\.UPDATE_ALL_ACTIONS\.slice\(\)/);
  assert.match(service, /ActionPolicy\.isEligible\(lastSnapshot, actionName, actionCapabilities\)/);
  assert.match(service, /handoffTransport\.finished/);
  assert.match(service, /handoffTransport\.finished\.connect\(handleHandoffFinished\)/);
  assert.match(handoff, /signal finished\(int exitCode\)/);
  assert.doesNotMatch(service, /\/bin\/sh/);
  assert.doesNotMatch(service, /handoffTransport\.start\(\[/);
});
