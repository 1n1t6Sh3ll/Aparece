# User stories (QA acceptance)

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
