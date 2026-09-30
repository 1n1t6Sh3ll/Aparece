import assert from "node:assert/strict";
import test from "node:test";
import { descStats } from "../src/description.ts";

test("counts chars and words", () => {
  assert.deepEqual(descStats("  Soft cotton\ntee. "), { chars: 16, words: 3 });
  assert.deepEqual(descStats(""), { chars: 0, words: 0 });
  assert.deepEqual(descStats("   \n "), { chars: 0, words: 0 });
});
