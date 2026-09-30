# Aparece

**See your product page the way AI shopping assistants do, and fix what they can't read.**

Shoppers now ask AI what to buy. We asked gpt-4o-mini and Claude Haiku 384 real shopping questions, in English and Spanish. None of the 103 small shirt shops we tested was named; Everlane, Uniqlo and Patagonia were. Paste your product link, and Aparece shows what machines can read on your page, ranks it against similar shirts, and gives you the 3 fixes to make first. It suggests text that only states what your page proves; you approve everything.

## Try it

```sh
docker run -p 8000:8000 ghcr.io/1n1t6sh3ll/aparece:latest
```

Open http://127.0.0.1:8000 and paste a product link. To run from source: `git clone https://github.com/1n1t6Sh3ll/powerlens.git && cd powerlens && ./run.sh` (Windows: `.\run.ps1`). You need Python 3.12+ and Node 22, and no API keys. To rank against real shirts, set `PRODUCTLENS_DATA` to the dataset (build it with `dataset/collect/wdc.py` → `dataset/build/make_ground_truth.py`). The model weights are in the [weights-v1 release](https://github.com/1n1t6Sh3ll/powerlens/releases/tag/weights-v1).

## How it works

```mermaid
flowchart TD
    U["Product link or pasted text"] --> F{"Fetch the page<br/>respects robots.txt, never Amazon<br/>api/safe_fetch.py"}
    F -- blocked --> X["Extension or pasted draft<br/>extension/"]
    X --> V
    F -- ok --> V["Verified facts, each with its evidence<br/>dataset/collect/normalize.py"]
    Q["Fine-tuned Qwen fills empty fields<br/>labelled 'predicted'<br/>train/"] -.-> V
    D[("20,037-shirt dataset<br/>dataset/")] --> M
    V --> M["Match comparable shirts<br/>same type, language, audience, sleeve, price<br/>analysis/peers.py"]
    M --> S["Score and rank<br/>60 facts + 20 questions + 20 markup<br/>api/audit_api.py"]
    S --> A["Top 3 fixes, with evidence"]
    A --> G["Generate Fix<br/>write from facts → fact-check → reward → best wins<br/>optimizer/, train/reward.py"]
    G --> H{"Merchant approves?"}
    H -- yes --> P["Use the new title and description"]
    H -. "accept / dismiss, winner vs loser pairs" .-> T["Training feedback<br/>optimizer/data/pairs.jsonl"]
    T -.-> Q
    V --> C["AI comparison<br/>shop vs Aparece vs AI models<br/>benchmark/shootout/"]
    V --> B["AI visibility<br/>real AI answers: who gets named?<br/>benchmark/harness.py"]
    P --> N["Monitor over time<br/>snapshots, changes, chat<br/>monitor/, chat/"]
    N --> F
```

**The key formulas**

```
listing score = 60 × (key facts stated ÷ 22) + 20 × (shopper questions answered ÷ 9) + 20 × (markup found ÷ 2)
rank          = 1 + number of comparable shirts with a higher score
reward        = 1 + share of sentences passing the fact-check − 2 × flagged sentences + 2 × share of facts covered
```

The fact-check rejects any word or number that your page's facts don't back (`optimizer/guard.py`). In the AI comparison, only parts that pass can win: the best title score, the best tag score, and the best description (most AI mentions, or the most facts covered).

## Results

| Test (same input for every model) | Result |
|---|---|
| Reading product pages (200 products, 63 stores) | Aparece Qwen2.5-0.5B **85.8%** · GPT-4.1 27.2% · untuned Qwen 4.7% |
| Writing product copy | Aparece best on title, tags and description with no unsupported claims; visibility a statistical tie |
| Which shops AI names (384 questions) | 0% for the 103 small shops; big brands named instead |

Caveats: the extraction test uses our own label format, and the copy-test judges are also AI models. Human feedback is being collected (label reviews, confirmed predictions, accepted fixes, text pairs), but the model hasn't been retrained on it yet.

## Learn more

[How it works](docs/HOW_IT_WORKS.md) covers every formula, where it is in the code, tags, the human loop and the vision. The [Reference](docs/REFERENCE.md) lists all settings and API routes, and there's a [Vision](docs/VISION.md) document. Tests: `python -m unittest discover -s api/tests` and `cd web && npm test` (offline, no paid calls). The code is MIT-licensed; the data and weights are for research use.
