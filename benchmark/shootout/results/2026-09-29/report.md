# AI comparison: title, tags, description

**Controlled evaluation (simulated shopping context); not proof of real-world ranking.**

5 products (en, es); judges openai:gpt-4o-mini, anthropic:claude-haiku-4-5-20251001 (held out: anthropic:claude-haiku-4-5-20251001); 6 dev/val prompts x 1 repeats.

- Best title: **productlens** (product wins: {'productlens': 4, 'openai:gpt-4o-mini': 1})
- Best tags: **productlens** (product wins: {'openai:gpt-4o-mini': 1, 'productlens': 3, 'anthropic:claude-haiku-4-5-20251001': 1})
- Best description: **productlens** (product wins: {'productlens@openai:gpt-4o-mini': 2, 'productlens': 3})
- Highest measured visibility (whole candidate, MRR, primary judges): **productlens**; vs productlens@openai:gpt-4o-mini +0.013 [-0.089, +0.116] (not separated; treat as a tie)
- Held-out judge anthropic:claude-haiku-4-5-20251001: productlens@openai:gpt-4o-mini (disagrees)

| Generator | Qualified | Flagged | Unsupp. claims | Title score | Tags score | Attr. cov. | Intent cov. | MRR [95% CI] | Mention [95% CI] |
|---|---|---|---|---|---|---|---|---|---|
| original | 0/5 | 27 | 21 | 0.53 | 0.0 | 0.6162 | 0.1417 | 0.422 [0.306, 0.556] | 0.700 [0.533, 0.867] |
| productlens | 5/5 | 0 | 0 | 0.86 | 0.9067 | 1.0 | 0.0312 | 0.396 [0.253, 0.537] | 0.633 [0.467, 0.800] |
| productlens@openai:gpt-4o-mini | 5/5 | 0 | 0 | 0.82 | 0.9067 | 0.6191 | 0.0417 | 0.383 [0.260, 0.522] | 0.667 [0.500, 0.833] |
| openai:gpt-4o-mini | 0/5 | 19 | 1 | 0.81 | 0.7675 | 0.8229 | 0.0771 | 0.426 [0.302, 0.559] | 0.700 [0.533, 0.867] |
| anthropic:claude-haiku-4-5-20251001 | 0/5 | 15 | 2 | 0.81 | 0.889 | 0.96 | 0.0875 | 0.472 [0.342, 0.596] | 0.767 [0.600, 0.900] |

## Recommended per product (guardrail-passing parts only)

### Merch Monger Green Line Short-Sleeve Unisex T-Shirt (en)
- Title (productlens): Merch Monger Green Line Short-Sleeve Unisex T-Shirt - 100% cotton
- Tags (openai:gpt-4o-mini, productlens): unisex t-shirt, green t-shirt, short sleeve, cotton t-shirt, Merch Monger, t-shirt, cotton, short sleeves
- Description (productlens@openai:gpt-4o-mini): This unisex t-shirt features short sleeves and is made from 100% cotton. It is available in a green color. The fabric weight is 142 gsm.

### Mercharoo Kawartha short sleeve women's organic V-neck t-shirt - 38017 (en)
- Title (productlens): Mercharoo Kawartha short sleeve women's organic V-neck t-shirt - 38017
- Tags (productlens, openai:gpt-4o-mini): t-shirt, organic cotton, elastane, short sleeves, v-neck, for women, 200 gsm, short sleeve
- Description (productlens): Material: 95% organic cotton, 5% elastane. Fabric weight: 200 gsm. Stretch fabric. Short sleeves. V-neck. For women.

### Chimmi Children of Immigrants T-Shirt - Midnight Black (en)
- Title (productlens): Chimmi Children of Immigrants T-Shirt - Midnight Black
- Tags (productlens, openai:gpt-4o-mini): t-shirt, oversized fit, short sleeves, crew neck, printed, black, Chimmi, black t-shirt
- Description (productlens@openai:gpt-4o-mini): This t-shirt features an oversized fit with short sleeves and a crew neck. It is printed in black.

### Thinking MU Camiseta Esqué Aaron (es)
- Title (openai:gpt-4o-mini): Camiseta Esqué Aaron de Thinking MU - 100% algodón orgánico
- Tags (productlens): camiseta, algodón orgánico, corte holgado, manga corta, cuello redondo, estampado, para hombre, 180 gsm
- Description (productlens): Material: 100% algodón orgánico. Gramaje: 180 gsm. Corte holgado. Manga corta. Cuello redondo. Estampado. Para hombre. Tallas: XS, S, M, L, XL, XXL. Cuidado: LAVADO A MÁQUINA A 30º CON ACCIÓN MECÁNICA REDUCIDA. Cuidado: NO USAR LEJIA. Cuidado: NO USAR SECADORA. Cuidado: PLANCHAR DEL REVÉS A BAJA TEMPERATURA. Cuidado: PERMITE LIMPIEZA EN SECO.

### Sepiia Camiseta hombre cuello redondo estampado rayas rosa Soft (es)
- Title (productlens): Sepiia Camiseta hombre cuello redondo estampado rayas rosa Soft
- Tags (anthropic:claude-haiku-4-5-20251001, productlens): camiseta hombre, cuello redondo, rayas rosa, manga corta, fácil cuidado, talla S M L XL 2XL, camiseta, corte holgado
- Description (productlens): Corte holgado. Manga corta. Cuello redondo. De rayas. Para hombre. Colores: rosa. Tallas: S, M, L, XL, 2XL. Cuidado: Menos tiempo pendiente de la camiseta. Se arruga menos, seca rápidamente y simplifica el cuidado entre usos. Cuidado: Cuidado: Fácil mantenimiento, no requiere plancha. Cuidado: LAVAR EN FRÍO O MÁX 30º. Cuidado: LAVAR Y COLGAR.

## Caveats

- Simulated context: 5 product pages chosen by us, not a real search index or live assistant.
- Small n: 5 products x 6 prompts x 1 repeats; CIs are cluster bootstrap over (product, prompt).
- Judges are from the same model families as the AI generators (OpenAI, Anthropic); self-preference is possible.
- Winner chosen on judges other than the held-out one (anthropic:claude-haiku-4-5-20251001); nothing was tuned on these results.
- Guardrail is a strict allowlist: harmless paraphrases can be flagged, which disqualifies that part.
- Title and tag winners are deterministic audit scores, not measured visibility.
- The merchant original is judged against the same Product Truth; the dataset has no merchant tags.

Cost: $0.4367 (300 judge calls).
