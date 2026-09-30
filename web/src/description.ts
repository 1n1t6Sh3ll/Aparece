/** Characters and words of a product description (whitespace-separated words). */
export function descStats(text: string): { chars: number; words: number } {
  const t = text.trim();
  return { chars: t.length, words: t ? t.split(/\s+/).length : 0 };
}
