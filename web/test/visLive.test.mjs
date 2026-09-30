import assert from "node:assert/strict";
import test from "node:test";
import { liveModelName } from "../src/visLive.ts";

test("names the two assistants and passes unknown ids through", () => {
  assert.equal(liveModelName("openai:gpt-4o-mini"), "ChatGPT (GPT-4o mini)");
  assert.equal(liveModelName("anthropic:claude-haiku-4-5-20251001"), "Claude (Haiku 4.5)");
  assert.equal(liveModelName("x:y"), "x:y");
});
