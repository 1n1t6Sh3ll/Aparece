# PowerLens Chrome extension

MV3 popup (plain JS, no build) that sends the active tab URL to `POST {apiBase}/v1/extract` and shows the extracted product facts with their evidence.

## Load unpacked
1. Open `chrome://extensions` and enable **Developer mode**.
2. Click **Load unpacked** and select this `extension/` folder.
3. Start the API (default `http://localhost:8000`), open a product page, click the PowerLens icon, then **Audit product**.

## Settings
Right-click the icon > **Options** (or use the popup's Settings link) to change the API base URL. Saving requests host access to that origin only.

## Preview with mock data
Open `chrome-extension://<extension-id>/popup.html?mock=1` (the ID is shown on `chrome://extensions`). It renders `mock.json`, built from `dataset/examples/normalized_record.example.json`.

## Behaviour
- Overview: name, type, language, materials with %, fit, sleeve, neckline, colors, sizes, price, currency, quality status, conflicts.
- Hover or expand a fact to see its evidence text. Null fields are listed under "Not found on page".
- Network, HTTP and JSON errors are shown in the popup.

Permissions: `activeTab`, `storage`, host access to `http://localhost:8000/*`. Other API origins are optional and requested on save.
