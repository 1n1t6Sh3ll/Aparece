# User stories

## Company story (pitch and exec summary)

**As a DTC apparel brand (e.g. a 20–500 SKU Shopify shirt store), I want to know which facts shoppers, search engines and AI assistants can and cannot find on each product page, and get grounded fixes I approve before anything changes, so that my shirts are described correctly and recommended more often, without me guessing or publishing claims I cannot back up.**

Why it matters: AI shopping answers are built from whatever facts a page exposes. A small brand cannot see what is missing or what the AI gets wrong. ProductLens gives every fact an evidence snippet, never invents one, and measures change over time. Targets below are goals to test, not results already measured.

| Persona | Story | Features used | Success outcome (measured in the product) |
|---|---|---|---|
| **Founder / merchandiser** at a 20–500 SKU shirt store | I want the 3 fixes that matter most for each shirt and a draft title/description I can accept or dismiss, so that my catalogue lists fabric, weight, fit and sizes before the next drop. | Company profile, Audit, 3 fixes, Generate Fix, My products, Monitoring | Within 30 days: facts found per page (`n / 22`) up on at least half of the catalogue; every accepted change traced to an evidence snippet (0 invented facts). |
| **Agency** running several apparel clients | I want to audit a client's catalogue in one pass, export it and share a read-only report, so that I can show the gaps and the before/after in a client meeting. | Bulk audit (20 URLs, CSV/print), Company switcher, Shareable report, Competitor audits | First client report in under 15 minutes per 20 URLs; re-audit after fixes shows fewer open fixes per product. |
| **Marketplace seller blocked by Amazon** | I want to audit my listing even though ProductLens never fetches Amazon, so that I can fix the copy before I paste it back. | Blocked store / Amazon message, one-click draft audit, Generate Fix, AI comparison | Draft audit in one click from the blocked message; AI-visibility check shows higher mention/citation rate and claim accuracy after the fix. |

How the company profile feeds the loop: the store link prefills product links in onboarding and My products, the first market and language set draft currency and language, and each competitor link is a one-click audit in My products. Profile data stays merchant-stated and is never shown as verified.

## QA acceptance stories

Source: QA round 2 (issues #87-#91). Each story lists what a user must be able to do; QA checks them against the running app.

1. **Audit.** A merchant pastes a product URL and within about 10 seconds sees the listing-quality rank and the 3 fixes to do first. The homepage examples work. Errors are translated and offer the draft route where it helps. Every audit has a shareable URL (`#/report/<id>`).
2. **Blocked store or Amazon.** When a store blocks automated reading, robots.txt disallows the page, or the link is Amazon, the merchant sees a clear reason and can switch to a draft in one click. No raw error codes are shown.
3. **Fix.** The merchant ticks fixes off the plan, uses "Generate fix" to get a title and description grounded in facts found on the page, and accepts or dismisses each suggestion. Nothing is published without the merchant's approval.
4. **Compare with AI.** Both `#/compare/<id>` and `#/compare?product=<id>` work. Sample data is labelled, and another product's numbers are never shown for a product outside the comparison set.
5. **Monitor.** In My products the merchant opens a monitored product, compares any two snapshots, sees trends and change events, and asks the grounded chat. Access is scoped by the manage token in this browser. An unknown id shows "not found".
6. **Agency bulk.** An agency audits up to 20 URLs with progress, exports CSV or prints, and invalid lines are reported.
7. **Models.** The Models page shows accuracy, cost and speed per model, with the run date.
8. **Governance.** An owner sees only their own audit log and approvals.
9. **Share.** A shared link reproduces the report (stored result, unlisted, not indexed).
10. **i18n and mobile.** Every screen works in English and Spanish, and there is no horizontal scroll at 375px.
