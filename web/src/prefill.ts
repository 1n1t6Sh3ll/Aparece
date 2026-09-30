/** Product-link prefill from the store URL. Pure (no imports) so it runs under `node --test` as well as in the app. */

const BARE = /^https?:\/\/[^\s/]+\/products\/?$/i;

/** True for a store's bare `/products/` prefix (an unedited prefill, not a product page). */
export const isBarePrefix = (u: string) => BARE.test(u.trim());

/** `<store origin>/products/`, or "" when the store URL is missing or not a full URL. */
export function productPrefix(website: string) {
  try { return website ? `${new URL(website).origin}/products/` : ""; } catch { return ""; }
}

/** Refill the product-link field: replace it with `prefix` unless the merchant has typed a real link. */
export function refreshPrefill(urls: string, prefix: string) {
  const list = urls.split(/[\n,]+/).map((x) => x.trim()).filter(Boolean);
  return list.every(isBarePrefix) ? prefix : urls;
}

/** Links to save: bare prefixes dropped. */
export const productLinks = (urls: string) => urls.split(/[\n,]+/).map((x) => x.trim()).filter((u) => u && !isBarePrefix(u));
