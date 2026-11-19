/**
 * Motor Serverless em Navegador para o Hub Ita Arte 3D (GitHub Pages).
 * Carrega os dados iniciais de ./seed_hub.json e persiste alterações no IndexedDB local.
 */

const IDB_NAME = "ItaArte3DHubDB";
const IDB_STORE = "kv";
const IDB_KEY = "hub_state_v2";
const LEGACY_IDB_KEY = "hub_state_v1";
const SEED_URL = "./seed_hub.json";

let memState = null;
let initPromise = null;

function nowIso() {
  return new Date().toISOString();
}

function openIdb() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB indisponível"));
      return;
    }
    const req = indexedDB.open(IDB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(IDB_STORE)) {
        db.createObjectStore(IDB_STORE);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error("Erro ao abrir IndexedDB"));
  });
}

async function idbGet(key) {
  try {
    const db = await openIdb();
    return await new Promise((resolve) => {
      const tx = db.transaction(IDB_STORE, "readonly");
      const req = tx.objectStore(IDB_STORE).get(key);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

async function idbSet(key, val) {
  try {
    const db = await openIdb();
    await new Promise((resolve) => {
      const tx = db.transaction(IDB_STORE, "readwrite");
      tx.objectStore(IDB_STORE).put(val, key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  } catch {
    // Fallback em memória já mantido em memState
  }
}

async function loadState() {
  if (memState) return memState;
  if (!initPromise) {
    initPromise = (async () => {
      const savedV2 = await idbGet(IDB_KEY);
      if (
        savedV2 &&
        savedV2.meta &&
        Array.isArray(savedV2.models) &&
        savedV2.models.length >= 100 &&
        Array.isArray(savedV2.nichos) &&
        savedV2.nichos.length > 0
      ) {
        savedV2.customers = savedV2.customers || [];
        savedV2.suppliers = savedV2.suppliers || [];
        savedV2.purchases = savedV2.purchases || [];
        savedV2.kits = savedV2.kits || [];
        savedV2.quotes = savedV2.quotes || [];
        memState = savedV2;
        return memState;
      }

      const res = await fetch(SEED_URL);
      if (!res.ok) {
        throw new Error(`Falha ao carregar ${SEED_URL} (HTTP ${res.status})`);
      }
      const seed = await res.json();
      const legacyV1 = await idbGet(LEGACY_IDB_KEY);
      const base = legacyV1 && legacyV1.meta && Array.isArray(legacyV1.models) ? legacyV1 : seed;

      memState = {
        meta: seed.meta || base.meta || {},
        models: base.models || [],
        printers: base.printers || [],
        spools: base.spools || [],
        rubrics: base.rubrics || [],
        slicing_profiles: base.slicing_profiles || [],
        subcategories: base.subcategories || [],
        catalog: base.catalog || [],
        jobs: base.jobs || [],
        sales: base.sales || [],
        media: base.media || [],
        nichos: base.nichos || seed.nichos || [],
        customers: base.customers || seed.customers || [],
        suppliers: base.suppliers || seed.suppliers || [],
        purchases: base.purchases || seed.purchases || [],
        kits: base.kits || seed.kits || [],
        quotes: base.quotes || seed.quotes || [],
      };
      await idbSet(IDB_KEY, memState);
      return memState;
    })();
  }
  return initPromise;
}

async function persistState(st) {
  memState = st;
  await idbSet(IDB_KEY, st);
}

function nextId(arr) {
  if (!arr || !arr.length) return 1;
  return Math.max(...arr.map((x) => Number(x.id || 0))) + 1;
}

function normalizeUrl(raw) {
  const s = String(raw || "").trim();
  if (!s) return "";
  try {
    const u = new URL(s);
    u.hash = "";
    return u.toString().replace(/\/$/, "");
  } catch {
    return s.split("#")[0].split("?")[0];
  }
}

function extractUrls(text) {
  const matches = String(text || "").match(/https?:\/\/[^\s"'<>()]+/gi) || [];
  const seen = new Set();
  const out = [];
  for (const m of matches) {
    const clean = normalizeUrl(m.replace(/[.,;!?]+$/, ""));
    if (clean && !seen.has(clean)) {
      seen.add(clean);
      out.push(clean);
    }
  }
  return out;
}

function inferModelAttributes(url, explicit = {}) {
  const low = `${url} ${explicit.title || ""} ${(explicit.tags || []).join(" ")}`.toLowerCase();
  let source = "Web";
  let external_id = "";
  if (low.includes("makerworld.com")) {
    source = "MakerWorld";
    const m = url.match(/models\/(\d+)/);
    if (m) external_id = m[1];
  } else if (low.includes("printables.com")) {
    source = "Printables";
    const m = url.match(/model\/(\d+)/);
    if (m) external_id = m[1];
  } else if (low.includes("thingiverse.com")) {
    source = "Thingiverse";
    const m = url.match(/thing:(\d+)/);
    if (m) external_id = m[1];
  }

  let title = String(explicit.title || "").trim();
  if (!title) {
    const slug = url.split("?")[0].split("/").filter(Boolean).pop() || "Modelo 3D";
    title = decodeURIComponent(slug)
      .replace(/^\d+-?/, "")
      .replace(/[-_]+/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase())
      .trim() || "Modelo 3D";
  }

  let category = explicit.category || "Decoração";
  let subcategory = explicit.subcategory || "";
  if (!explicit.category) {
    if (/(themis|temis|justica|justiça|advog|direito|malhete|oab|balanca|balança)/.test(low)) {
      category = "Direito & Advocacia";
      subcategory = "Estátuas & Símbolos";
    } else if (/(medicin|estetosc|coracao|coração|anatomia|enferm|odonto|dent)/.test(low)) {
      category = "Medicina & Saúde";
    } else if (/(gridfinity|organizer|organizador|porta|suporte|holder|hook|gancho|headset|desk)/.test(low)) {
      category = "Organizadores & Utilitários";
      subcategory = "Mesa & Escritório";
    } else if (/(dragon|dragao|dragão|flexi|articulated|articulado|fidget|toy|brinquedo|pokemon|anime|goku|batman|marvel)/.test(low)) {
      category = "Geek, Miniaturas & Articulados";
      subcategory = "Articulados & Flexi";
    } else if (/(chaveiro|keychain|lembranc|placa|pix)/.test(low)) {
      category = "Chaveiros & Lembrancinhas";
    } else if (/(vaso|planter|cachepot|luminaria|luminária|lamp|estatua|estátua|busto)/.test(low)) {
      category = "Decoração";
      subcategory = "Vasos & Luminárias";
    }
  }

  const grams = explicit.filament_grams != null ? Number(explicit.filament_grams) : 65;
  const maxDim = explicit.max_dimension_mm != null ? Number(explicit.max_dimension_mm) : 140;
  let size_tier = explicit.size_tier || "Médio";
  if (!explicit.size_tier) {
    if (maxDim <= 80 || grams <= 45) size_tier = "Pequeno";
    else if (maxDim > 180 || grams > 180) size_tier = "Grande";
  }

  const filaments = Array.isArray(explicit.recommended_filaments) && explicit.recommended_filaments.length
    ? explicit.recommended_filaments
    : (/(externo|sol|chuv|mecan|engren|suporte pesado|bracket)/.test(low) ? ["PETG", "PLA+"] : ["PLA", "PLA+"]);

  const colors = Array.isArray(explicit.recommended_colors) && explicit.recommended_colors.length
    ? explicit.recommended_colors
    : (/(dragon|multicolor|ams|rainbow|bicolor)/.test(low)
        ? ["Multicolor / Todas as Cores"]
        : ["Preto", "Branco", "Multicolor / Todas as Cores"]);

  const classifications = Array.isArray(explicit.classifications) && explicit.classifications.length
    ? explicit.classifications
    : [{ category, subcategory }];

  const now = nowIso();
  return {
    url,
    source,
    external_id,
    title,
    image_url: explicit.image_url || "",
    category: classifications[0].category,
    subcategory: classifications[0].subcategory || "",
    classifications,
    categories: Array.from(new Set(classifications.map((c) => c.category))),
    subcategories: Array.from(new Set(classifications.map((c) => c.subcategory).filter(Boolean))),
    tags: Array.isArray(explicit.tags) ? explicit.tags.slice(0, 8) : [],
    size_tier,
    dimensions_mm: explicit.dimensions_mm || "",
    max_dimension_mm: maxDim,
    filament_grams: grams,
    print_time_min: explicit.print_time_min != null ? Number(explicit.print_time_min) : 95,
    recommended_filaments: filaments,
    filament_reason: explicit.filament_reason || "Classificação automática por palavras-chave do link/título.",
    recommended_colors: colors,
    status: explicit.status || "Na Fila",
    notes: explicit.notes || "",
    collected_at: explicit.collected_at || now,
    updated_at: now,
  };
}

function ensureSubcategory(st, scope, category, name) {
  const cat = String(category || "").trim();
  const sub = String(name || "").trim();
  if (!cat || !sub) return;
  const exists = st.subcategories.some((s) => s.scope === scope && s.category === cat && s.name === sub);
  if (!exists) {
    const ts = nowIso();
    st.subcategories.push({
      id: nextId(st.subcategories),
      scope,
      category: cat,
      name: sub,
      sort_order: 0,
      created_at: ts,
      updated_at: ts,
    });
  }
}

function computeCatalogPrices(data) {
  const grams = Number(data.filament_grams || 0);
  const costPerKg = Number(data.filament_cost_per_kg_brl || 120);
  const energy = Number(data.energy_and_wear_brl || 0);
  const extras = Number(data.extras_cost_brl || 0);
  const filamentCost = (grams / 1000) * costPerKg;
  const unitCost = Math.round((filamentCost + energy + extras) * 100) / 100;
  const mode = data.pricing_mode || "rate_per_gram";
  const rate = Number(data.rate_per_gram_brl || 0.4);
  const margin = Number(data.margin_percent || 150);

  let salePrice = Number(data.sale_price_brl || 0);
  if (mode === "rate_per_gram") {
    salePrice = Math.round((grams * rate + extras) * 100) / 100;
  } else if (mode === "cost_markup") {
    salePrice = Math.round(unitCost * (1 + margin / 100) * 100) / 100;
  }
  const profit = Math.round((salePrice - unitCost) * 100) / 100;
  return { unit_cost_brl: unitCost, sale_price_brl: salePrice, estimated_profit_brl: profit };
}

function enrichSpool(s) {
  const initG = Math.max(1, Number(s.initial_grams || 1000));
  const remG = Math.max(0, Number(s.remaining_grams ?? initG));
  const minG = Number(s.min_alert_grams ?? 150);
  const costKg = Number(s.cost_per_kg_brl ?? 120);
  return {
    ...s,
    initial_grams: initG,
    remaining_grams: remG,
    min_alert_grams: minG,
    cost_per_kg_brl: costKg,
    is_low_stock: remG <= minG,
    percent_remaining: Math.min(100, Math.round((remG / initG) * 1000) / 10),
    estimated_value_brl: Math.round((remG / 1000) * costKg * 100) / 100,
  };
}

function enrichPrinter(st, p) {
  const active = st.jobs.filter((j) => j.printer_id === p.id && j.status === "Em Impressão").length;
  const queued = st.jobs.filter((j) => j.printer_id === p.id && j.status === "Pendente").length;
  return { ...p, active_jobs_count: active, queued_jobs_count: queued };
}

function enrichJob(st, j) {
  const printer = st.printers.find((p) => p.id === j.printer_id);
  const rubric = st.rubrics.find((r) => r.id === j.rubric_id);
  const slicing = st.slicing_profiles.find((s) => s.id === j.slicing_profile_id);
  const spool = st.spools.find((s) => s.id === j.spool_id);
  const spoolRem = spool ? Number(spool.remaining_grams) : null;
  const est = Number(j.estimated_grams || 0);
  return {
    ...j,
    printer_name: printer ? printer.name : "",
    rubric_name: rubric ? rubric.name : (j.rubric_name || ""),
    rubric_color: rubric ? rubric.color_hex : "#22d3ee",
    slicing_profile_name: slicing ? slicing.name : "",
    layer_height_mm: slicing ? slicing.layer_height_mm : j.layer_height_mm,
    spool_label: spool ? `${spool.material} ${spool.color_name}` : "",
    spool_remaining_grams: spoolRem,
    filament_ok: spoolRem == null ? true : spoolRem >= est,
  };
}

function buildSummary(st) {
  const archivedModels = st.models.filter((m) => m.status === "Arquivado").length;
  const archivedJobs = st.jobs.filter((j) => j.status === "Arquivado").length;
  const spools = st.spools.map(enrichSpool);
  return {
    models_total: st.models.length,
    models_active: st.models.length - archivedModels,
    archived_models: archivedModels,
    archived_jobs: archivedJobs,
    archived_total: archivedModels + archivedJobs,
    queue_pending: st.jobs.filter((j) => j.status === "Pendente").length,
    queue_active: st.jobs.filter((j) => j.status === "Em Impressão").length,
    printers_total: st.printers.length,
    printers_busy: st.printers.filter((p) => p.status === "Imprimindo").length,
    spools_total: spools.length,
    spools_low: spools.filter((s) => s.is_low_stock).length,
    spools_grams: Math.round(spools.reduce((a, s) => a + s.remaining_grams, 0) * 10) / 10,
    catalog_total: st.catalog.length,
    ready_stock_units: st.catalog.reduce((a, c) => a + Number(c.stock_qty || 0), 0),
    sales_total: st.sales.length,
    sales_revenue_brl: Math.round(st.sales.reduce((a, s) => a + Number(s.total_price_brl || 0), 0) * 100) / 100,
    media_total: st.media.length,
    media_ready: st.media.filter((m) => m.status === "Legenda Pronta" || m.status === "Agendado").length,
    customers_total: (st.customers || []).length,
    quotes_open: (st.quotes || []).filter((q) => q.status === "Rascunho" || q.status === "Enviada").length,
    suppliers_total: (st.suppliers || []).length,
    kits_total: (st.kits || []).length,
  };
}

function computeQuoteMetrics(data) {
  const qty = Math.max(1, Number(data.quantity || 1));
  const grams = Math.max(0, Number(data.grams || 0));
  const timeMin = Math.max(0, Number(data.time_min || 0));
  const costKg = Math.max(0, Number(data.spool_cost_per_kg_brl ?? 120));
  const hourly = Math.max(0, Number(data.printer_hourly_cost_brl ?? 2.5));
  const energyWear = Math.max(0, Number(data.energy_wear_brl ?? 1.5));
  const extras = Math.max(0, Number(data.extras_brl ?? 0));
  const mode = data.pricing_mode || "cost_markup";
  const rateG = Math.max(0, Number(data.rate_per_gram_brl ?? 0.45));
  const marginPct = Math.max(0, Number(data.margin_percent ?? 160));

  const filamentCost = Math.round(((grams / 1000) * costKg) * 100) / 100;
  const machineCost = Math.round((((timeMin / 60) * hourly) + energyWear) * 100) / 100;
  const unitCost = Math.round((filamentCost + machineCost + extras) * 100) / 100;

  let unitPrice = Number(data.unit_price_brl || 0);
  if (mode === "rate_per_gram") {
    unitPrice = Math.round((grams * rateG + extras) * 100) / 100;
  } else if (mode === "cost_markup") {
    unitPrice = Math.round((unitCost * (1 + marginPct / 100)) * 100) / 100;
  }
  const totalPrice = Math.round((unitPrice * qty) * 100) / 100;
  const profit = Math.round((totalPrice - unitCost * qty) * 100) / 100;
  return {
    filament_cost_brl: filamentCost,
    machine_cost_brl: machineCost,
    unit_cost_brl: unitCost,
    unit_price_brl: unitPrice,
    total_price_brl: totalPrice,
    estimated_profit_brl: profit,
  };
}

function buildErpDashboard(st) {
  const sum = buildSummary(st);
  const spools = (st.spools || []).map(enrichSpool);
  const lowSpools = spools.filter((s) => s.is_low_stock);
  const lowProducts = (st.catalog || []).filter((c) => c.active !== false && Number(c.stock_qty || 0) <= Number(c.min_stock_alert ?? 1));
  const sales = st.sales || [];
  const totalRevenue = sales.reduce((a, s) => a + Number(s.total_price_brl || 0), 0);
  const estimatedCost = sales.reduce((a, s) => {
    const cat = (st.catalog || []).find((c) => Number(c.id) === Number(s.catalog_item_id));
    const unitC = Number(s.unit_cost_brl ?? cat?.unit_cost_brl ?? Number(s.unit_price_brl || 0) * 0.4);
    return a + unitC * Number(s.quantity || 1);
  }, 0);
  const curMonth = String(new Date().getMonth() + 1).padStart(2, "0");
  const birthdayCustomers = (st.customers || []).filter((c) => {
    const b = String(c.birthday || "").trim();
    if (!b) return false;
    const parts = b.split(/[/-]/);
    return parts.length >= 2 && parts[1].padStart(2, "0") === curMonth;
  });

  const ordersByStatus = {};
  for (const s of sales) {
    const k = s.fulfillment_status || "Pendente";
    ordersByStatus[k] = (ordersByStatus[k] || 0) + 1;
  }

  return {
    ...sum,
    revenue_brl: Math.round(totalRevenue * 100) / 100,
    estimated_profit_brl: Math.round((totalRevenue - estimatedCost) * 100) / 100,
    low_spools: lowSpools,
    low_products: lowProducts.slice(0, 12),
    low_products_count: lowProducts.length,
    birthday_customers: birthdayCustomers,
    orders_by_status: ordersByStatus,
    recent_orders: sales.slice(0, 8),
    recent_quotes: (st.quotes || []).slice(0, 6),
    active_jobs: (st.jobs || []).map((j) => enrichJob(st, j)).filter((j) => j.status === "Em Impressão" || j.status === "Pendente").slice(0, 8),
  };
}

export async function exportFullHubBackupJson() {
  const st = await loadState();
  return JSON.stringify(st, null, 2);
}

export async function importFullHubBackupJson(data) {
  if (!data || typeof data !== "object" || !Array.isArray(data.models)) {
    throw new Error("Arquivo JSON inválido para backup do sistema.");
  }
  const st = await loadState();
  const next = {
    meta: data.meta || st.meta,
    models: data.models || st.models,
    printers: data.printers || st.printers,
    spools: data.spools || st.spools,
    rubrics: data.rubrics || st.rubrics,
    slicing_profiles: data.slicing_profiles || st.slicing_profiles,
    subcategories: data.subcategories || st.subcategories,
    catalog: data.catalog || st.catalog,
    jobs: data.jobs || st.jobs,
    sales: data.sales || st.sales,
    media: data.media || st.media,
    nichos: data.nichos || st.nichos,
    customers: data.customers || st.customers,
    suppliers: data.suppliers || st.suppliers,
    purchases: data.purchases || st.purchases,
    kits: data.kits || st.kits,
    quotes: data.quotes || st.quotes,
  };
  await persistState(next);
  return buildSummary(next);
}

export async function getFullErpState() {
  return loadState();
}

export async function mergeRemoteErpData(remote) {
  if (!remote || typeof remote !== "object") return;
  const st = await loadState();
  if (Array.isArray(remote.customers) && remote.customers.length) st.customers = remote.customers;
  if (Array.isArray(remote.quotes) && remote.quotes.length) st.quotes = remote.quotes;
  if (Array.isArray(remote.sales) && remote.sales.length) st.sales = remote.sales;
  if (Array.isArray(remote.suppliers) && remote.suppliers.length) st.suppliers = remote.suppliers;
  if (Array.isArray(remote.jobs) && remote.jobs.length) st.jobs = remote.jobs;
  await persistState(st);
  return buildSummary(st);
}

function generateCaptionData({ title = "", category = "", price_brl = null, notes = "" }) {
  const cleanTitle = title.trim() || "Peça Exclusiva em Impressão 3D";
  const priceLine = price_brl ? `\n💰 Por apenas ${Number(price_brl).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}` : "";
  const extra = notes ? `\n✨ ${notes}` : "";
  const caption =
    `✨ Novidade na Ita Arte 3D!\n\n` +
    `🖨️ ${cleanTitle}${category ? ` (${category})` : ""}\n` +
    `Produzido em impressão 3D de alta precisão, acabamento caprichado e personalizável na sua cor favorita!${extra}${priceLine}\n\n` +
    `📲 Peça a sua pelo Direct ou WhatsApp! Enviamos para todo o Brasil.`;
  const baseTags = ["#ItaArte3D", "#Impressao3D", "#PresentePersonalizado", "#3DPrintBrasil", "#BambuLabA1"];
  if (category) baseTags.push("#" + category.replace(/[^a-zA-Z0-9]/g, ""));
  return { caption, hashtags: baseTags.join(" ") };
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Falha ao ler arquivo local"));
    reader.readAsDataURL(file);
  });
}

function parseBody(options) {
  if (!options || !options.body) return {};
  if (typeof options.body === "string") {
    try { return JSON.parse(options.body); } catch { return {}; }
  }
  return {};
}

function httpError(detail) {
  const err = new Error(detail);
  err.detail = detail;
  throw err;
}

export async function getPublicCatalogSnapshot() {
  const st = await loadState();
  return st.catalog || [];
}

export async function handleServerlessApi(rawUrl, options = {}) {
  const st = await loadState();
  const method = String(options.method || "GET").toUpperCase();
  const parsed = new URL(rawUrl, window.location.origin);
  const path = parsed.pathname;
  const qp = parsed.searchParams;

  // ---- Health & Summary & Meta ---- //
  if (path === "/api/health") return { status: "ok", mode: "serverless-github-pages" };
  if (path === "/api/hub/summary") return buildSummary(st);
  if (path === "/api/catalog-meta") return st.meta;

  // ---- 1. Models ---- //
  if (path === "/api/import/batch" && method === "POST") {
    const body = parseBody(options);
    const byUrl = new Map();
    for (const u of extractUrls(body.raw_text || "")) byUrl.set(u, { url: u });
    for (const rawU of body.urls || []) {
      for (const u of extractUrls(rawU)) if (!byUrl.has(u)) byUrl.set(u, { url: u });
    }
    for (const it of body.items || []) {
      const norm = normalizeUrl(it?.url);
      if (norm) byUrl.set(norm, { ...it, url: norm });
    }
    if (!byUrl.size) httpError("Nenhum link HTTP/HTTPS válido encontrado para importar.");

    const saved = [];
    for (const entry of byUrl.values()) {
      const analyzed = inferModelAttributes(entry.url, entry);
      const idx = st.models.findIndex((m) => m.url === analyzed.url);
      if (idx >= 0) {
        st.models[idx] = { ...st.models[idx], ...analyzed, id: st.models[idx].id };
        saved.push(st.models[idx]);
      } else {
        const created = { id: nextId(st.models), ...analyzed };
        st.models.unshift(created);
        saved.push(created);
      }
      for (const p of analyzed.classifications) {
        ensureSubcategory(st, "models", p.category, p.subcategory);
      }
    }
    await persistState(st);
    return { count: saved.length, items: saved };
  }

  if (path === "/api/seed-demo" && method === "POST") {
    const demos = [
      { url: "https://makerworld.com/en/models/120001-articulated-crystal-dragon", title: "Articulated Crystal Dragon (Exemplo)", filament_grams: 118, dimensions_mm: "210 x 145 x 55 mm", print_time_min: 215, tags: ["dragon", "articulated", "ams", "flexi"] },
      { url: "https://makerworld.com/en/models/120002-gridfinity-screw-organizer", title: "Gridfinity Modular Screw Organizer (Exemplo)", filament_grams: 74, dimensions_mm: "126 x 84 x 42 mm", print_time_min: 110, tags: ["gridfinity", "organizer", "storage"] },
      { url: "https://makerworld.com/en/models/120003-heavy-duty-headset-clamp", title: "Heavy Duty Desk Headset Clamp (Exemplo)", filament_grams: 48, dimensions_mm: "78 x 45 x 62 mm", print_time_min: 75, tags: ["headset", "clamp", "desk"] },
    ];
    const saved = [];
    for (const d of demos) {
      const analyzed = inferModelAttributes(d.url, d);
      const idx = st.models.findIndex((m) => m.url === analyzed.url);
      if (idx >= 0) {
        st.models[idx] = { ...st.models[idx], ...analyzed };
        saved.push(st.models[idx]);
      } else {
        const created = { id: nextId(st.models), ...analyzed };
        st.models.unshift(created);
        saved.push(created);
      }
    }
    await persistState(st);
    return { count: saved.length, items: saved };
  }

  if (path === "/api/models/enrich-missing" && method === "POST") {
    const totalMissing = st.models.filter((m) => !m.image_url).length;
    return { requested: totalMissing, enriched: 0, total_missing: totalMissing, next_offset: totalMissing, has_more_missing: false };
  }

  let mMatch = path.match(/^\/api\/models\/(\d+)\/enrich$/);
  if (mMatch && method === "POST") {
    httpError("No modo estático do GitHub Pages, o MakerWorld bloqueia leitura direta por CORS. Cole o link da imagem no campo ou rode o sistema local.");
  }

  if (path === "/api/models" && method === "GET") {
    const q = (qp.get("q") || "").trim().toLowerCase();
    const status = qp.get("status") || "";
    const category = qp.get("category") || "";
    const subcategory = qp.get("subcategory") || "";
    const sizeTier = qp.get("size_tier") || "";
    const filament = qp.get("filament") || "";
    const color = qp.get("color") || "";
    const includeMulti = qp.get("include_multicolor") === "true";
    const excludeArchived = qp.get("exclude_archived") === "true";
    const maxDim = qp.get("max_dimension_mm") ? Number(qp.get("max_dimension_mm")) : null;
    const minGrams = qp.get("min_grams") ? Number(qp.get("min_grams")) : null;
    const maxGrams = qp.get("max_grams") ? Number(qp.get("max_grams")) : null;
    const fromDt = qp.get("collected_from") ? new Date(qp.get("collected_from")).getTime() : null;
    const toDt = qp.get("collected_to") ? new Date(qp.get("collected_to")).getTime() : null;
    const sortKey = qp.get("sort") || "collected_desc";
    const limit = qp.get("limit") ? Number(qp.get("limit")) : null;
    const offset = Math.max(0, Number(qp.get("offset") || 0));
    const multiLabel = st.meta?.multicolor_label || "Multicolor / Todas as Cores";

    let filtered = st.models.filter((item) => {
      if (q) {
        const hay = [item.title, item.category, item.subcategory, ...(item.categories || []), ...(item.subcategories || []), item.url, item.notes, item.filament_reason, ...(item.tags || [])].join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (status) {
        if (item.status !== status) return false;
      } else if (excludeArchived && item.status === "Arquivado") {
        return false;
      }
      const cls = item.classifications || [];
      if (category && subcategory) {
        if (!cls.some((c) => c.category === category && c.subcategory === subcategory)) return false;
      } else if (category) {
        if (!(item.categories || [item.category]).includes(category)) return false;
      } else if (subcategory) {
        if (!(item.subcategories || [item.subcategory]).includes(subcategory)) return false;
      }
      if (sizeTier && item.size_tier !== sizeTier) return false;
      if (fromDt || toDt) {
        const t = new Date(item.collected_at).getTime();
        if (Number.isNaN(t)) return false;
        if (fromDt && t < fromDt) return false;
        if (toDt && t > toDt) return false;
      }
      if (maxDim != null && (item.max_dimension_mm == null || Number(item.max_dimension_mm) > maxDim)) return false;
      if (minGrams != null && (item.filament_grams == null || Number(item.filament_grams) < minGrams)) return false;
      if (maxGrams != null && (item.filament_grams == null || Number(item.filament_grams) > maxGrams)) return false;
      if (filament && !(item.recommended_filaments || []).includes(filament)) return false;
      if (color) {
        const cols = item.recommended_colors || [];
        if (color === multiLabel) {
          if (!cols.includes(multiLabel)) return false;
        } else {
          const ok = cols.includes(color) || (includeMulti && cols.includes(multiLabel));
          if (!ok) return false;
        }
      }
      return true;
    });

    filtered.sort((a, b) => {
      if (sortKey === "collected_asc") return String(a.collected_at).localeCompare(String(b.collected_at));
      if (sortKey === "grams_asc") return (a.filament_grams ?? 1e9) - (b.filament_grams ?? 1e9);
      if (sortKey === "grams_desc") return (b.filament_grams ?? -1) - (a.filament_grams ?? -1);
      if (sortKey === "size_asc") return (a.max_dimension_mm ?? 1e9) - (b.max_dimension_mm ?? 1e9);
      if (sortKey === "size_desc") return (b.max_dimension_mm ?? -1) - (a.max_dimension_mm ?? -1);
      return String(b.collected_at).localeCompare(String(a.collected_at));
    });

    const total = filtered.length;
    const totalGrams = Math.round(filtered.reduce((acc, m) => acc + Number(m.filament_grams || 0), 0) * 10) / 10;
    const naFila = filtered.filter((m) => m.status === "Na Fila").length;
    const multiCount = filtered.filter((m) => (m.recommended_colors || []).includes(multiLabel)).length;
    const paged = limit && limit > 0 ? filtered.slice(offset, offset + limit) : filtered.slice(offset);
    return {
      items: paged,
      total,
      limit,
      offset,
      has_more: limit && limit > 0 ? offset + paged.length < total : false,
      total_filament_grams: totalGrams,
      stats: { na_fila: naFila, multicolor: multiCount },
    };
  }

  mMatch = path.match(/^\/api\/models\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = st.models.findIndex((m) => Number(m.id) === id);
    if (idx < 0) httpError("Modelo não encontrado.");
    if (method === "DELETE") {
      st.models.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      const body = parseBody(options);
      const cur = st.models[idx];
      const updated = { ...cur, ...body, id: cur.id, updated_at: nowIso() };
      const cls = Array.isArray(updated.classifications) && updated.classifications.length
        ? updated.classifications
        : [{ category: updated.category || "Outros", subcategory: updated.subcategory || "" }];
      updated.classifications = cls;
      updated.category = cls[0].category;
      updated.subcategory = cls[0].subcategory || "";
      updated.categories = Array.from(new Set(cls.map((c) => c.category)));
      updated.subcategories = Array.from(new Set(cls.map((c) => c.subcategory).filter(Boolean)));
      for (const p of cls) ensureSubcategory(st, "models", p.category, p.subcategory);
      st.models[idx] = updated;
      await persistState(st);
      return updated;
    }
  }

  // ---- 2. Printers ---- //
  if (path === "/api/printers") {
    if (method === "GET") {
      const items = st.printers.map((p) => enrichPrinter(st, p));
      return { items, total: items.length };
    }
    if (method === "POST") {
      const body = parseBody(options);
      if (!String(body.name || "").trim()) httpError("Informe o apelido da impressora.");
      const ts = nowIso();
      const created = {
        id: nextId(st.printers),
        name: body.name,
        brand_model: body.brand_model || "Bambu Lab A1",
        build_volume_mm: body.build_volume_mm || "256 x 256 x 256 mm",
        max_dim_mm: Number(body.max_dim_mm || 256),
        nozzle_mm: Number(body.nozzle_mm || 0.4),
        has_ams: body.has_ams ?? Number(body.ams_slots || 0) > 0,
        ams_slots: Number(body.ams_slots ?? 4),
        ams_mapping: body.ams_mapping || [],
        status: body.status || "Disponível",
        hourly_cost_brl: Number(body.hourly_cost_brl ?? 2.5),
        notes: body.notes || "",
        created_at: ts,
        updated_at: ts,
      };
      st.printers.push(created);
      await persistState(st);
      return enrichPrinter(st, created);
    }
  }

  mMatch = path.match(/^\/api\/printers\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = st.printers.findIndex((p) => Number(p.id) === id);
    if (idx < 0) httpError("Impressora não encontrada.");
    if (method === "DELETE") {
      st.printers.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      st.printers[idx] = { ...st.printers[idx], ...parseBody(options), id, updated_at: nowIso() };
      await persistState(st);
      return enrichPrinter(st, st.printers[idx]);
    }
  }

  // ---- 3. Filament Spools ---- //
  if (path === "/api/spools") {
    if (method === "GET") {
      const mat = qp.get("material") || "";
      const lowOnly = qp.get("low_only") === "true";
      let items = st.spools.map(enrichSpool);
      if (mat) items = items.filter((s) => s.material === mat);
      if (lowOnly) items = items.filter((s) => s.is_low_stock);
      return {
        items,
        total: items.length,
        total_remaining_grams: Math.round(items.reduce((a, s) => a + s.remaining_grams, 0) * 10) / 10,
        low_stock_count: items.filter((s) => s.is_low_stock).length,
      };
    }
    if (method === "POST") {
      const body = parseBody(options);
      if (!String(body.color_name || "").trim()) httpError("Informe a cor do carretel.");
      const ts = nowIso();
      const created = enrichSpool({
        id: nextId(st.spools),
        brand: body.brand || "",
        material: body.material || "PLA",
        color_name: body.color_name,
        color_hex: body.color_hex || "#171717",
        initial_grams: Number(body.initial_grams || 1000),
        remaining_grams: body.remaining_grams != null ? Number(body.remaining_grams) : Number(body.initial_grams || 1000),
        min_alert_grams: Number(body.min_alert_grams ?? 150),
        cost_per_kg_brl: Number(body.cost_per_kg_brl ?? 120),
        location: body.location || "",
        notes: body.notes || "",
        created_at: ts,
        updated_at: ts,
      });
      st.spools.push(created);
      await persistState(st);
      return created;
    }
  }

  mMatch = path.match(/^\/api\/spools\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = st.spools.findIndex((s) => Number(s.id) === id);
    if (idx < 0) httpError("Carretel não encontrado.");
    if (method === "DELETE") {
      st.spools.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      st.spools[idx] = enrichSpool({ ...st.spools[idx], ...parseBody(options), id, updated_at: nowIso() });
      await persistState(st);
      return st.spools[idx];
    }
  }

  // ---- 4. Print Queue ---- //
  if (path === "/api/queue") {
    if (method === "GET") {
      const status = qp.get("status") || "";
      const excludeArchived = qp.get("exclude_archived") === "true";
      const unassigned = qp.get("unassigned_printer") === "true";
      const printerId = qp.get("printer_id") ? Number(qp.get("printer_id")) : null;
      const rubricId = qp.get("rubric_id") ? Number(qp.get("rubric_id")) : null;
      const slicingId = qp.get("slicing_profile_id") ? Number(qp.get("slicing_profile_id")) : null;
      const spoolId = qp.get("spool_id") ? Number(qp.get("spool_id")) : null;
      const target = qp.get("target_type") || "";
      const priority = qp.get("priority") || "";
      const q = (qp.get("q") || "").trim().toLowerCase();

      const allEnriched = st.jobs.map((j) => enrichJob(st, j));
      const filtered = allEnriched.filter((j) => {
        if (status) { if (j.status !== status) return false; }
        else if (excludeArchived && j.status === "Arquivado") return false;
        if (unassigned && j.printer_id != null) return false;
        if (printerId != null && j.printer_id !== printerId) return false;
        if (rubricId != null && j.rubric_id !== rubricId) return false;
        if (slicingId != null && j.slicing_profile_id !== slicingId) return false;
        if (spoolId != null && j.spool_id !== spoolId) return false;
        if (target && j.target_type !== target) return false;
        if (priority && j.priority !== priority) return false;
        if (q) {
          const hay = [j.title, j.customer_name, j.rubric_name, j.slicing_profile_name, j.slicing_notes, j.notes].join(" ").toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      });

      const activeJobs = allEnriched.filter((j) => j.status === "Em Impressão");
      const pendingJobs = allEnriched.filter((j) => j.status === "Pendente");
      const doneJobs = allEnriched.filter((j) => j.status === "Concluída");
      return {
        items: filtered,
        total: filtered.length,
        active_count: activeJobs.length,
        pending_count: pendingJobs.length,
        done_count: doneJobs.length,
        total_estimated_grams: Math.round(
          [...activeJobs, ...pendingJobs].reduce((a, j) => a + Number(j.estimated_grams || 0), 0) * 10
        ) / 10,
      };
    }
    if (method === "POST") {
      const body = parseBody(options);
      if (!String(body.title || "").trim()) httpError("Informe o título da peça/trabalho.");
      let rubricId = body.rubric_id ? Number(body.rubric_id) : null;
      const rubricName = String(body.rubric_name || "").trim();
      if (!rubricId && rubricName) {
        let rb = st.rubrics.find((r) => r.name.toLowerCase() === rubricName.toLowerCase());
        if (!rb) {
          const ts = nowIso();
          rb = { id: nextId(st.rubrics), name: rubricName, color_hex: "#22d3ee", notes: "", created_at: ts, updated_at: ts };
          st.rubrics.push(rb);
        }
        rubricId = rb.id;
      }
      const ts = nowIso();
      const created = {
        id: nextId(st.jobs),
        model_id: body.model_id ? Number(body.model_id) : null,
        printer_id: body.printer_id ? Number(body.printer_id) : null,
        spool_id: body.spool_id ? Number(body.spool_id) : null,
        catalog_item_id: body.catalog_item_id ? Number(body.catalog_item_id) : null,
        rubric_id: rubricId,
        rubric_name: rubricName,
        slicing_profile_id: body.slicing_profile_id ? Number(body.slicing_profile_id) : null,
        layer_height_mm: body.layer_height_mm ?? null,
        slicing_notes: body.slicing_notes || "",
        title: body.title,
        target_type: body.target_type || "Encomenda",
        customer_name: body.customer_name || "",
        quantity: Number(body.quantity || 1),
        estimated_grams: Number(body.estimated_grams || 0),
        actual_grams_used: body.actual_grams_used != null ? Number(body.actual_grams_used) : null,
        estimated_time_min: body.estimated_time_min != null ? Number(body.estimated_time_min) : 60,
        priority: body.priority || "Normal",
        status: body.status || "Pendente",
        failure_reason: "",
        notes: body.notes || "",
        created_at: ts,
        updated_at: ts,
      };
      st.jobs.unshift(created);
      await persistState(st);
      return enrichJob(st, created);
    }
  }

  mMatch = path.match(/^\/api\/queue\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = st.jobs.findIndex((j) => Number(j.id) === id);
    if (idx < 0) httpError("Trabalho na fila não encontrado.");
    if (method === "DELETE") {
      st.jobs.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      const body = parseBody(options);
      const prev = st.jobs[idx];
      let rubricId = body.rubric_id !== undefined ? (body.rubric_id ? Number(body.rubric_id) : null) : prev.rubric_id;
      const rubricName = body.rubric_name !== undefined ? String(body.rubric_name || "").trim() : prev.rubric_name;
      if (!rubricId && rubricName) {
        let rb = st.rubrics.find((r) => r.name.toLowerCase() === rubricName.toLowerCase());
        if (!rb) {
          const ts = nowIso();
          rb = { id: nextId(st.rubrics), name: rubricName, color_hex: "#22d3ee", notes: "", created_at: ts, updated_at: ts };
          st.rubrics.push(rb);
        }
        rubricId = rb.id;
      }
      const next = { ...prev, ...body, rubric_id: rubricId, id, updated_at: nowIso() };
      const becameDone = prev.status !== "Concluída" && next.status === "Concluída";
      const becameFail = prev.status !== "Falhou" && next.status === "Falhou";
      if ((becameDone || becameFail) && next.spool_id) {
        const spIdx = st.spools.findIndex((s) => Number(s.id) === Number(next.spool_id));
        if (spIdx >= 0) {
          const used = Number(next.actual_grams_used ?? next.estimated_grams ?? 0);
          st.spools[spIdx] = enrichSpool({
            ...st.spools[spIdx],
            remaining_grams: Math.max(0, Number(st.spools[spIdx].remaining_grams) - used),
            updated_at: nowIso(),
          });
        }
      }
      if (becameDone && next.target_type === "Estoque" && next.catalog_item_id) {
        const cIdx = st.catalog.findIndex((c) => Number(c.id) === Number(next.catalog_item_id));
        if (cIdx >= 0) {
          st.catalog[cIdx].stock_qty = Number(st.catalog[cIdx].stock_qty || 0) + Number(next.quantity || 1);
        }
      }
      if (next.model_id) {
        const mIdx = st.models.findIndex((m) => Number(m.id) === Number(next.model_id));
        if (mIdx >= 0) {
          if (next.status === "Em Impressão") st.models[mIdx].status = "Imprimindo";
          else if (next.status === "Concluída") st.models[mIdx].status = "Impresso";
        }
      }
      st.jobs[idx] = next;
      await persistState(st);
      return enrichJob(st, next);
    }
  }

  // ---- 4b. Rubrics & Slicing & Subcategories ---- //
  if (path === "/api/rubrics") {
    if (method === "GET") {
      return {
        items: st.rubrics.map((r) => ({
          ...r,
          jobs_count: st.jobs.filter((j) => Number(j.rubric_id) === Number(r.id)).length,
        })),
      };
    }
    if (method === "POST") {
      const body = parseBody(options);
      const name = String(body.name || "").trim();
      if (!name) httpError("Informe o nome da rubrica.");
      if (st.rubrics.some((r) => r.name.toLowerCase() === name.toLowerCase())) httpError("Já existe uma rubrica com este nome.");
      const ts = nowIso();
      const created = { id: nextId(st.rubrics), name, color_hex: body.color_hex || "#22d3ee", notes: body.notes || "", created_at: ts, updated_at: ts };
      st.rubrics.push(created);
      await persistState(st);
      return { ...created, jobs_count: 0 };
    }
  }

  mMatch = path.match(/^\/api\/rubrics\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = st.rubrics.findIndex((r) => Number(r.id) === id);
    if (idx < 0) httpError("Rubrica não encontrada.");
    if (method === "DELETE") {
      st.rubrics.splice(idx, 1);
      for (const j of st.jobs) if (Number(j.rubric_id) === id) j.rubric_id = null;
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      st.rubrics[idx] = { ...st.rubrics[idx], ...parseBody(options), id, updated_at: nowIso() };
      await persistState(st);
      return { ...st.rubrics[idx], jobs_count: st.jobs.filter((j) => Number(j.rubric_id) === id).length };
    }
  }

  if (path === "/api/slicing-profiles") {
    if (method === "GET") {
      return { items: [...st.slicing_profiles].sort((a, b) => Number(a.layer_height_mm) - Number(b.layer_height_mm)) };
    }
    if (method === "POST") {
      const body = parseBody(options);
      const ts = nowIso();
      const layer = Number(body.layer_height_mm || 0.2);
      const created = {
        id: nextId(st.slicing_profiles),
        name: String(body.name || "").trim() || `${layer.toFixed(2)} mm`,
        layer_height_mm: layer,
        notes: body.notes || "",
        is_default: Boolean(body.is_default),
        created_at: ts,
        updated_at: ts,
      };
      st.slicing_profiles.push(created);
      await persistState(st);
      return created;
    }
  }

  mMatch = path.match(/^\/api\/slicing-profiles\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = st.slicing_profiles.findIndex((s) => Number(s.id) === id);
    if (idx < 0) httpError("Perfil de fatiamento não encontrado.");
    if (method === "DELETE") {
      st.slicing_profiles.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      st.slicing_profiles[idx] = { ...st.slicing_profiles[idx], ...parseBody(options), id, updated_at: nowIso() };
      await persistState(st);
      return st.slicing_profiles[idx];
    }
  }

  if (path === "/api/subcategories/reclassify" && method === "POST") {
    let mUpdated = 0;
    for (let i = 0; i < st.models.length; i++) {
      const m = st.models[i];
      const inf = inferModelAttributes(m.url, { title: m.title, tags: m.tags });
      if (!m.subcategory && inf.subcategory) {
        st.models[i] = { ...m, subcategory: inf.subcategory, classifications: inf.classifications, subcategories: inf.subcategories };
        mUpdated++;
      }
    }
    await persistState(st);
    return { ok: true, models_updated: mUpdated, catalog_updated: 0 };
  }

  if (path === "/api/subcategories") {
    if (method === "GET") {
      const scope = qp.get("scope") || "";
      const category = qp.get("category") || "";
      let rows = st.subcategories;
      if (scope) rows = rows.filter((s) => s.scope === scope);
      if (category) rows = rows.filter((s) => s.category === category);
      const items = rows.map((s) => {
        const list = s.scope === "models" ? st.models : st.catalog;
        const cnt = list.filter((it) =>
          (it.classifications || [{ category: it.category, subcategory: it.subcategory || "" }]).some(
            (c) => c.category === s.category && (c.subcategory || "") === s.name
          )
        ).length;
        return { ...s, items_count: cnt };
      });
      return { items };
    }
    if (method === "POST") {
      const body = parseBody(options);
      const scope = body.scope || "sales_catalog";
      const category = String(body.category || "").trim();
      const name = String(body.name || "").trim();
      if (!category || !name) httpError("Informe a categoria pai e o nome da subcategoria.");
      if (st.subcategories.some((s) => s.scope === scope && s.category === category && s.name === name)) {
        httpError("Esta subcategoria já existe nesta categoria.");
      }
      const ts = nowIso();
      const created = { id: nextId(st.subcategories), scope, category, name, sort_order: Number(body.sort_order || 0), created_at: ts, updated_at: ts };
      st.subcategories.push(created);
      await persistState(st);
      return { ...created, items_count: 0 };
    }
  }

  mMatch = path.match(/^\/api\/subcategories\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = st.subcategories.findIndex((s) => Number(s.id) === id);
    if (idx < 0) httpError("Subcategoria não encontrada.");
    const cur = st.subcategories[idx];
    if (method === "DELETE") {
      st.subcategories.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      const body = parseBody(options);
      const nextCat = String(body.category || cur.category).trim();
      const nextName = String(body.name || cur.name).trim();
      st.subcategories[idx] = { ...cur, category: nextCat, name: nextName, updated_at: nowIso() };
      const list = cur.scope === "models" ? st.models : st.catalog;
      for (const it of list) {
        if (it.category === cur.category && it.subcategory === cur.name) {
          it.category = nextCat;
          it.subcategory = nextName;
        }
        if (Array.isArray(it.classifications)) {
          for (const c of it.classifications) {
            if (c.category === cur.category && c.subcategory === cur.name) {
              c.category = nextCat;
              c.subcategory = nextName;
            }
          }
        }
      }
      await persistState(st);
      return st.subcategories[idx];
    }
  }

  // ---- 5. Sales Catalog & Orders ---- //
  if (path === "/api/catalog/import-ita-arte" && method === "POST") {
    return { imported: 0 };
  }

  if (path === "/api/catalog") {
    if (method === "GET") {
      const q = (qp.get("q") || "").trim().toLowerCase();
      const category = qp.get("category") || "";
      const subcategory = qp.get("subcategory") || "";
      const inStockOnly = qp.get("in_stock_only") === "true";

      let items = st.catalog.filter((c) => {
        if (q && !`${c.code} ${c.name} ${c.category} ${c.subcategory}`.toLowerCase().includes(q)) return false;
        const cls = c.classifications || [{ category: c.category, subcategory: c.subcategory || "" }];
        if (category && subcategory) {
          if (!cls.some((p) => p.category === category && p.subcategory === subcategory)) return false;
        } else if (category) {
          if (!(c.categories || [c.category]).includes(category)) return false;
        } else if (subcategory) {
          if (!(c.subcategories || [c.subcategory]).includes(subcategory)) return false;
        }
        if (inStockOnly && Number(c.stock_qty || 0) <= 0) return false;
        return true;
      });
      const totalReady = items.reduce((a, c) => a + Number(c.stock_qty || 0), 0);
      const totalStockVal = items.reduce((a, c) => a + Number(c.stock_qty || 0) * Number(c.sale_price_brl || 0), 0);
      return { items, total: items.length, total_ready_units: totalReady, total_stock_value_brl: Math.round(totalStockVal * 100) / 100 };
    }
    if (method === "POST") {
      const body = parseBody(options);
      if (!String(body.name || "").trim()) httpError("Informe o nome do produto.");
      const prices = computeCatalogPrices(body);
      const cls = Array.isArray(body.classifications) && body.classifications.length
        ? body.classifications
        : [{ category: body.category || "Decoração", subcategory: body.subcategory || "" }];
      for (const p of cls) ensureSubcategory(st, "sales_catalog", p.category, p.subcategory);
      const ts = nowIso();
      const created = {
        id: nextId(st.catalog),
        code: body.code || `#${nextId(st.catalog)}`,
        model_id: body.model_id ? Number(body.model_id) : null,
        name: body.name,
        category: cls[0].category,
        subcategory: cls[0].subcategory || "",
        classifications: cls,
        categories: Array.from(new Set(cls.map((c) => c.category))),
        subcategories: Array.from(new Set(cls.map((c) => c.subcategory).filter(Boolean))),
        source_url: body.source_url || "",
        image_url: body.image_url || "",
        dimensions_cm: body.dimensions_cm || "",
        filament_grams: Number(body.filament_grams || 0),
        filament_cost_per_kg_brl: Number(body.filament_cost_per_kg_brl || 120),
        energy_and_wear_brl: Number(body.energy_and_wear_brl || 0),
        extras_cost_brl: Number(body.extras_cost_brl || 0),
        pricing_mode: body.pricing_mode || "rate_per_gram",
        rate_per_gram_brl: Number(body.rate_per_gram_brl || 0.4),
        margin_percent: Number(body.margin_percent || 150),
        ...prices,
        stock_qty: Number(body.stock_qty || 0),
        min_stock_alert: Number(body.min_stock_alert ?? 1),
        active: body.active !== false,
        notes: body.notes || "",
        created_at: ts,
        updated_at: ts,
      };
      st.catalog.unshift(created);
      await persistState(st);
      return created;
    }
  }

  mMatch = path.match(/^\/api\/catalog\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = st.catalog.findIndex((c) => Number(c.id) === id);
    if (idx < 0) httpError("Produto não encontrado no catálogo.");
    if (method === "DELETE") {
      st.catalog.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      const body = parseBody(options);
      const merged = { ...st.catalog[idx], ...body, id, updated_at: nowIso() };
      const prices = computeCatalogPrices(merged);
      const cls = Array.isArray(merged.classifications) && merged.classifications.length
        ? merged.classifications
        : [{ category: merged.category || "Decoração", subcategory: merged.subcategory || "" }];
      for (const p of cls) ensureSubcategory(st, "sales_catalog", p.category, p.subcategory);
      st.catalog[idx] = {
        ...merged,
        ...prices,
        classifications: cls,
        category: cls[0].category,
        subcategory: cls[0].subcategory || "",
        categories: Array.from(new Set(cls.map((c) => c.category))),
        subcategories: Array.from(new Set(cls.map((c) => c.subcategory).filter(Boolean))),
      };
      await persistState(st);
      return st.catalog[idx];
    }
  }

  if (path === "/api/sales") {
    if (method === "GET") {
      const fStatus = qp.get("fulfillment_status") || "";
      const pStatus = qp.get("payment_status") || "";
      const q = (qp.get("q") || "").trim().toLowerCase();
      let list = st.sales;
      if (fStatus) list = list.filter((s) => s.fulfillment_status === fStatus);
      if (pStatus) list = list.filter((s) => s.payment_status === pStatus);
      if (q) {
        list = list.filter((s) =>
          `${s.item_name} ${s.customer_name} ${s.channel} ${s.notes}`.toLowerCase().includes(q)
        );
      }
      const totalRev = list.reduce((a, s) => a + Number(s.total_price_brl || 0), 0);
      return { items: list, total: list.length, total_revenue_brl: Math.round(totalRev * 100) / 100 };
    }
    if (method === "POST") {
      const body = parseBody(options);
      const qty = Math.max(1, Number(body.quantity || 1));
      const catItem = body.catalog_item_id ? st.catalog.find((c) => Number(c.id) === Number(body.catalog_item_id)) : null;
      const kitItem = body.kit_id ? (st.kits || []).find((k) => Number(k.id) === Number(body.kit_id)) : null;
      const custObj = body.customer_id ? (st.customers || []).find((c) => Number(c.id) === Number(body.customer_id)) : null;

      const customerName = String(body.customer_name || custObj?.name || "Consumidor Final").trim();
      const customerWhatsapp = String(body.customer_whatsapp || custObj?.whatsapp || "").trim();
      const itemName = kitItem ? `Kit: ${kitItem.name}` : catItem ? catItem.name : (body.item_name || "Peça / Pedido 3D");
      const unitPrice = body.unit_price_brl != null
        ? Number(body.unit_price_brl)
        : kitItem
          ? Number(kitItem.sale_price_brl || 0)
          : catItem
            ? Number(catItem.sale_price_brl || 0)
            : 0;
      const unitCost = body.unit_cost_brl != null
        ? Number(body.unit_cost_brl)
        : kitItem
          ? Number(kitItem.total_cost_brl || 0)
          : catItem
            ? Number(catItem.unit_cost_brl || 0)
            : 0;
      const discount = Math.max(0, Number(body.discount_brl || 0));
      const freight = Math.max(0, Number(body.freight_brl || 0));
      const total = Math.max(0, Math.round((qty * unitPrice - discount + freight) * 100) / 100);

      let missing = qty;
      let fulfillment = body.fulfillment_status || "Sob Encomenda";
      if (kitItem && Array.isArray(kitItem.items)) {
        let minAvail = qty;
        for (const comp of kitItem.items) {
          const prod = comp.catalog_item_id ? st.catalog.find((c) => Number(c.id) === Number(comp.catalog_item_id)) : null;
          if (prod) {
            const need = qty * Number(comp.qty || 1);
            const avail = Math.max(0, Number(prod.stock_qty || 0));
            const used = Math.min(avail, need);
            prod.stock_qty = avail - used;
            if (used < need) minAvail = 0;
          }
        }
        missing = minAvail >= qty ? 0 : qty;
        if (!body.fulfillment_status) {
          fulfillment = missing === 0 ? "Entregue" : "Na Fila";
        }
      } else if (catItem) {
        const avail = Math.max(0, Number(catItem.stock_qty || 0));
        const usedStock = Math.min(avail, qty);
        catItem.stock_qty = avail - usedStock;
        missing = qty - usedStock;
        if (!body.fulfillment_status) {
          if (missing === 0) fulfillment = "Pronto para Entrega";
          else if (usedStock > 0) fulfillment = "Parcial / Na Fila";
          else fulfillment = "Na Fila";
        }
      } else if (!body.fulfillment_status) {
        fulfillment = body.auto_queue_missing !== false ? "Na Fila" : "Pronto para Entrega";
      }

      let queuedJob = null;
      if (body.auto_queue_missing !== false && missing > 0) {
        const ts = nowIso();
        queuedJob = {
          id: nextId(st.jobs),
          model_id: body.model_id || catItem?.model_id || null,
          printer_id: body.printer_id ? Number(body.printer_id) : null,
          spool_id: body.spool_id ? Number(body.spool_id) : null,
          catalog_item_id: catItem?.id || null,
          rubric_id: st.rubrics[0]?.id || null,
          rubric_name: st.rubrics[0]?.name || "Encomendas Gerais",
          slicing_profile_id: null,
          slicing_notes: "",
          title: itemName,
          target_type: "Encomenda",
          customer_name: customerName,
          quantity: missing,
          estimated_grams: Number(body.estimated_grams || catItem?.filament_grams || 50) * missing,
          estimated_time_min: Number(body.estimated_time_min || 90) * missing,
          priority: "Alta",
          status: "Pendente",
          notes: `Pedido via ${body.channel || "WhatsApp"}${body.notes ? ` • ${body.notes}` : ""}`,
          created_at: ts,
          updated_at: ts,
        };
        st.jobs.unshift(queuedJob);
      }

      const sale = {
        id: nextId(st.sales),
        catalog_item_id: catItem?.id || null,
        kit_id: kitItem?.id || null,
        quote_id: body.quote_id ? Number(body.quote_id) : null,
        customer_id: custObj?.id || null,
        customer_name: customerName,
        customer_whatsapp: customerWhatsapp,
        item_name: itemName,
        channel: body.channel || "WhatsApp",
        quantity: qty,
        unit_price_brl: unitPrice,
        unit_cost_brl: unitCost,
        discount_brl: discount,
        freight_brl: freight,
        total_price_brl: total,
        payment_method: body.payment_method || "Pix",
        payment_status: body.payment_status || "Pendente",
        fulfillment_status: fulfillment,
        linked_job_id: queuedJob?.id || null,
        notes: body.notes || "",
        created_at: nowIso(),
        updated_at: nowIso(),
      };
      st.sales.unshift(sale);
      await persistState(st);
      return { ...sale, queued_job: queuedJob ? enrichJob(st, queuedJob) : null };
    }
  }

  mMatch = path.match(/^\/api\/sales\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = st.sales.findIndex((s) => Number(s.id) === id);
    if (idx < 0) httpError("Venda não encontrada.");
    if (method === "DELETE") {
      st.sales.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      const body = parseBody(options);
      st.sales[idx] = { ...st.sales[idx], ...body, id, updated_at: nowIso() };
      await persistState(st);
      return st.sales[idx];
    }
  }

  // ---- 6. Media & Instagram Studio ---- //
  if (path === "/api/media/generate-caption" && method === "POST") {
    return generateCaptionData(parseBody(options));
  }

  if (path === "/api/media") {
    if (method === "GET") {
      const status = qp.get("status") || "";
      const fmt = qp.get("post_format") || "";
      let items = st.media;
      if (status) items = items.filter((m) => m.status === status);
      if (fmt) items = items.filter((m) => m.post_format === fmt);
      return {
        items,
        total: st.media.length,
        ready_to_post_count: st.media.filter((m) => m.status === "Legenda Pronta" || m.status === "Agendado").length,
        posted_count: st.media.filter((m) => m.status === "Postado").length,
      };
    }
    if (method === "POST") {
      let imageUrl = "";
      let title = "";
      let postFormat = "Feed";
      let status = "Banco de Fotos";
      let catalogId = null;
      let jobId = null;
      let modelId = null;

      if (options.body instanceof FormData) {
        imageUrl = String(options.body.get("image_url") || "").trim();
        title = String(options.body.get("title") || "").trim();
        postFormat = String(options.body.get("post_format") || "Feed");
        status = String(options.body.get("status") || "Banco de Fotos");
        const cRaw = options.body.get("catalog_item_id");
        const jRaw = options.body.get("print_job_id");
        const mRaw = options.body.get("model_id");
        catalogId = cRaw ? Number(cRaw) : null;
        jobId = jRaw ? Number(jRaw) : null;
        modelId = mRaw ? Number(mRaw) : null;
        const file = options.body.get("file");
        if (!imageUrl && file instanceof File) {
          imageUrl = await readFileAsDataUrl(file);
          if (!title) title = file.name.replace(/\.[^.]+$/, "");
        }
      } else {
        const body = parseBody(options);
        imageUrl = String(body.image_url || "").trim();
        title = String(body.title || "").trim();
        postFormat = body.post_format || "Feed";
        status = body.status || "Banco de Fotos";
        catalogId = body.catalog_item_id ? Number(body.catalog_item_id) : null;
        jobId = body.print_job_id ? Number(body.print_job_id) : null;
        modelId = body.model_id ? Number(body.model_id) : null;
      }

      if (!imageUrl) httpError("Informe o link da imagem (URL) ou selecione um arquivo.");
      const ts = nowIso();
      const created = {
        id: nextId(st.media),
        filename: "",
        file_url: imageUrl,
        title: title || "Foto de Impressão 3D",
        model_id: modelId,
        print_job_id: jobId,
        catalog_item_id: catalogId,
        post_format: postFormat,
        status,
        caption: "",
        hashtags: "",
        scheduled_date: "",
        notes: "",
        created_at: ts,
        updated_at: ts,
      };
      st.media.unshift(created);
      await persistState(st);
      return created;
    }
  }

  mMatch = path.match(/^\/api\/media\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = st.media.findIndex((m) => Number(m.id) === id);
    if (idx < 0) httpError("Mídia não encontrada.");
    if (method === "DELETE") {
      st.media.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      st.media[idx] = { ...st.media[idx], ...parseBody(options), id, updated_at: nowIso() };
      await persistState(st);
      return st.media[idx];
    }
  }

  // ---- 7. ERP Loja (Dashboard, Clientes, Cotações 3D, Fornecedores, Compras, Kits, Nichos) ---- //
  if (path === "/api/erp/dashboard" && method === "GET") {
    return buildErpDashboard(st);
  }

  // Clientes
  if (path === "/api/customers") {
    if (method === "GET") {
      const q = (qp.get("q") || "").trim().toLowerCase();
      const bMonth = (qp.get("birthday_month") || "").trim();
      let items = (st.customers || []).map((c) => {
        const orders = (st.sales || []).filter(
          (s) => Number(s.customer_id) === Number(c.id) || (c.name && s.customer_name?.toLowerCase() === c.name.toLowerCase())
        );
        const totalSpent = Math.round(orders.reduce((a, s) => a + Number(s.total_price_brl || 0), 0) * 100) / 100;
        return { ...c, orders_count: orders.length, total_spent_brl: totalSpent };
      });
      if (q) {
        items = items.filter((c) => `${c.name} ${c.whatsapp} ${c.city} ${c.notes}`.toLowerCase().includes(q));
      }
      if (bMonth) {
        const bm = bMonth.padStart(2, "0");
        items = items.filter((c) => {
          const parts = String(c.birthday || "").split(/[/-]/);
          return parts.length >= 2 && parts[1].padStart(2, "0") === bm;
        });
      }
      return { items, total: items.length };
    }
    if (method === "POST") {
      const body = parseBody(options);
      const name = String(body.name || "").trim();
      if (!name) httpError("Informe o nome do cliente.");
      const ts = nowIso();
      const created = {
        id: nextId(st.customers),
        name,
        whatsapp: String(body.whatsapp || "").trim(),
        email: String(body.email || "").trim(),
        city: String(body.city || "Itamarandiba - MG").trim(),
        birthday: String(body.birthday || "").trim(),
        notes: String(body.notes || "").trim(),
        created_at: ts,
        updated_at: ts,
      };
      st.customers.unshift(created);
      await persistState(st);
      return { ...created, orders_count: 0, total_spent_brl: 0 };
    }
  }

  mMatch = path.match(/^\/api\/customers\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = (st.customers || []).findIndex((c) => Number(c.id) === id);
    if (idx < 0) httpError("Cliente não encontrado.");
    if (method === "DELETE") {
      st.customers.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      st.customers[idx] = { ...st.customers[idx], ...parseBody(options), id, updated_at: nowIso() };
      await persistState(st);
      return st.customers[idx];
    }
  }

  // Cotações / Orçamentos 3D para Clientes
  if (path === "/api/quotes") {
    if (method === "GET") {
      const status = qp.get("status") || "";
      const q = (qp.get("q") || "").trim().toLowerCase();
      let items = st.quotes || [];
      if (status) items = items.filter((x) => x.status === status);
      if (q) items = items.filter((x) => `${x.code} ${x.title} ${x.customer_name} ${x.notes}`.toLowerCase().includes(q));
      return { items, total: items.length };
    }
    if (method === "POST") {
      const body = parseBody(options);
      const title = String(body.title || "").trim();
      if (!title) httpError("Informe o nome da peça/projeto do orçamento.");
      const custObj = body.customer_id ? (st.customers || []).find((c) => Number(c.id) === Number(body.customer_id)) : null;
      const printerObj = body.printer_id ? (st.printers || []).find((p) => Number(p.id) === Number(body.printer_id)) : null;
      const spoolObj = body.spool_id ? (st.spools || []).find((s) => Number(s.id) === Number(body.spool_id)) : null;

      const calcInput = {
        ...body,
        spool_cost_per_kg_brl: body.spool_cost_per_kg_brl ?? spoolObj?.cost_per_kg_brl ?? 120,
        printer_hourly_cost_brl: body.printer_hourly_cost_brl ?? printerObj?.hourly_cost_brl ?? 2.5,
      };
      const metrics = computeQuoteMetrics(calcInput);
      const nextNum = nextId(st.quotes);
      const ts = nowIso();
      const created = {
        id: nextNum,
        code: body.code || `ORC-${String(nextNum).padStart(3, "0")}`,
        customer_id: custObj?.id || (body.customer_id ? Number(body.customer_id) : null),
        customer_name: String(body.customer_name || custObj?.name || "Cliente").trim(),
        customer_whatsapp: String(body.customer_whatsapp || custObj?.whatsapp || "").trim(),
        model_id: body.model_id ? Number(body.model_id) : null,
        catalog_item_id: body.catalog_item_id ? Number(body.catalog_item_id) : null,
        printer_id: printerObj?.id || null,
        printer_name: printerObj?.name || "",
        spool_id: spoolObj?.id || null,
        spool_label: spoolObj ? `${spoolObj.material} ${spoolObj.color_name}` : "",
        title,
        quantity: Math.max(1, Number(body.quantity || 1)),
        grams: Math.max(0, Number(body.grams || 0)),
        time_min: Math.max(0, Number(body.time_min || 0)),
        spool_cost_per_kg_brl: Number(calcInput.spool_cost_per_kg_brl),
        printer_hourly_cost_brl: Number(calcInput.printer_hourly_cost_brl),
        energy_wear_brl: Number(body.energy_wear_brl ?? 1.5),
        extras_brl: Number(body.extras_brl ?? 0),
        pricing_mode: body.pricing_mode || "cost_markup",
        rate_per_gram_brl: Number(body.rate_per_gram_brl ?? 0.45),
        margin_percent: Number(body.margin_percent ?? 160),
        ...metrics,
        lead_days: Math.max(1, Number(body.lead_days || 2)),
        status: body.status || "Enviada",
        notes: String(body.notes || "").trim(),
        created_at: ts,
        updated_at: ts,
      };
      st.quotes.unshift(created);
      await persistState(st);
      return created;
    }
  }

  mMatch = path.match(/^\/api\/quotes\/(\d+)\/approve$/);
  if (mMatch && method === "POST") {
    const id = Number(mMatch[1]);
    const idx = (st.quotes || []).findIndex((q) => Number(q.id) === id);
    if (idx < 0) httpError("Cotação não encontrada.");
    const quote = st.quotes[idx];
    const ts = nowIso();
    quote.status = "Aprovada";
    quote.updated_at = ts;

    const job = {
      id: nextId(st.jobs),
      model_id: quote.model_id || null,
      printer_id: quote.printer_id || null,
      spool_id: quote.spool_id || null,
      catalog_item_id: quote.catalog_item_id || null,
      rubric_id: st.rubrics[0]?.id || null,
      rubric_name: st.rubrics[0]?.name || "Encomendas Gerais",
      slicing_profile_id: null,
      slicing_notes: quote.notes || "",
      title: `${quote.code} — ${quote.title}`,
      target_type: "Encomenda",
      customer_name: quote.customer_name || "",
      quantity: Number(quote.quantity || 1),
      estimated_grams: Number(quote.grams || 0) * Number(quote.quantity || 1),
      estimated_time_min: Number(quote.time_min || 60) * Number(quote.quantity || 1),
      priority: "Alta",
      status: "Pendente",
      notes: `Origem: Orçamento ${quote.code}${quote.notes ? ` • ${quote.notes}` : ""}`,
      created_at: ts,
      updated_at: ts,
    };
    st.jobs.unshift(job);

    const sale = {
      id: nextId(st.sales),
      catalog_item_id: quote.catalog_item_id || null,
      kit_id: null,
      quote_id: quote.id,
      customer_id: quote.customer_id || null,
      customer_name: quote.customer_name || "Cliente",
      customer_whatsapp: quote.customer_whatsapp || "",
      item_name: `${quote.code} — ${quote.title}`,
      channel: "WhatsApp",
      quantity: Number(quote.quantity || 1),
      unit_price_brl: Number(quote.unit_price_brl || 0),
      unit_cost_brl: Number(quote.unit_cost_brl || 0),
      discount_brl: 0,
      freight_brl: 0,
      total_price_brl: Number(quote.total_price_brl || 0),
      payment_method: "Pix",
      payment_status: "Sinal 50%",
      fulfillment_status: "Na Fila",
      linked_job_id: job.id,
      notes: `Aprovado da cotação ${quote.code}`,
      created_at: ts,
      updated_at: ts,
    };
    st.sales.unshift(sale);
    await persistState(st);
    return { quote, sale, job: enrichJob(st, job) };
  }

  mMatch = path.match(/^\/api\/quotes\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = (st.quotes || []).findIndex((q) => Number(q.id) === id);
    if (idx < 0) httpError("Cotação não encontrada.");
    if (method === "DELETE") {
      st.quotes.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      const merged = { ...st.quotes[idx], ...parseBody(options), id, updated_at: nowIso() };
      const metrics = computeQuoteMetrics(merged);
      st.quotes[idx] = { ...merged, ...metrics };
      await persistState(st);
      return st.quotes[idx];
    }
  }

  // Fornecedores
  if (path === "/api/suppliers") {
    if (method === "GET") return { items: st.suppliers || [], total: (st.suppliers || []).length };
    if (method === "POST") {
      const body = parseBody(options);
      const name = String(body.name || "").trim();
      if (!name) httpError("Informe o nome do fornecedor.");
      const created = {
        id: nextId(st.suppliers),
        name,
        type: String(body.type || "Atacado / Filamentos"),
        contact: String(body.contact || ""),
        whatsapp: String(body.whatsapp || ""),
        site: String(body.site || ""),
        city_uf: String(body.city_uf || ""),
        lead_days: Number(body.lead_days || 5),
        min_order_brl: Number(body.min_order_brl || 0),
        notes: String(body.notes || ""),
        active: body.active !== false,
        created_at: nowIso(),
      };
      st.suppliers.unshift(created);
      await persistState(st);
      return created;
    }
  }

  mMatch = path.match(/^\/api\/suppliers\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = (st.suppliers || []).findIndex((s) => Number(s.id) === id);
    if (idx < 0) httpError("Fornecedor não encontrado.");
    if (method === "DELETE") {
      st.suppliers.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      st.suppliers[idx] = { ...st.suppliers[idx], ...parseBody(options), id };
      await persistState(st);
      return st.suppliers[idx];
    }
  }

  // Compras de Reposição
  if (path === "/api/purchases") {
    if (method === "GET") return { items: st.purchases || [], total: (st.purchases || []).length };
    if (method === "POST") {
      const body = parseBody(options);
      const qty = Math.max(1, Number(body.quantity || 1));
      const unitCost = Math.max(0, Number(body.unit_cost_brl || 0));
      const freight = Math.max(0, Number(body.freight_brl || 0));
      const taxes = Math.max(0, Number(body.taxes_brl || 0));
      const other = Math.max(0, Number(body.other_costs_brl || 0));
      const total = Math.round((qty * unitCost + freight + taxes + other) * 100) / 100;
      const finalUnit = Math.round((total / qty) * 100) / 100;
      const supObj = body.supplier_id ? (st.suppliers || []).find((s) => Number(s.id) === Number(body.supplier_id)) : null;

      let itemName = String(body.item_name || "").trim();
      const kind = body.target_kind || "catalog";
      const targetId = body.target_id ? Number(body.target_id) : null;

      if (kind === "catalog" && targetId) {
        const cat = st.catalog.find((c) => Number(c.id) === targetId);
        if (cat) {
          cat.stock_qty = Number(cat.stock_qty || 0) + qty;
          cat.unit_cost_brl = finalUnit;
          if (!itemName) itemName = cat.name;
        }
      } else if (kind === "spool" && targetId) {
        const spIdx = st.spools.findIndex((s) => Number(s.id) === targetId);
        if (spIdx >= 0) {
          const sp = st.spools[spIdx];
          const addGrams = qty * 1000;
          st.spools[spIdx] = enrichSpool({
            ...sp,
            initial_grams: Number(sp.initial_grams || 1000) + addGrams,
            remaining_grams: Number(sp.remaining_grams || 0) + addGrams,
            cost_per_kg_brl: finalUnit > 0 ? finalUnit : sp.cost_per_kg_brl,
            updated_at: nowIso(),
          });
          if (!itemName) itemName = `${sp.material} ${sp.color_name} (${qty} kg)`;
        }
      }

      const created = {
        id: nextId(st.purchases),
        supplier_id: supObj?.id || null,
        supplier_name: supObj?.name || String(body.supplier_name || "Fornecedor Avulso"),
        target_kind: kind,
        target_id: targetId,
        item_name: itemName || "Compra de Reposição",
        quantity: qty,
        unit_cost_brl: unitCost,
        freight_brl: freight,
        taxes_brl: taxes,
        other_costs_brl: other,
        final_unit_cost_brl: finalUnit,
        total_brl: total,
        notes: String(body.notes || "").trim(),
        created_at: nowIso(),
      };
      st.purchases.unshift(created);
      await persistState(st);
      return created;
    }
  }

  mMatch = path.match(/^\/api\/purchases\/(\d+)$/);
  if (mMatch && method === "DELETE") {
    const id = Number(mMatch[1]);
    const idx = (st.purchases || []).findIndex((p) => Number(p.id) === id);
    if (idx < 0) httpError("Compra não encontrada.");
    st.purchases.splice(idx, 1);
    await persistState(st);
    return { deleted: true, id };
  }

  // Kits & Combos
  if (path === "/api/kits") {
    if (method === "GET") return { items: st.kits || [], total: (st.kits || []).length };
    if (method === "POST") {
      const body = parseBody(options);
      const name = String(body.name || "").trim();
      if (!name) httpError("Informe o nome do Kit / Combo.");
      const rawItems = Array.isArray(body.items) ? body.items : [];
      const items = rawItems.map((it) => {
        const prod = it.catalog_item_id ? st.catalog.find((c) => Number(c.id) === Number(it.catalog_item_id)) : null;
        return {
          catalog_item_id: prod?.id || null,
          name: it.name || prod?.name || "Item",
          qty: Math.max(1, Number(it.qty || 1)),
          unit_cost_brl: Number(it.unit_cost_brl ?? prod?.unit_cost_brl ?? 0),
        };
      });
      const sumCost = items.reduce((a, it) => a + it.unit_cost_brl * it.qty, 0);
      const totalCost = body.total_cost_brl != null ? Number(body.total_cost_brl) : Math.round(sumCost * 100) / 100;
      const created = {
        id: nextId(st.kits),
        name,
        level: String(body.level || "Médio"),
        niche: String(body.niche || "Presentes Personalizados & Kits Prontos"),
        items,
        total_cost_brl: totalCost,
        sale_price_brl: Number(body.sale_price_brl || Math.round(totalCost * 2 * 100) / 100),
        notes: String(body.notes || "").trim(),
        active: body.active !== false,
        created_at: nowIso(),
      };
      st.kits.unshift(created);
      await persistState(st);
      return created;
    }
  }

  mMatch = path.match(/^\/api\/kits\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = (st.kits || []).findIndex((k) => Number(k.id) === id);
    if (idx < 0) httpError("Kit não encontrado.");
    if (method === "DELETE") {
      st.kits.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      st.kits[idx] = { ...st.kits[idx], ...parseBody(options), id };
      await persistState(st);
      return st.kits[idx];
    }
  }

  // Nichos da Loja
  if (path === "/api/nichos") {
    if (method === "GET") return { items: st.nichos || [], total: (st.nichos || []).length };
    if (method === "POST") {
      const body = parseBody(options);
      const nome = String(body.nome || "").trim();
      if (!nome) httpError("Informe o nome do nicho.");
      const created = {
        id: nextId(st.nichos),
        nome,
        cor: String(body.cor || "#38bdf8"),
        descricao: String(body.descricao || ""),
        ativo: body.ativo !== false,
        created_at: nowIso(),
      };
      st.nichos.push(created);
      await persistState(st);
      return created;
    }
  }

  mMatch = path.match(/^\/api\/nichos\/(\d+)$/);
  if (mMatch) {
    const id = Number(mMatch[1]);
    const idx = (st.nichos || []).findIndex((n) => Number(n.id) === id);
    if (idx < 0) httpError("Nicho não encontrado.");
    if (method === "DELETE") {
      st.nichos.splice(idx, 1);
      await persistState(st);
      return { deleted: true, id };
    }
    if (method === "PATCH") {
      st.nichos[idx] = { ...st.nichos[idx], ...parseBody(options), id };
      await persistState(st);
      return st.nichos[idx];
    }
  }

  httpError(`Rota não suportada no modo offline/GitHub Pages: ${method} ${path}`);
}
