import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import ts from "typescript";

const uuidV4Pattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const originalCryptoDescriptor = Object.getOwnPropertyDescriptor(globalThis, "crypto");
const safeRandomUUID = await loadSafeRandomUUID();

test.afterEach(() => {
  restoreCrypto();
});

test("uses crypto.randomUUID when available", () => {
  const expected = "11111111-2222-4333-8444-555555555555";
  let getRandomValuesCalled = false;

  replaceCrypto({
    randomUUID: () => expected,
    getRandomValues: (array) => {
      getRandomValuesCalled = true;
      return array;
    },
  });

  assert.equal(safeRandomUUID(), expected);
  assert.equal(getRandomValuesCalled, false);
});

test("uses crypto.getRandomValues when randomUUID is unavailable", () => {
  replaceCrypto({
    getRandomValues: (array) => {
      for (let index = 0; index < array.length; index += 1) {
        array[index] = index;
      }
      return array;
    },
  });

  const value = safeRandomUUID();

  assert.match(value, uuidV4Pattern);
  assert.equal(value.length, 36);
});

test("falls back when crypto is missing entirely", () => {
  replaceCrypto(undefined);

  const value = safeRandomUUID();

  assert.equal(typeof value, "string");
  assert.notEqual(value.length, 0);
  assert.match(value, uuidV4Pattern);
});

test("is safe without a window object", () => {
  replaceCrypto(undefined);

  assert.equal(globalThis.window, undefined);
  assert.doesNotThrow(() => safeRandomUUID());
});

test("falls back when crypto methods throw", () => {
  replaceCrypto({
    randomUUID: () => {
      throw new TypeError("randomUUID unavailable");
    },
    getRandomValues: () => {
      throw new TypeError("getRandomValues unavailable");
    },
  });

  const value = safeRandomUUID();

  assert.match(value, uuidV4Pattern);
});

async function loadSafeRandomUUID() {
  const source = readFileSync(new URL("../lib/safe-random-uuid.ts", import.meta.url), "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const tempDir = mkdtempSync(join(tmpdir(), "switch-uuid-test-"));
  const modulePath = join(tempDir, "safe-random-uuid.mjs");

  writeFileSync(modulePath, transpiled, "utf8");
  const loadedHelper = await import(`file://${modulePath}`);
  rmSync(tempDir, { recursive: true, force: true });

  return loadedHelper.safeRandomUUID;
}

function replaceCrypto(value) {
  Object.defineProperty(globalThis, "crypto", {
    configurable: true,
    value,
  });
}

function restoreCrypto() {
  if (originalCryptoDescriptor) {
    Object.defineProperty(globalThis, "crypto", originalCryptoDescriptor);
    return;
  }

  delete globalThis.crypto;
}
