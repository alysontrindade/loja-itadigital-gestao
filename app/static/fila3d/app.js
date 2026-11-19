import { createHubController } from "./hub_tabs.js";
import {
  apiJson,
  escapeHtml,
  formatDateTimePtBr,
  formatDuration,
  formatGrams,
  showToast,
  toLocalDatetimeInputValue,
} from "./utils.js";

const PAGE_LIMIT = 48;

const state = {
  meta: null,
  modelSubcategories: [],
  activeTab: "models",
  items: [],
  total: 0,
  offset: 0,
  hasMore: false,
  editClassifications: [],
  editClassificationsDirty: false,
  filters: {
    q: "",
    status: "",
    category: "",
    subcategory: "",
    collected_from: "",
    collected_to: "",
    size_tier: "",
    max_dimension_mm: "",
    min_grams: "",
    max_grams: "",
    filament: "",
    color: "",
    include_multicolor: true,
    sort: "collected_desc",
  },
  activeRequestController: null,
};

let hubCtrl = null;

function colorSwatchHtml(colorName) {
  const colorMeta = state.meta?.colors?.find((c) => c.name === colorName);
  if (colorMeta?.type === "multicolor" || colorName === "Multicolor / Todas as Cores") {
    return '<span class="swatch swatch-multicolor" aria-hidden="true"></span>';
  }
  const hex = colorMeta?.hex || "#71717a";
  return `<span class="swatch" style="background:${escapeHtml(hex)}" aria-hidden="true"></span>`;
}

function statusClass(status) {
  return `status-${String(status || "na-fila")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, "-")}`;
}

function renderExtraClassBadges(item) {
  const pairs = Array.isArray(item.classifications) && item.classifications.length
    ? item.classifications
    : [{ category: item.category, subcategory: item.subcategory || "" }];
  if (pairs.length <= 1) return "";
  return `<div class="card-class-badges">${pairs
    .slice(1)
    .map((p) => {
      const full = p.subcategory ? `${p.category} › ${p.subcategory}` : p.category;
      return `<span class="card-class-badge" title="${escapeHtml(full)}">+ ${escapeHtml(p.subcategory || p.category)}</span>`;
    })
    .join("")}</div>`;
}

function renderEditClassifications() {
  const wrap = document.getElementById("edit-classifications-list");
  if (!wrap) return;
  wrap.innerHTML = state.editClassifications
    .map((pair, idx) => {
      const label = pair.subcategory ? `${pair.category} › ${pair.subcategory}` : pair.category;
      const removeBtn =
        state.editClassifications.length > 1
          ? `<button type="button" class="class-chip-remove" data-remove-class="${idx}" title="Remover classificação">×</button>`
          : "";
      return `<span class="class-chip ${idx === 0 ? "primary" : ""}">${escapeHtml(label)}${removeBtn}</span>`;
    })
    .join("");
}

