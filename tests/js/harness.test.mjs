import assert from "node:assert/strict";
import { accessSync, constants } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const repositoryRoot = resolve(import.meta.dirname, "../..");

test("quality harness entry points exist when the checkout is inspected", () => {
  for (const path of [
    "pyproject.toml",
    "Makefile",
    "scripts/validate.sh",
    "scripts/qml_offscreen.sh",
  ]) {
    assert.doesNotThrow(() => {
      accessSync(resolve(repositoryRoot, path), constants.R_OK);
    });
  }
});
