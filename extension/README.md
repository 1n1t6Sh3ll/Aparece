# PowerLens Chrome extension

MV3 popup (plain JS, no build). On a product page, **Audit this product** sends the tab URL to `POST {apiBase}/v1/audit` and shows the listing audit.

## Load unpacked
1. Open `chrome://extensions` and enable **Developer mode**.
2. Click **Load unpacked** and select this `extension/` folder.
3. Start the API (default `http://localhost:8000`), open a product page, click the PowerLens icon, then **Audit this product**.

## What the popup shows
- Listing-quality rank: "#k of N similar shirts", or "No comparable shirts" when the dataset has none.
- The 3 things to fix first; expand one to see its evidence (how many top-ranked similar shirts state it, etc.).
- Top missing attributes (not found on the page, which is not the same as the product lacking them).
- Price position against comparable listings.
- AI visibility: placeholder until the benchmark runs.
- **Compare with AI models** opens `{apiBase}/#/compare?product=<product_id>`; **Open full report** opens the web app audit for the URL.

## Audit as draft
If the API can't fetch the store (HTTP 403 or higher, e.g. blocked by robots.txt or a bot wall), or the page is on Amazon, the popup offers **Audit as draft**. Only when you click it, the extension reads the page's visible title and description (and the displayed price, if any) from the active tab with `chrome.scripting` in your own browser, and sends them to `POST /v1/audit` as `{title, description, language}`. No background scraping, no content script runs otherwise.

## Settings
Right-click the icon > **Options** (or the popup's Settings link):
- API base URL. Saving requests optional host access to that origin only.
- Profile token (optional), sent as the `X-Profile-Token` header. Stored in `chrome.storage.local`, never synced.
- Language: browser default, English or Spanish.

## Preview with mock data
Open `chrome-extension://<extension-id>/popup.html?mock=1` (add `&lang=es` for Spanish). It renders `mock.json`, a real `/v1/audit` response for `api/tests/fixtures/heavy_tee.html` against the test fixtures dataset.

Permissions: `activeTab`, `scripting`, `storage`, host access to `http://localhost:8000/*`. Other API origins are optional and requested on save. All page and API text is inserted with `textContent` (no `innerHTML`).
