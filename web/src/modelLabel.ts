/** A data label may carry its own English " — partial: 87 of 200" (hand-set in the git-ignored comparison.json);
 * the localized "partial" chip already says it, so drop it. Needs whitespace before the dash ("Semi-partial" is kept). */
export const nm = (m: { label: string }) => m.label.replace(/\s+[—–-]\s*partial.*$/i, "");
