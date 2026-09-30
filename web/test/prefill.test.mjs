// node --test web/test  (Node >= 22.6 strips the TypeScript types of src/prefill.ts)
import assert from "node:assert/strict";
import test from "node:test";
import { isBarePrefix, productLinks, productPrefix, refreshPrefill } from "../src/prefill.ts";

test("prefix from the store URL", () => {
  assert.equal(productPrefix("https://teeco.example/"), "https://teeco.example/products/");
  assert.equal(productPrefix("https://www.teeco.example/about?x=1"), "https://www.teeco.example/products/");
  assert.equal(productPrefix(""), "");
  assert.equal(productPrefix("teeco"), "");
});

test("bare prefixes are not products", () => {
  assert.ok(isBarePrefix("https://old.example/products/"));
  assert.ok(isBarePrefix(" https://old.example/products "));
  assert.ok(!isBarePrefix("https://old.example/products/tee"));
  assert.deepEqual(productLinks("https://old.example/products/\nhttps://new.example/products/\nhttps://new.example/products/tee"),
    ["https://new.example/products/tee"]);
});

test("changing the store replaces an unedited prefill and keeps typed links", () => {
  const first = refreshPrefill("", "https://old.example/products/");
  assert.equal(first, "https://old.example/products/");
  assert.equal(refreshPrefill(first, "https://new.example/products/"), "https://new.example/products/");
  const typed = "https://old.example/products/tee";
  assert.equal(refreshPrefill(typed, "https://new.example/products/"), typed);
  assert.equal(refreshPrefill(first, ""), "");  // store URL removed: no stale prefill
});
