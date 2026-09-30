import assert from "node:assert/strict";
import test from "node:test";
import { nm } from "../src/modelLabel.ts";

test("strips the English partial suffix only", () => {
  assert.equal(nm({ label: "Claude Sonnet 5.5 (API) — partial: 87 of 200" }), "Claude Sonnet 5.5 (API)");
  assert.equal(nm({ label: "Semi-partial model" }), "Semi-partial model");
  assert.equal(nm({ label: "Plain" }), "Plain");
});