function syncModelSubcatSelect(selectEl, category, currentVal = "", emptyLabel = "Todas as subcategorias") {
  const subs = state.modelSubcategories.filter((s) => !category || s.category === category);
  const names = Array.from(new Set(subs.map((s) => s.name)));
  if (currentVal && !names.includes(currentVal)) names.unshift(currentVal);
  selectEl.innerHTML = [`<option value="">${escapeHtml(emptyLabel)}</option>`]
    .concat(names.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`))
    .join("");
  selectEl.value = currentVal && names.includes(currentVal) ? currentVal : "";
}

async function refreshModelSubcategories() {
  try {
    const res = await apiJson("/api/subcategories?scope=models");
    state.modelSubcategories = res.items || [];
    const curFilterSub = state.filters.subcategory || "";
    syncModelSubcatSelect(
      document.getElementById("filter-subcategory"),
      state.filters.category,
      curFilterSub,
      "Todas as subcategorias"
    );
    syncModelSubcatSelect(
      document.getElementById("edit-subcategory"),
      document.getElementById("edit-category").value,
      document.getElementById("edit-subcategory").value,
      "Sem subcategoria"
    );
  } catch {
    // non-blocking
  }
}

async function refreshSummary() {
  try {
    const s = await apiJson("/api/hub/summary");
    document.getElementById("badge-models").textContent = s.models_active ?? s.models_total;
    document.getElementById("badge-queue").textContent = s.queue_pending + s.queue_active;
    document.getElementById("badge-printers").textContent = s.printers_total;
    document.getElementById("badge-inventory").textContent = s.spools_low > 0 ? `${s.spools_total}!` : s.spools_total;
    document.getElementById("badge-catalog").textContent = s.catalog_total;
    document.getElementById("badge-media").textContent = s.media_total;
    document.getElementById("badge-archived").textContent = s.archived_total ?? 0;
  } catch {
    // Non-blocking topbar badge refresh
  }
}

async function switchTab(tabName) {
  state.activeTab = tabName;
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.hidden = panel.id !== `tab-${tabName}`;
  });
  if (!hubCtrl) return;
  if (tabName === "queue") await hubCtrl.renderQueueTab();
  else if (tabName === "printers") await hubCtrl.renderPrintersTab();
  else if (tabName === "inventory") await hubCtrl.renderInventoryTab();
  else if (tabName === "catalog") await hubCtrl.renderCatalogTab();
  else if (tabName === "media") await hubCtrl.renderMediaTab();
  else if (tabName === "archived") await hubCtrl.renderArchivedTab();
}

function populateMetaControls() {
  const { meta } = state;

  document.getElementById("filter-status-chips").innerHTML = [
    '<button class="chip active" type="button" data-status="">Todos</button>',
    ...meta.statuses
      .filter((st) => st !== "Arquivado")
      .map((st) => `<button class="chip" type="button" data-status="${escapeHtml(st)}">${escapeHtml(st)}</button>`),
  ].join("");

  const catOptions = meta.categories.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
  document.getElementById("filter-category").innerHTML = `<option value="">Todos os nichos</option>${catOptions}`;
  document.getElementById("edit-category").innerHTML = catOptions;

  document.getElementById("filter-size-chips").innerHTML = [
    '<button class="chip active" type="button" data-size="">Qualquer</button>',
    ...meta.size_tiers.map(
      (sz) => `<button class="chip" type="button" data-size="${escapeHtml(sz.name)}">${escapeHtml(sz.name)}</button>`
    ),
  ].join("");
  document.getElementById("edit-size-tier").innerHTML = meta.size_tiers
    .map((sz) => `<option value="${escapeHtml(sz.name)}">${escapeHtml(sz.name)} (${escapeHtml(sz.label)})</option>`)
    .join("");

  document.getElementById("filter-filament").innerHTML =
    `<option value="">Todos os filamentos</option>` +
    meta.filaments.map((f) => `<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`).join("");

  document.getElementById("filter-color-chips").innerHTML = [
    '<button class="chip active" type="button" data-color="">Todas</button>',
    ...meta.colors.map(
      (c) => `<button class="chip" type="button" data-color="${escapeHtml(c.name)}">${colorSwatchHtml(c.name)}<span>${escapeHtml(c.name)}</span></button>`
    ),
  ].join("");

  document.getElementById("edit-filaments-wrap").innerHTML = meta.filaments
    .map((f) => `<button class="chip" type="button" data-edit-filament="${escapeHtml(f)}">${escapeHtml(f)}</button>`)
    .join("");

  document.getElementById("edit-colors-wrap").innerHTML = meta.colors
    .map(
      (c) => `<button class="chip" type="button" data-edit-color="${escapeHtml(c.name)}">${colorSwatchHtml(c.name)}<span>${escapeHtml(c.name)}</span></button>`
    )
    .join("");
}

function buildModelsQueryParams() {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(state.filters)) {
    if (k === "include_multicolor") {
      params.set(k, v ? "true" : "false");
    } else if (v !== "" && v !== null && v !== undefined) {
      params.set(k, String(v));
    }
  }
  if (state.filters.status !== "Arquivado") {
    params.set("exclude_archived", "true");
  }
  params.set("limit", String(PAGE_LIMIT));
  params.set("offset", String(state.offset));
  return params;
}

function hasActiveFilters() {
  const { filters } = state;
  return Boolean(
    filters.q ||
      filters.status ||
      filters.category ||
      filters.collected_from ||
      filters.collected_to ||
      filters.size_tier ||
      filters.max_dimension_mm ||
      filters.min_grams ||
      filters.max_grams ||
      filters.filament ||
      filters.color
  );
}

function renderModels(data) {
  state.items = data.items;
  state.total = data.total;
  state.hasMore = Boolean(data.has_more);

  document.getElementById("metric-total").textContent = data.total;
  document.getElementById("metric-grams").textContent = formatGrams(data.total_filament_grams);
  document.getElementById("metric-queue").textContent = data.stats.na_fila;
  document.getElementById("metric-multicolor").textContent = data.stats.multicolor;

  const startNum = data.total === 0 ? 0 : state.offset + 1;
  const endNum = state.offset + data.items.length;
  document.getElementById("results-summary").textContent =
    data.total === 0 ? "0 modelos encontrados" : `Exibindo ${startNum}–${endNum} de ${data.total} modelos`;

  const grid = document.getElementById("cards-grid");
  const emptyEl = document.getElementById("empty-state");
  const pagBar = document.getElementById("pagination-bar");

  if (!data.items.length) {
    grid.innerHTML = "";
    emptyEl.hidden = false;
    pagBar.hidden = true;
    document.getElementById("empty-clear-btn").hidden = !hasActiveFilters();
    return;
  }

  emptyEl.hidden = true;
  grid.innerHTML = data.items
    .map((item) => {
      const fallbackHtml = (msg, hiddenByDefault) => `
        <div class="card-thumb-fallback"${hiddenByDefault ? ' style="display:none;"' : ""}>
          <span>${escapeHtml(msg)}</span>
          <div class="thumb-config-actions">
            <button class="btn btn-secondary btn-xs model-config-img-btn" data-id="${item.id}" type="button">Configurar link</button>
            <button class="btn btn-ghost btn-xs model-quick-enrich-btn" data-id="${item.id}" type="button">Buscar API</button>
          </div>
        </div>
      `;
      const thumb = item.image_url
        ? `<img class="card-thumb-clickable" data-lightbox-id="${item.id}" src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.hidden=true; this.nextElementSibling.style.display='flex';" />${fallbackHtml(`${item.source} • link indisponível`, true)}`
        : fallbackHtml(`${item.source} • sem imagem`, false);
      const dur = formatDuration(item.print_time_min);
      const dims = item.dimensions_mm || (item.max_dimension_mm ? `≤ ${item.max_dimension_mm} mm` : null);

      return `
        <article class="card">
          <div class="card-thumb">
            ${thumb}
            <span class="thumb-source">${escapeHtml(item.source)}</span>
            <span class="thumb-status ${statusClass(item.status)}">${escapeHtml(item.status)}</span>
          </div>
          <div class="card-body">
            <div class="card-category-row">
              <span>${escapeHtml(item.category)}${item.subcategory ? ` › <strong>${escapeHtml(item.subcategory)}</strong>` : ""}</span>
              <span class="tnum">${formatDateTimePtBr(item.collected_at)}</span>
            </div>
            ${renderExtraClassBadges(item)}
            <h3 class="card-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</h3>
            <div class="specs-strip tnum">
              <span class="spec-pill">Tam.: <strong>${escapeHtml(item.size_tier)}</strong>${dims ? ` (${escapeHtml(dims)})` : ""}</span>
              <span class="spec-pill">Fil.: <strong>${formatGrams(item.filament_grams)}</strong></span>
              ${dur ? `<span class="spec-pill">Tempo: <strong>${escapeHtml(dur)}</strong></span>` : ""}
            </div>
            <div class="rec-block">
              <div class="rec-row">
                ${(item.recommended_filaments || []).map((f) => `<span class="rec-tag">${escapeHtml(f)}</span>`).join("")}
              </div>
              <div class="rec-row">
                ${(item.recommended_colors || []).map((c) => `<span class="color-pill">${colorSwatchHtml(c)}<span>${escapeHtml(c)}</span></span>`).join("")}
              </div>
              <p class="rec-reason">${escapeHtml(item.filament_reason)}</p>
            </div>
          </div>
          <div class="card-footer">
            <a class="btn btn-ghost btn-xs" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">Abrir link ↗</a>
            <div class="card-actions">
              <button class="btn btn-accent btn-xs model-queue-btn" data-id="${item.id}" type="button">+ Fila</button>
              <button class="btn btn-secondary btn-xs model-edit-btn" data-id="${item.id}" type="button">Editar</button>
              <button class="btn btn-ghost btn-xs model-archive-btn" data-id="${item.id}" type="button" title="Mover para Arquivados">Arquivar</button>
            </div>
          </div>
        </article>
      `;
    })
    .join("");

  grid.querySelectorAll(".model-edit-btn").forEach((btn) => {
    btn.addEventListener("click", () => openEditDrawer(Number(btn.dataset.id)));
  });

  grid.querySelectorAll(".model-config-img-btn").forEach((btn) => {
    btn.addEventListener("click", () => openEditDrawer(Number(btn.dataset.id), { focusImageUrl: true }));
  });

  grid.querySelectorAll(".model-quick-enrich-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.dataset.id);
      const orig = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Buscando...";
      try {
        const updated = await apiJson(`/api/models/${id}/enrich`, { method: "POST" });
        if (updated.image_url) {
          showToast("Link da imagem configurado!");
          fetchModels(false);
        } else {
          showToast("Sem capa automática — configure o link manualmente.");
          openEditDrawer(id, { focusImageUrl: true });
        }
      } catch {
        showToast("Sem capa automática — configure o link manualmente.");
        openEditDrawer(id, { focusImageUrl: true });
      } finally {
        btn.disabled = false;
        btn.textContent = orig;
      }
    });
  });

  grid.querySelectorAll("[data-lightbox-id]").forEach((img) => {
    img.addEventListener("click", () => openLightbox(Number(img.dataset.lightboxId)));
  });

  grid.querySelectorAll(".model-queue-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const m = state.items.find((x) => x.id === Number(btn.dataset.id));
      if (!m || !hubCtrl) return;
      hubCtrl.openJobModal({
        model_id: m.id,
        title: m.title,
        estimated_grams: m.filament_grams || 50,
        estimated_time_min: m.print_time_min || 60,
        target_type: "Estoque",
      });
    });
  });

  grid.querySelectorAll(".model-archive-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await apiJson(`/api/models/${btn.dataset.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "Arquivado" }),
      });
      showToast("Impressão arquivada.");
      await Promise.all([fetchModels(false), refreshSummary()]);
    });
  });

  const currentPage = Math.floor(state.offset / PAGE_LIMIT) + 1;
  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_LIMIT));
  pagBar.hidden = totalPages <= 1;
  document.getElementById("page-info").textContent = `Página ${currentPage} de ${totalPages}`;
  document.getElementById("page-prev-btn").disabled = state.offset === 0;
  document.getElementById("page-next-btn").disabled = !state.hasMore;
}

