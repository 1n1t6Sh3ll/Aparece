// Shared by popup and options: settings (chrome.storage.local), EN/ES strings, safe DOM builder (no innerHTML).
const DEFAULTS = { apiBase: "http://localhost:8000", token: "", lang: "auto" };

function getSettings() {
  return new Promise((resolve) => {
    if (!globalThis.chrome || !chrome.storage) return resolve({ ...DEFAULTS });
    chrome.storage.local.get(DEFAULTS, (v) => resolve({ ...DEFAULTS, ...v, apiBase: v.apiBase || DEFAULTS.apiBase }));
  });
}

function pickLang(pref) {
  const q = new URLSearchParams(location.search).get("lang");
  const l = q || (pref && pref !== "auto" ? pref : (navigator.language || "en"));
  return l.toLowerCase().startsWith("es") ? "es" : "en";
}

const STR = {
  en: {
    settings: "Settings", audit: "Audit this product", draft: "Audit as draft",
    auditing: "Auditing…", reading: "Reading the page title and description…",
    needPage: "Open a product page (http/https) first.",
    unreachable: (b) => `Cannot reach the API at ${b}. Is it running? Check Settings.`,
    blocked: "This store blocked our fetch. You can audit it as a draft: we read the visible title and description from this tab (only now, in your browser) and send them to the API.",
    amazon: "Amazon pages can't be fetched by the API. Audit as a draft instead: we read the visible title and description from this tab (only now, in your browser).",
    draftNote: "Audited as a draft from the visible title and description. Page markup is not scored.",
    apiError: (s, t) => `API error ${s}: ${t}`,
    badJson: "The API returned invalid JSON.",
    noTitle: "No product title found on this page.",
    rankHead: "Listing quality",
    rank: (k, n, t) => `#${k} of ${n} similar ${t}`,
    noPeers: (t) => `No comparable ${t} in our dataset yet.`,
    shirts: "shirts", score: (s) => `Score ${s}/100 (page completeness, not a search or AI rank).`,
    fixHead: "Fix these first", noFix: "Nothing to fix against the top-ranked similar shirts.",
    missingHead: "Top missing attributes", missingOf: (c, n) => `${c} of ${n} top shirts state it`,
    notFoundNote: "Not found on your page; that doesn't mean the product lacks it.",
    priceHead: "Price position",
    pos: { below: "Below the typical range", within: "Within the typical range", above: "Above the typical range" },
    priceLine: (p, c, a, b, m, n) => `${p} ${c} vs ${a}–${b} ${c} (median ${m}, ${n} comparable listings)`,
    noPrice: "Not enough comparable prices to position yours.",
    visHead: "AI visibility", visBody: "Not run yet.",
    compare: "Compare with AI models", report: "Open full report",
    act: {
      missing_attribute: (l) => `Add ${l}, if you can verify it`,
      readable: (l) => `Make your ${l} readable by machines`,
      description: () => "Describe the product in more detail, with facts you can verify",
      structured_data: () => "Add schema.org markup that matches your visible page",
      price: () => "Check your price is correct and the page explains it",
      language: () => "Declare your page language",
    },
    ev: {
      missing_attribute: (e) => `${e.peers_with_attribute} of ${e.of} top-ranked similar shirts state it.`,
      description: (e) => `Your description: ${e.target_chars} characters. Median of the top ${e.of}: ${Math.round(e.peer_median_chars)}.`,
      structured_data: (e) => `${e.peers_present} of ${e.of} top-ranked similar shirts have it.`,
      price: (e) => `Middle half of ${e.peer_count} comparable listings: ${e.p25}–${e.p75} (median ${e.median}). Positioning evidence, not a recommended price.`,
      language: () => "No <html lang> found, so we can't compare you with products in your language.",
    },
    saved: "Saved.", badUrl: "Enter a valid http(s) URL.", denied: "Host permission denied; requests to this API will fail.",
    oApi: "API base URL", oToken: "Profile token (optional)", oTokenHelp: "Sent as the X-Profile-Token header. Stored only in this browser.",
    oLang: "Language", oAuto: "Browser default", save: "Save",
  },
  es: {
    settings: "Ajustes", audit: "Auditar este producto", draft: "Auditar como borrador",
    auditing: "Auditando…", reading: "Leyendo el título y la descripción de la página…",
    needPage: "Abre primero una página de producto (http/https).",
    unreachable: (b) => `No se puede conectar con la API en ${b}. ¿Está en marcha? Revisa los Ajustes.`,
    blocked: "Esta tienda bloqueó nuestra descarga. Puedes auditarla como borrador: leemos el título y la descripción visibles de esta pestaña (solo ahora, en tu navegador) y los enviamos a la API.",
    amazon: "La API no puede descargar páginas de Amazon. Audítala como borrador: leemos el título y la descripción visibles de esta pestaña (solo ahora, en tu navegador).",
    draftNote: "Auditado como borrador a partir del título y la descripción visibles. El marcado de la página no se puntúa.",
    apiError: (s, t) => `Error de la API ${s}: ${t}`,
    badJson: "La API devolvió un JSON no válido.",
    noTitle: "No se encontró el título del producto en esta página.",
    rankHead: "Calidad del anuncio",
    rank: (k, n, t) => `#${k} de ${n} ${t} similares`,
    noPeers: (t) => `Aún no hay ${t} comparables en nuestros datos.`,
    shirts: "camisetas", score: (s) => `Puntuación ${s}/100 (completitud de la página, no un ranking de búsqueda ni de IA).`,
    fixHead: "Corrige esto primero", noFix: "Nada que corregir frente a las camisetas similares mejor clasificadas.",
    missingHead: "Atributos que faltan", missingOf: (c, n) => `${c} de ${n} camisetas top lo indican`,
    notFoundNote: "No encontrado en tu página; no significa que el producto no lo tenga.",
    priceHead: "Posición de precio",
    pos: { below: "Por debajo del rango habitual", within: "Dentro del rango habitual", above: "Por encima del rango habitual" },
    priceLine: (p, c, a, b, m, n) => `${p} ${c} frente a ${a}–${b} ${c} (mediana ${m}, ${n} anuncios comparables)`,
    noPrice: "No hay suficientes precios comparables para situar el tuyo.",
    visHead: "Visibilidad en IA", visBody: "Aún no se ha ejecutado.",
    compare: "Comparar con modelos de IA", report: "Abrir informe completo",
    act: {
      missing_attribute: (l) => `Añade ${l}, si puedes verificarlo`,
      readable: (l) => `Haz que ${l} sea legible por máquinas`,
      description: () => "Describe el producto con más detalle, con datos verificables",
      structured_data: () => "Añade marcado schema.org que coincida con tu página visible",
      price: () => "Comprueba que el precio es correcto y que la página lo explica",
      language: () => "Declara el idioma de tu página",
    },
    ev: {
      missing_attribute: (e) => `${e.peers_with_attribute} de ${e.of} camisetas similares mejor clasificadas lo indican.`,
      description: (e) => `Tu descripción: ${e.target_chars} caracteres. Mediana de las ${e.of} mejores: ${Math.round(e.peer_median_chars)}.`,
      structured_data: (e) => `${e.peers_present} de ${e.of} camisetas similares mejor clasificadas lo tienen.`,
      price: (e) => `Mitad central de ${e.peer_count} anuncios comparables: ${e.p25}–${e.p75} (mediana ${e.median}). Es evidencia de posición, no un precio recomendado.`,
      language: () => "No se encontró <html lang>, así que no podemos compararte con productos en tu idioma.",
    },
    saved: "Guardado.", badUrl: "Introduce una URL http(s) válida.", denied: "Permiso de host denegado; las peticiones a esta API fallarán.",
    oApi: "URL base de la API", oToken: "Token de perfil (opcional)", oTokenHelp: "Se envía en la cabecera X-Profile-Token. Solo se guarda en este navegador.",
    oLang: "Idioma", oAuto: "Idioma del navegador", save: "Guardar",
  },
};

