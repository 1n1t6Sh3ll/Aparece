// node --test web/test  (Node >= 22.6 strips the TypeScript types of src/bulk.ts)
import assert from "node:assert/strict";
import test from "node:test";
import { MAX, parseBulk } from "../src/bulk.ts";

test("URLs and TSV drafts, per-line rejects with reasons", () => {
  const { items, rejects } = parseBulk([
    "https://shop.example.com/products/tee",
    "",
    "ftp://shop.example.com/x",
    "www.shop.example.com/products/tee",
    "Heavy tee\t100% cotton. Regular fit.\t35,50\teur\tes",
    "\tno title here",
    "Tee\tdesc\tcheap",
    "Tee\tdesc\t10\tEURO",
    "just some words",
    "https://shop.example.com/products/tee",
  ].join("\n"));
  assert.deepEqual(items.map((i) => i.line), [1, 5]);
  assert.deepEqual(items[1].body, { title: "Heavy tee", description: "100% cotton. Regular fit.", price: "35.50", currency: "EUR", language: "es" });
  assert.deepEqual(rejects.map((r) => [r.line, r.reason]), [
    [3, "not_http"], [4, "not_http"], [6, "no_title"], [7, "bad_price"], [8, "bad_currency"], [9, "unrecognised"], [10, "duplicate"]]);
});

test("JSON array of urls and drafts", () => {
  const { items, rejects } = parseBulk(JSON.stringify([{ url: "https://a.example.com/p/1" }, { title: "Polo", description: "Pique" }, { description: "x" }]));
  assert.deepEqual(items.map((i) => i.body), [{ url: "https://a.example.com/p/1" }, { title: "Polo", description: "Pique" }]);
  assert.deepEqual(rejects.map((r) => [r.line, r.reason]), [[3, "no_title"]]);
  assert.equal(parseBulk("[not json").rejects[0].reason, "invalid_json");
});

test("more than MAX items are reported, not silently dropped", () => {
  const lines = Array.from({ length: MAX + 3 }, (_, i) => `https://s.example.com/products/${i}`);
  const { items, rejects } = parseBulk(lines.join("\n"));
  assert.equal(items.length, MAX);
  assert.deepEqual(rejects.map((r) => r.reason), ["too_many", "too_many", "too_many"]);
  assert.equal(rejects[0].line, MAX + 1);
});