async function fetchModels(resetOffset = false) {
  if (resetOffset) state.offset = 0;
  if (state.activeRequestController) state.activeRequestController.abort();
  state.activeRequestController = new AbortController();

  document.getElementById("error-banner").hidden = true;
  document.getElementById("loading-state").hidden = false;

  try {
    const data = await apiJson(`/api/models?${buildModelsQueryParams().toString()}`, {
      signal: state.activeRequestController.signal,
    });
    renderModels(data);
  } catch (err) {
    if (err.name === "AbortError") return;
    document.getElementById("error-text").textContent = err.message;
    document.getElementById("error-banner").hidden = false;
  } finally {
    document.getElementById("loading-state").hidden = true;
  }
}

function openLightbox(id) {
  const item = state.items.find((i) => i.id === id);
  if (!item || !item.image_url) return;
  document.getElementById("lightbox-title").textContent = item.title;
  const imgEl = document.getElementById("lightbox-img");
  imgEl.src = item.image_url;
  imgEl.alt = item.title;
  const parts = [item.category, formatGrams(item.filament_grams), formatDuration(item.print_time_min), item.dimensions_mm].filter(Boolean);
  document.getElementById("lightbox-meta").textContent = parts.join(" • ");
  document.getElementById("lightbox-link").href = item.url;
  const qBtn = document.getElementById("lightbox-queue-btn");
  qBtn.onclick = () => {
    document.getElementById("lightbox-backdrop").hidden = true;
    hubCtrl?.openJobModal({
      model_id: item.id,
      title: item.title,
      estimated_grams: item.filament_grams || 50,
      estimated_time_min: item.print_time_min || 60,
      target_type: "Estoque",
    });
  };
  document.getElementById("lightbox-backdrop").hidden = false;
}

