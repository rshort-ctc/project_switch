import assert from "node:assert/strict";
import test from "node:test";

import { validateLocalBackendUrl } from "../src/locality";
import { sanitizeTitle } from "../src/render";

test("validateLocalBackendUrl accepts local endpoints", () => {
  assert.equal(validateLocalBackendUrl("http://127.0.0.1:8000/"), "http://127.0.0.1:8000");
  assert.equal(validateLocalBackendUrl("http://localhost:8000"), "http://localhost:8000");
  assert.equal(
    validateLocalBackendUrl("http://switch.internal:8000"),
    "http://switch.internal:8000",
  );
});

test("validateLocalBackendUrl rejects remote endpoints", () => {
  assert.throws(() => validateLocalBackendUrl("https://api.example.com"), /LOCAL_ONLY/);
});

test("sanitizeTitle strips unsafe noisy characters", () => {
  assert.equal(sanitizeTitle("Fix token() <bad>\nnow"), "Fix token bad now");
});