// Spanish attribute labels; English comes from the API's `label`.
const LABEL_ES = {
  "identity.brand": "la marca", "identity.audience": "a quién va dirigido (hombre, mujer, unisex)",
  "identity.subcategory": "la categoría", "content.full_description": "la descripción",
  "materials.primary_material": "el material principal", "materials.material_percentages": "la composición (%)",
  "materials.fabric_type": "el tipo de tejido", "materials.fabric_weight_gsm": "el gramaje (g/m²)",
  "materials.stretch": "la elasticidad", "materials.texture": "la textura", "fit_and_style.fit": "el corte",
  "fit_and_style.neckline": "el cuello", "fit_and_style.collar_type": "el tipo de cuello",
  "fit_and_style.sleeve_length": "el largo de manga", "fit_and_style.shirt_length": "el largo",
  "fit_and_style.pattern": "el estampado", "fit_and_style.style": "el estilo", "variants.colors": "los colores",
  "variants.sizes": "las tallas", "commerce.price": "el precio", "commerce.currency": "la moneda",
  "commerce.availability": "la disponibilidad", "commerce.gtin": "el código de barras (GTIN/EAN)",
};

function el(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k in e) e[k] = v;
    else e.setAttribute(k, v);
  }
  e.append(...kids.filter((k) => k != null));
  return e;
}