function openEditDrawer(id, opts = {}) {
  const item = state.items.find((i) => i.id === id);
  if (!item) return;

  document.getElementById("edit-id").value = item.id;
  document.getElementById("edit-title").value = item.title;
  document.getElementById("edit-category").value = item.category;
  syncModelSubcatSelect(
    document.getElementById("edit-subcategory"),
    item.category,
    item.subcategory || "",
    "Sem subcategoria"
  );
  state.editClassifications =
    Array.isArray(item.classifications) && item.classifications.length
      ? item.classifications.map((c) => ({ category: c.category, subcategory: c.subcategory || "" }))
      : [{ category: item.category, subcategory: item.subcategory || "" }];
  state.editClassificationsDirty = false;
  renderEditClassifications();
  document.getElementById("edit-status").value = item.status;
  document.getElementById("edit-size-tier").value = item.size_tier;
  document.getElementById("edit-dimensions").value = item.dimensions_mm || "";
  document.getElementById("edit-grams").value = item.filament_grams ?? "";
  document.getElementById("edit-time").value = item.print_time_min ?? "";
  document.getElementById("edit-reason").value = item.filament_reason || "";
  document.getElementById("edit-image-url").value = item.image_url || "";
  const prev = document.getElementById("edit-image-preview");
  if (item.image_url) {
    prev.src = item.image_url;
    prev.hidden = false;
  } else {
    prev.hidden = true;
  }
  document.getElementById("edit-notes").value = item.notes || "";

  document.querySelectorAll("[data-edit-filament]").forEach((btn) => {
    btn.classList.toggle("active", (item.recommended_filaments || []).includes(btn.dataset.editFilament));
  });
  document.querySelectorAll("[data-edit-color]").forEach((btn) => {
    btn.classList.toggle("active", (item.recommended_colors || []).includes(btn.dataset.editColor));
  });

  document.getElementById("edit-backdrop").hidden = false;
  if (opts.focusImageUrl) {
    setTimeout(() => {
      const el = document.getElementById("edit-image-url");
      el.focus();
      el.select();
    }, 30);
  }
}

function clearAllFilters() {
  state.filters = {
    q: "",
    status: "",
    category: "",
    subcategory: "",
    collected_from: "",
    collected_to: "",
    size_tier: "",
    max_dimension_mm: "",
    min_grams: "",
    max_grams: "",
    filament: "",
    color: "",
    include_multicolor: true,
    sort: "collected_desc",
  };
  document.getElementById("filter-q").value = "";
  document.getElementById("filter-category").value = "";
  syncModelSubcatSelect(document.getElementById("filter-subcategory"), "", "", "Todas as subcategorias");
  document.getElementById("filter-from").value = "";
  document.getElementById("filter-to").value = "";
  document.getElementById("filter-max-mm").value = "";
  document.getElementById("filter-min-grams").value = "";
  document.getElementById("filter-max-grams").value = "";
  document.getElementById("filter-filament").value = "";
  document.getElementById("filter-include-multicolor").checked = true;
  document.getElementById("sort-select").value = "collected_desc";

  document.querySelectorAll("[data-status], [data-size], [data-color]").forEach((c) => {
    const val = c.dataset.status ?? c.dataset.size ?? c.dataset.color ?? "";
    c.classList.toggle("active", val === "");
  });
  document.querySelectorAll(".date-preset, .gram-preset").forEach((b, idx) => {
    b.classList.toggle("active", b.dataset.preset === "" || (b.dataset.min === "" && b.dataset.max === "" && idx >= 0));
  });
  fetchModels(true);
}

function bindModelsEvents() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  document.getElementById("page-prev-btn").addEventListener("click", () => {
    if (state.offset >= PAGE_LIMIT) {
      state.offset -= PAGE_LIMIT;
      fetchModels(false);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  });
  document.getElementById("page-next-btn").addEventListener("click", () => {
    if (state.hasMore) {
      state.offset += PAGE_LIMIT;
      fetchModels(false);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  });

  document.getElementById("ingest-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const rawText = document.getElementById("ingest-links").value.trim();
    if (!rawText) {
      showToast("Cole pelo menos um link HTTP/HTTPS antes de coletar.");
      return;
    }
    const res = await apiJson("/api/import/batch", { method: "POST", body: JSON.stringify({ raw_text: rawText }) });
    document.getElementById("ingest-links").value = "";
    showToast(`${res.count} modelo(s) coletado(s)!`);
    await Promise.all([fetchModels(true), refreshSummary()]);
  });

  document.getElementById("seed-demo-btn").addEventListener("click", async () => {
    const res = await apiJson("/api/seed-demo", { method: "POST" });
    showToast(`${res.count} modelos de exemplo adicionados.`);
    await Promise.all([fetchModels(true), refreshSummary()]);
  });

  let debounce = null;
  document.getElementById("filter-q").addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.filters.q = document.getElementById("filter-q").value.trim();
      fetchModels(true);
    }, 200);
  });

  document.getElementById("filter-status-chips").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-status]");
    if (!btn) return;
    document.querySelectorAll("[data-status]").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.filters.status = btn.dataset.status;
    fetchModels(true);
  });

  document.getElementById("filter-size-chips").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-size]");
    if (!btn) return;
    document.querySelectorAll("[data-size]").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.filters.size_tier = btn.dataset.size;
    fetchModels(true);
  });

  document.getElementById("filter-color-chips").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-color]");
    if (!btn) return;
    document.querySelectorAll("[data-color]").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.filters.color = btn.dataset.color;
    fetchModels(true);
  });

  document.querySelectorAll(".date-preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".date-preset").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const now = new Date();
      const preset = btn.dataset.preset;
      if (preset === "today") {
        const start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
        document.getElementById("filter-from").value = toLocalDatetimeInputValue(start);
        document.getElementById("filter-to").value = toLocalDatetimeInputValue(now);
      } else if (preset === "7d") {
        const start = new Date(now.getTime() - 7 * 86400 * 1000);
        document.getElementById("filter-from").value = toLocalDatetimeInputValue(start);
        document.getElementById("filter-to").value = toLocalDatetimeInputValue(now);
      } else {
        document.getElementById("filter-from").value = "";
        document.getElementById("filter-to").value = "";
      }
      state.filters.collected_from = document.getElementById("filter-from").value;
      state.filters.collected_to = document.getElementById("filter-to").value;
      fetchModels(true);
    });
  });

  document.querySelectorAll(".gram-preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".gram-preset").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("filter-min-grams").value = btn.dataset.min;
      document.getElementById("filter-max-grams").value = btn.dataset.max;
      state.filters.min_grams = btn.dataset.min;
      state.filters.max_grams = btn.dataset.max;
      fetchModels(true);
    });
  });

  const directBindings = [
    ["filter-subcategory", "subcategory"],
    ["filter-from", "collected_from"],
    ["filter-to", "collected_to"],
    ["filter-max-mm", "max_dimension_mm"],
    ["filter-min-grams", "min_grams"],
    ["filter-max-grams", "max_grams"],
    ["filter-filament", "filament"],
    ["sort-select", "sort"],
  ];
  document.getElementById("filter-category").addEventListener("change", (e) => {
    state.filters.category = e.target.value;
    state.filters.subcategory = "";
    syncModelSubcatSelect(document.getElementById("filter-subcategory"), e.target.value, "", "Todas as subcategorias");
    fetchModels(true);
  });
  document.getElementById("edit-category").addEventListener("change", (e) => {
    syncModelSubcatSelect(document.getElementById("edit-subcategory"), e.target.value, "", "Sem subcategoria");
  });
  document.getElementById("models-manage-subs-btn").addEventListener("click", () => {
    hubCtrl?.openSubcategoriesModal("models", state.filters.category);
  });
  for (const [elId, key] of directBindings) {
    document.getElementById(elId).addEventListener("change", (e) => {
      state.filters[key] = e.target.value;
      fetchModels(true);
    });
  }

  document.getElementById("filter-include-multicolor").addEventListener("change", (e) => {
    state.filters.include_multicolor = e.target.checked;
    fetchModels(true);
  });

  document.getElementById("clear-filters-btn").addEventListener("click", clearAllFilters);
  document.getElementById("empty-clear-btn").addEventListener("click", clearAllFilters);
  document.getElementById("retry-btn").addEventListener("click", () => fetchModels(false));

  // Drawer events
  document.getElementById("edit-filaments-wrap").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-edit-filament]");
    if (btn) btn.classList.toggle("active");
  });
  document.getElementById("edit-colors-wrap").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-edit-color]");
    if (btn) btn.classList.toggle("active");
  });

  const closeDrawer = () => { document.getElementById("edit-backdrop").hidden = true; };
  document.getElementById("drawer-close-btn").addEventListener("click", closeDrawer);
  document.getElementById("drawer-cancel-btn").addEventListener("click", closeDrawer);

  document.getElementById("edit-add-class-btn").addEventListener("click", () => {
    const category = document.getElementById("edit-category").value;
    const subcategory = document.getElementById("edit-subcategory").value;
    if (!category) return;
    const exists = state.editClassifications.some(
      (c) => c.category === category && (c.subcategory || "") === (subcategory || "")
    );
    if (!exists) {
      state.editClassifications.push({ category, subcategory });
      state.editClassificationsDirty = true;
      renderEditClassifications();
    } else {
      showToast("Essa categoria/subcategoria já está vinculada.");
    }
  });

  document.getElementById("edit-classifications-list").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-remove-class]");
    if (!btn || state.editClassifications.length <= 1) return;
    const idx = Number(btn.dataset.removeClass);
    state.editClassifications.splice(idx, 1);
    state.editClassificationsDirty = true;
    const first = state.editClassifications[0];
    if (first) {
      document.getElementById("edit-category").value = first.category;
      syncModelSubcatSelect(
        document.getElementById("edit-subcategory"),
        first.category,
        first.subcategory || "",
        "Sem subcategoria"
      );
    }
    renderEditClassifications();
  });

  document.getElementById("edit-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = Number(document.getElementById("edit-id").value);
    const grams = document.getElementById("edit-grams").value;
    const mins = document.getElementById("edit-time").value;
    const curCat = document.getElementById("edit-category").value;
    const curSub = document.getElementById("edit-subcategory").value;
    const payloadClasses =
      state.editClassificationsDirty || state.editClassifications.length > 1
        ? state.editClassifications
        : [{ category: curCat, subcategory: curSub }];
    await apiJson(`/api/models/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        title: document.getElementById("edit-title").value.trim(),
        image_url: document.getElementById("edit-image-url").value.trim(),
        category: payloadClasses[0].category,
        subcategory: payloadClasses[0].subcategory || "",
        classifications: payloadClasses,
        status: document.getElementById("edit-status").value,
        size_tier: document.getElementById("edit-size-tier").value,
        dimensions_mm: document.getElementById("edit-dimensions").value.trim(),
        filament_grams: grams === "" ? null : Number(grams),
        print_time_min: mins === "" ? null : Number(mins),
        recommended_filaments: Array.from(document.querySelectorAll("[data-edit-filament].active")).map((b) => b.dataset.editFilament),
        recommended_colors: Array.from(document.querySelectorAll("[data-edit-color].active")).map((b) => b.dataset.editColor),
        filament_reason: document.getElementById("edit-reason").value.trim(),
        notes: document.getElementById("edit-notes").value.trim(),
      }),
    });
    closeDrawer();
    showToast("Modelo atualizado!");
    fetchModels(false);
  });

  document.getElementById("edit-image-url").addEventListener("input", (e) => {
    const val = e.target.value.trim();
    const prev = document.getElementById("edit-image-preview");
    if (val) {
      prev.src = val;
      prev.hidden = false;
    } else {
      prev.hidden = true;
    }
  });

  document.getElementById("edit-enrich-btn").addEventListener("click", async () => {
    const id = Number(document.getElementById("edit-id").value);
    try {
      const updated = await apiJson(`/api/models/${id}/enrich`, { method: "POST" });
      document.getElementById("edit-image-url").value = updated.image_url || "";
      if (updated.image_url) {
        const prev = document.getElementById("edit-image-preview");
        prev.src = updated.image_url;
        prev.hidden = false;
      }
      if (updated.filament_grams != null) document.getElementById("edit-grams").value = updated.filament_grams;
      if (updated.print_time_min != null) document.getElementById("edit-time").value = updated.print_time_min;
      showToast("Foto e metadados atualizados do MakerWorld!");
      fetchModels(false);
    } catch (err) {
      showToast(err.message || "Falha ao buscar no MakerWorld.");
    }
  });

  document.getElementById("enrich-images-btn").addEventListener("click", async () => {
    const btn = document.getElementById("enrich-images-btn");
    btn.disabled = true;
    const orig = btn.textContent;
    let offset = 0;
    let totalEnriched = 0;
    let totalChecked = 0;
    let remaining = 0;
    try {
      for (let batch = 0; batch < 60; batch++) {
        btn.textContent = totalChecked ? `Buscando (${totalEnriched} links, restam ${remaining})...` : "Buscando imagens...";
        const res = await apiJson(`/api/models/enrich-missing?limit=50&offset=${offset}`, { method: "POST" });
        totalEnriched += res.enriched || 0;
        totalChecked += res.requested || 0;
        remaining = res.total_missing || 0;
        offset = res.next_offset || 0;
        if (!res.has_more_missing || !res.requested) break;
      }
      showToast(
        totalEnriched > 0
          ? `${totalEnriched} modelo(s) atualizados com link de imagem! (${remaining} sem capa automática)`
          : `Busca concluída (${remaining} modelos seguem sem capa automática — clique em "Configurar link" nos cards).`
      );
      await fetchModels(false);
    } catch (err) {
      showToast(err.message || "Falha ao enriquecer modelos.");
    } finally {
      btn.disabled = false;
      btn.textContent = orig;
    }
  });

  document.getElementById("lightbox-close-btn").addEventListener("click", () => {
    document.getElementById("lightbox-backdrop").hidden = true;
  });
  document.getElementById("lightbox-backdrop").addEventListener("click", (e) => {
    if (e.target.id === "lightbox-backdrop") {
      document.getElementById("lightbox-backdrop").hidden = true;
    }
  });

  document.getElementById("drawer-delete-btn").addEventListener("click", async () => {
    const id = Number(document.getElementById("edit-id").value);
    await apiJson(`/api/models/${id}`, { method: "DELETE" });
    closeDrawer();
    showToast("Modelo removido.");
    await Promise.all([fetchModels(false), refreshSummary()]);
  });

  document.getElementById("drawer-to-catalog-btn").addEventListener("click", () => {
    const id = Number(document.getElementById("edit-id").value);
    const item = state.items.find((i) => i.id === id);
    if (!item) return;
    closeDrawer();
    document.getElementById("cat-id").value = "";
    document.getElementById("cat-model-id").value = item.id;
    document.getElementById("cat-code").value = "";
    document.getElementById("cat-name").value = item.title;
    document.getElementById("cat-category").value = item.category;
    hubCtrl?.syncCatalogSubcatSelect(item.category, item.subcategory || "");
    hubCtrl?.setCatalogClassifications(item.classifications || [{ category: item.category, subcategory: item.subcategory || "" }]);
    document.getElementById("cat-grams").value = item.filament_grams || 50;
    document.getElementById("cat-image").value = item.image_url || "";
    const prev = document.getElementById("cat-image-preview");
    if (item.image_url) {
      prev.src = item.image_url;
      prev.hidden = false;
    } else {
      prev.hidden = true;
    }
    document.getElementById("catalog-modal-title").textContent = "Enviar Modelo para Catálogo de Vendas";
    document.getElementById("catalog-backdrop").hidden = false;
  });

  document.getElementById("open-ext-modal-btn").addEventListener("click", () => {
    document.getElementById("ext-backdrop").hidden = false;
  });
  document.getElementById("ext-close-btn").addEventListener("click", () => {
    document.getElementById("ext-backdrop").hidden = true;
  });
}

async function init() {
  state.meta = await apiJson("/api/catalog-meta");
  populateMetaControls();
  hubCtrl = createHubController({
    meta: state.meta,
    refreshSummary,
    switchTab,
    reloadModels: () => fetchModels(false),
    onSubcategoriesChanged: refreshModelSubcategories,
    applyModelSubcatFilter: (cat, subcat) => {
      state.filters.category = cat || "";
      state.filters.subcategory = subcat || "";
      document.getElementById("filter-category").value = state.filters.category;
      syncModelSubcatSelect(
        document.getElementById("filter-subcategory"),
        state.filters.category,
        state.filters.subcategory,
        "Todas as subcategorias"
      );
      switchTab("models");
      fetchModels(true);
    },
  });
  hubCtrl.bindEvents();
  bindModelsEvents();
  await Promise.all([refreshModelSubcategories(), fetchModels(true), refreshSummary()]);
}

init().catch((err) => {
  document.getElementById("error-text").textContent = err.message || "Falha ao inicializar Hub.";
  document.getElementById("error-banner").hidden = false;
});
