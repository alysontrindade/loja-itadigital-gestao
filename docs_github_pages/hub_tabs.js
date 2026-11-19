import { apiJson, escapeHtml, formatBrl, formatDateTimePtBr, formatDuration, formatGrams, showToast } from "./utils.js?v=2.1.0";

export function createHubController({ meta, refreshSummary, switchTab, reloadModels, onSubcategoriesChanged, applyModelSubcatFilter }) {
  const hubState = {
    printers: [],
    spools: [],
    rubrics: [],
    slicingProfiles: [],
    jobs: [],
    catalog: [],
    sales: [],
    media: [],
    subcategories: [],
  };

  let pendingFiles = [];
  let editingSubId = null;
  let editingRubricId = null;
  let editingSlicingId = null;
  let lastProfileAutoNote = "";
  let catFormClassifications = [];
  let catFormClassificationsDirty = false;

  function renderCatExtraBadges(item) {
    const pairs =
      Array.isArray(item.classifications) && item.classifications.length
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

  function renderCatFormClassifications() {
    const wrap = document.getElementById("cat-classifications-list");
    if (!wrap) return;
    wrap.innerHTML = catFormClassifications
      .map((pair, idx) => {
        const label = pair.subcategory ? `${pair.category} › ${pair.subcategory}` : pair.category;
        const removeBtn =
          catFormClassifications.length > 1
            ? `<button type="button" class="class-chip-remove" data-cat-remove-class="${idx}" title="Remover classificação">×</button>`
            : "";
        return `<span class="class-chip ${idx === 0 ? "primary" : ""}">${escapeHtml(label)}${removeBtn}</span>`;
      })
      .join("");
  }

  function setCatalogClassifications(pairs) {
    catFormClassifications = (Array.isArray(pairs) && pairs.length ? pairs : [])
      .map((c) => ({ category: String(c.category || "").trim(), subcategory: String(c.subcategory || "").trim() }))
      .filter((c) => c.category);
    catFormClassificationsDirty = catFormClassifications.length > 1;
    renderCatFormClassifications();
  }

  function getCategoriesForScope(scope) {
    const fromSubs = hubState.subcategories.filter((s) => s.scope === scope).map((s) => s.category);
    if (scope === "models") {
      return Array.from(new Set([...(meta?.categories || []), ...fromSubs])).sort((a, b) => a.localeCompare(b));
    }
    const fromCatalog = hubState.catalog.flatMap((c) => c.categories || (c.category ? [c.category] : [])).filter(Boolean);
    return Array.from(new Set([...fromCatalog, ...fromSubs])).sort((a, b) => a.localeCompare(b));
  }

  function syncCatalogSubcatSelect(category, currentVal = "") {
    const sel = document.getElementById("cat-subcategory");
    if (!sel) return;
    const cat = String(category || "").trim();
    const names = Array.from(
      new Set(
        hubState.subcategories
          .filter((s) => s.scope === "sales_catalog" && (!cat || s.category === cat))
          .map((s) => s.name)
      )
    );
    if (currentVal && !names.includes(currentVal)) names.unshift(currentVal);
    sel.innerHTML = ['<option value="">Sem subcategoria</option>']
      .concat(names.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`))
      .join("");
    sel.value = currentVal && names.includes(currentVal) ? currentVal : "";
  }

  function syncCatalogFilterSelects() {
    const catSel = document.getElementById("catalog-filter-category");
    const subSel = document.getElementById("catalog-filter-subcategory");
    const catList = document.getElementById("cat-category-list");
    if (!catSel || !subSel) return;

    const curCat = catSel.value;
    const curSub = subSel.value;
    const cats = getCategoriesForScope("sales_catalog");
    catSel.innerHTML = ['<option value="">Todas categorias</option>']
      .concat(cats.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`))
      .join("");
    catSel.value = cats.includes(curCat) ? curCat : "";

    if (catList) {
      catList.innerHTML = cats.map((c) => `<option value="${escapeHtml(c)}"></option>`).join("");
    }

    const activeCat = catSel.value;
    const subs = Array.from(
      new Set([
        ...hubState.subcategories
          .filter((s) => s.scope === "sales_catalog" && (!activeCat || s.category === activeCat))
          .map((s) => s.name),
        ...hubState.catalog
          .flatMap((c) => c.classifications || [{ category: c.category, subcategory: c.subcategory || "" }])
          .filter((p) => p.subcategory && (!activeCat || p.category === activeCat))
          .map((p) => p.subcategory),
      ])
    ).sort((a, b) => a.localeCompare(b));

    subSel.innerHTML = ['<option value="">Todas subcategorias</option>']
      .concat(subs.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`))
      .join("");
    subSel.value = subs.includes(curSub) ? curSub : "";
  }

  async function loadSubcategories() {
    const res = await apiJson("/api/subcategories");
    hubState.subcategories = res.items || [];
    syncCatalogFilterSelects();
  }

  function renderSubcategoriesManagerList() {
    const scope = document.getElementById("subcat-scope").value;
    const filterCatSel = document.getElementById("subcat-filter-cat");
    const datalist = document.getElementById("subcat-cat-datalist");
    const cats = getCategoriesForScope(scope);

    const curFilterCat = filterCatSel.value;
    filterCatSel.innerHTML = ['<option value="">Todas as categorias</option>']
      .concat(cats.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`))
      .join("");
    filterCatSel.value = cats.includes(curFilterCat) ? curFilterCat : "";
    datalist.innerHTML = cats.map((c) => `<option value="${escapeHtml(c)}"></option>`).join("");

    const activeCat = filterCatSel.value;
    const rows = hubState.subcategories.filter((s) => s.scope === scope && (!activeCat || s.category === activeCat));
    const listEl = document.getElementById("subcat-list");

    if (!rows.length) {
      listEl.innerHTML = `<div class="empty-state"><h3>Nenhuma subcategoria neste filtro</h3><p>Use o formulário acima para criar a primeira subcategoria.</p></div>`;
      return;
    }

    listEl.innerHTML = rows
      .map((s) => {
        if (editingSubId === s.id) {
          return `
            <div class="subcat-item" style="flex-direction:column; align-items:stretch;">
              <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                <input class="input subcat-edit-cat" data-id="${s.id}" type="text" list="subcat-cat-datalist" value="${escapeHtml(s.category)}" />
                <input class="input subcat-edit-name" data-id="${s.id}" type="text" value="${escapeHtml(s.name)}" />
              </div>
              <div style="display:flex; justify-content:flex-end; gap:6px;">
                <button class="btn btn-secondary btn-xs subcat-edit-cancel" type="button">Cancelar</button>
                <button class="btn btn-primary btn-xs subcat-edit-save" data-id="${s.id}" type="button">Salvar Alteração</button>
              </div>
            </div>
          `;
        }
        return `
          <div class="subcat-item">
            <div class="subcat-meta">
              <span class="subcat-cat-label">${escapeHtml(s.category)}</span>
              <span class="subcat-name-label">${escapeHtml(s.name)}</span>
            </div>
            <span class="badge tnum">${s.items_count} ${s.items_count === 1 ? "item" : "itens"}</span>
            <div class="card-actions">
              <button class="btn btn-ghost btn-xs subcat-filter-btn" data-id="${s.id}" type="button">Filtrar</button>
              <button class="btn btn-secondary btn-xs subcat-edit-btn" data-id="${s.id}" type="button">Editar</button>
              <button class="btn btn-danger btn-xs subcat-del-btn" data-id="${s.id}" type="button">Excluir</button>
            </div>
          </div>
        `;
      })
      .join("");

    listEl.querySelectorAll(".subcat-edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        editingSubId = Number(btn.dataset.id);
        renderSubcategoriesManagerList();
      });
    });

    listEl.querySelectorAll(".subcat-edit-cancel").forEach((btn) => {
      btn.addEventListener("click", () => {
        editingSubId = null;
        renderSubcategoriesManagerList();
      });
    });

    listEl.querySelectorAll(".subcat-edit-save").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.dataset.id);
        const catVal = listEl.querySelector(`.subcat-edit-cat[data-id="${id}"]`)?.value.trim() || "";
        const nameVal = listEl.querySelector(`.subcat-edit-name[data-id="${id}"]`)?.value.trim() || "";
        try {
          await apiJson(`/api/subcategories/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ category: catVal, name: nameVal }),
          });
          editingSubId = null;
          showToast("Subcategoria atualizada em todos os itens!");
          await loadSubcategories();
          renderSubcategoriesManagerList();
          if (scope === "sales_catalog") await renderCatalogTab();
          else {
            if (onSubcategoriesChanged) await onSubcategoriesChanged();
            if (reloadModels) await reloadModels();
          }
        } catch (err) {
          showToast(err.message || "Falha ao atualizar subcategoria.");
        }
      });
    });

    listEl.querySelectorAll(".subcat-filter-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const s = hubState.subcategories.find((x) => x.id === Number(btn.dataset.id));
        if (!s) return;
        document.getElementById("subcat-backdrop").hidden = true;
        if (s.scope === "sales_catalog") {
          document.getElementById("catalog-filter-category").value = s.category;
          syncCatalogFilterSelects();
          document.getElementById("catalog-filter-subcategory").value = s.name;
          await switchTab("catalog");
        } else if (applyModelSubcatFilter) {
          applyModelSubcatFilter(s.category, s.name);
        }
      });
    });

    listEl.querySelectorAll(".subcat-del-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.dataset.id);
        await apiJson(`/api/subcategories/${id}`, { method: "DELETE" });
        editingSubId = null;
        showToast("Subcategoria excluída.");
        await loadSubcategories();
        renderSubcategoriesManagerList();
        if (scope === "sales_catalog") await renderCatalogTab();
        else {
          if (onSubcategoriesChanged) await onSubcategoriesChanged();
          if (reloadModels) await reloadModels();
        }
      });
    });
  }

  async function openSubcategoriesModal(scope = "sales_catalog", initialCategory = "") {
    editingSubId = null;
    await loadSubcategories();
    document.getElementById("subcat-scope").value = scope;
    if (initialCategory) {
      document.getElementById("subcat-parent-cat").value = initialCategory;
    }
    renderSubcategoriesManagerList();
    document.getElementById("subcat-backdrop").hidden = false;
  }

  async function loadPrintersAndSpools() {
    const [pr, sp, rb, sl] = await Promise.all([
      apiJson("/api/printers"),
      apiJson("/api/spools"),
      apiJson("/api/rubrics"),
      apiJson("/api/slicing-profiles"),
    ]);
    hubState.printers = pr.items;
    hubState.spools = sp.items;
    hubState.rubrics = rb.items;
    hubState.slicingProfiles = sl.items;
    syncSelectOptions();
  }

  function syncSelectOptions() {
    const curJobPrinter = document.getElementById("job-printer")?.value || "";
    const curFilterPrinter = document.getElementById("queue-filter-printer")?.value || "";
    const printerOpts = ['<option value="">Sem impressora definida</option>']
      .concat(hubState.printers.map((p) => `<option value="${p.id}">${escapeHtml(p.name)} (${escapeHtml(p.status)})</option>`))
      .join("");
    document.getElementById("job-printer").innerHTML = printerOpts;
    if (curJobPrinter) document.getElementById("job-printer").value = curJobPrinter;

    document.getElementById("queue-filter-printer").innerHTML =
      '<option value="">Todas as impressoras</option>' +
      '<option value="__none__">Sem impressora definida</option>' +
      hubState.printers.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join("");
    if (curFilterPrinter) document.getElementById("queue-filter-printer").value = curFilterPrinter;

    const curJobSpool = document.getElementById("job-spool")?.value || "";
    const curFilterSpool = document.getElementById("queue-filter-spool")?.value || "";
    const spoolOpts = ['<option value="">Sem carretel vinculado</option>']
      .concat(
        hubState.spools.map(
          (s) =>
            `<option value="${s.id}">${escapeHtml(s.material)} ${escapeHtml(s.color_name)}${s.brand ? ` (${escapeHtml(s.brand)})` : ""} — ${formatGrams(s.remaining_grams)}</option>`
        )
      )
      .join("");
    document.getElementById("job-spool").innerHTML = spoolOpts;
    if (curJobSpool) document.getElementById("job-spool").value = curJobSpool;
    const filterSpoolEl = document.getElementById("queue-filter-spool");
    if (filterSpoolEl) {
      filterSpoolEl.innerHTML =
        '<option value="">Todos os filamentos</option>' +
        hubState.spools
          .map((s) => `<option value="${s.id}">${escapeHtml(s.material)} ${escapeHtml(s.color_name)} (${formatGrams(s.remaining_grams)})</option>`)
          .join("");
      if (curFilterSpool) filterSpoolEl.value = curFilterSpool;
    }

    const curJobRubric = document.getElementById("job-rubric")?.value || "";
    const curFilterRubric = document.getElementById("queue-filter-rubric")?.value || "";
    const jobRubricEl = document.getElementById("job-rubric");
    if (jobRubricEl) {
      jobRubricEl.innerHTML =
        '<option value="">Sem rubrica</option>' +
        hubState.rubrics.map((r) => `<option value="${r.id}">${escapeHtml(r.name)}</option>`).join("");
      if (curJobRubric) jobRubricEl.value = curJobRubric;
    }
    const filterRubricEl = document.getElementById("queue-filter-rubric");
    if (filterRubricEl) {
      filterRubricEl.innerHTML =
        '<option value="">Todas as rubricas</option>' +
        hubState.rubrics.map((r) => `<option value="${r.id}">${escapeHtml(r.name)} (${r.jobs_count})</option>`).join("");
      if (curFilterRubric) filterRubricEl.value = curFilterRubric;
    }

    const curJobSlicing = document.getElementById("job-slicing-profile")?.value || "";
    const curFilterSlicing = document.getElementById("queue-filter-slicing")?.value || "";
    const jobSlicingEl = document.getElementById("job-slicing-profile");
    if (jobSlicingEl) {
      jobSlicingEl.innerHTML =
        '<option value="">Selecione um perfil...</option>' +
        hubState.slicingProfiles
          .map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`)
          .join("");
      if (curJobSlicing) jobSlicingEl.value = curJobSlicing;
    }
    const filterSlicingEl = document.getElementById("queue-filter-slicing");
    if (filterSlicingEl) {
      filterSlicingEl.innerHTML =
        '<option value="">Todos os perfis</option>' +
        hubState.slicingProfiles.map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join("");
      if (curFilterSlicing) filterSlicingEl.value = curFilterSlicing;
    }

    const spMat = document.getElementById("sp-material");
    const filterMat = document.getElementById("spool-filter-material");
    if (meta?.filaments) {
      const fOpts = meta.filaments.map((f) => `<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`).join("");
      spMat.innerHTML = fOpts;
      const curFilter = filterMat.value;
      filterMat.innerHTML = '<option value="">Todos os materiais</option>' + fOpts;
      filterMat.value = curFilter;
    }

    const catSel = document.getElementById("sale-catalog");
    const mediaCatSel = document.getElementById("media-up-catalog");
    if (hubState.catalog.length) {
      catSel.innerHTML = hubState.catalog
        .map((c) => `<option value="${c.id}">${escapeHtml(c.code ? `${c.code} ` : "")}${escapeHtml(c.name)} (${formatBrl(c.sale_price_brl)} • estq: ${c.stock_qty})</option>`)
        .join("");
      mediaCatSel.innerHTML =
        '<option value="">Vincular ao catálogo (opcional)</option>' +
        hubState.catalog.map((c) => `<option value="${c.id}">${escapeHtml(c.code ? `${c.code} ` : "")}${escapeHtml(c.name)}</option>`).join("");
    } else {
      catSel.innerHTML = '<option value="">Cadastre um produto primeiro</option>';
      mediaCatSel.innerHTML = '<option value="">Vincular ao catálogo (opcional)</option>';
    }

    const mediaJobSel = document.getElementById("media-up-job");
    mediaJobSel.innerHTML =
      '<option value="">Vincular a impressão (opcional)</option>' +
      hubState.jobs.slice(0, 40).map((j) => `<option value="${j.id}">#${j.id} ${escapeHtml(j.title)} (${escapeHtml(j.status)})</option>`).join("");
  }

  function statusBadgeClass(status) {
    if (status === "Disponível" || status === "Concluída" || status === "Pago" || status === "Postado" || status === "Pronta Entrega") return "badge-success";
    if (status === "Imprimindo" || status === "Em Impressão" || status === "Agendado" || status === "Sinal 50%") return "badge-warn";
    if (status === "Falhou" || status === "Manutenção" || status === "Pendente") return "badge-info";
    if (status === "Cancelada") return "badge-danger";
    return "badge-muted";
  }

  // ---- TAB 2: FILA DE IMPRESSÃO ---- //

  function renderQueueCardHtml(j) {
    const printerOpts = ['<option value="">Sem impressora</option>']
      .concat(hubState.printers.map((p) => `<option value="${p.id}" ${p.id === j.printer_id ? "selected" : ""}>${escapeHtml(p.name)}</option>`))
      .join("");
    const timeStr = formatDuration(j.estimated_time_min) || "—";
    const prioBadge = j.priority === "Urgente" ? "badge-danger" : j.priority === "Alta" ? "badge-warn" : "badge-muted";
    const rubricHtml = j.rubric_name
      ? `<span class="rubric-badge"><span class="rubric-dot" style="background:${escapeHtml(j.rubric_color || "#22d3ee")};"></span>${escapeHtml(j.rubric_name)}</span>`
      : `<span class="badge badge-muted">Sem rubrica</span>`;
    const slicingHtml = j.slicing_profile_name
      ? `<span class="slicing-pill">${escapeHtml(j.slicing_profile_name)}</span>`
      : j.layer_height_mm
        ? `<span class="slicing-pill">${Number(j.layer_height_mm).toFixed(2)} mm</span>`
        : "";
    const filamentWarn = !j.filament_ok && j.spool_remaining_grams != null
      ? `<span style="color:#f87171; font-weight:600;">⚠ Saldo carretel (${formatGrams(j.spool_remaining_grams)})</span>`
      : "";
    let actionsHtml = "";
    if (j.status === "Pendente") {
      actionsHtml = `
        <select class="select job-assign-printer" data-id="${j.id}" style="width:auto;">${printerOpts}</select>
        <button class="btn btn-accent btn-sm job-start-btn" data-id="${j.id}" type="button">Iniciar</button>
      `;
    } else if (j.status === "Em Impressão") {
      actionsHtml = `
        <button class="btn btn-success btn-sm job-complete-btn" data-id="${j.id}" type="button">Concluir</button>
        <button class="btn btn-danger btn-sm job-fail-btn" data-id="${j.id}" type="button">Falhou</button>
      `;
    } else if (j.status === "Concluída") {
      actionsHtml = `<button class="btn btn-secondary btn-sm job-post-btn" data-id="${j.id}" data-title="${escapeHtml(j.title)}" type="button">Postar Foto</button>`;
    }
    return `
      <article class="queue-row">
        <div class="queue-main">
          <div class="queue-top">
            <span class="badge ${statusBadgeClass(j.status)}">${escapeHtml(j.status)}</span>
            <span class="badge ${prioBadge}">${escapeHtml(j.priority)}</span>
            ${rubricHtml}
            ${slicingHtml}
            <span class="badge badge-purple">${escapeHtml(j.target_type)}</span>
            <h3 class="queue-title">${escapeHtml(j.title)} <span class="tnum" style="color:var(--muted);">(${j.quantity}x)</span></h3>
          </div>
          <div class="queue-meta tnum">
            <span>Impressora: <strong>${escapeHtml(j.printer_name || "A definir")}</strong></span>
            <span>Filamento: <strong>${formatGrams(j.estimated_grams)}</strong>${j.spool_label ? ` • ${escapeHtml(j.spool_label)}` : ""}</span>
            ${filamentWarn}
            <span>Tempo est.: <strong>${timeStr}</strong></span>
            ${j.customer_name ? `<span>Cliente: <strong>${escapeHtml(j.customer_name)}</strong></span>` : ""}
            ${j.failure_reason ? `<span style="color:var(--danger);">Motivo: ${escapeHtml(j.failure_reason)}</span>` : ""}
          </div>
          ${j.slicing_notes ? `<div class="slicing-note-line"><strong>Fatiamento:</strong> ${escapeHtml(j.slicing_notes)}</div>` : ""}
          ${j.notes ? `<div class="queue-meta" style="margin-top:2px;"><span>Obs.: ${escapeHtml(j.notes)}</span></div>` : ""}
        </div>
        <div class="queue-actions">
          ${actionsHtml}
          <button class="btn btn-secondary btn-sm job-edit-btn" data-id="${j.id}" type="button">Editar</button>
          <button class="btn btn-secondary btn-sm job-archive-btn" data-id="${j.id}" type="button">Arquivar</button>
          <button class="btn btn-ghost btn-sm job-del-btn" data-id="${j.id}" type="button">Remover</button>
        </div>
      </article>
    `;
  }

  async function renderQueueTab() {
    await loadPrintersAndSpools();
    const status = document.getElementById("queue-filter-status").value;
    const printerVal = document.getElementById("queue-filter-printer").value;
    const rubricId = document.getElementById("queue-filter-rubric")?.value || "";
    const slicingId = document.getElementById("queue-filter-slicing")?.value || "";
    const spoolId = document.getElementById("queue-filter-spool")?.value || "";
    const targetType = document.getElementById("queue-filter-target")?.value || "";
    const priority = document.getElementById("queue-filter-priority")?.value || "";
    const q = document.getElementById("queue-filter-q")?.value.trim() || "";
    const groupMode = document.getElementById("queue-group-mode")?.value || "printer";

    const params = new URLSearchParams();
    if (status) params.set("status", status);
    else params.set("exclude_archived", "true");
    if (printerVal === "__none__") params.set("unassigned_printer", "true");
    else if (printerVal) params.set("printer_id", printerVal);
    if (rubricId) params.set("rubric_id", rubricId);
    if (slicingId) params.set("slicing_profile_id", slicingId);
    if (spoolId) params.set("spool_id", spoolId);
    if (targetType) params.set("target_type", targetType);
    if (priority) params.set("priority", priority);
    if (q) params.set("q", q);

    const data = await apiJson(`/api/queue?${params.toString()}`);
    hubState.jobs = data.items;

    document.getElementById("queue-metrics").innerHTML = `
      <div class="metric-tile"><div class="metric-value tnum">${data.active_count}</div><div class="metric-caption">Imprimindo agora</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${data.pending_count}</div><div class="metric-caption">Pendentes na fila</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${formatGrams(data.total_estimated_grams)}</div><div class="metric-caption">Filamento necessário</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${data.done_count}</div><div class="metric-caption">Peças concluídas</div></div>
    `;

    const listEl = document.getElementById("queue-list");
    const hasAnyFilter = Boolean(status || printerVal || rubricId || slicingId || spoolId || targetType || priority || q);

    if (groupMode === "printer") {
      const printersToShow =
        printerVal === "__none__"
          ? []
          : printerVal
            ? hubState.printers.filter((p) => String(p.id) === printerVal)
            : hubState.printers;

      const sections = [];
      for (const p of printersToShow) {
        const pJobs = data.items.filter((j) => j.printer_id === p.id);
        if (hasAnyFilter && !pJobs.length && printerVal !== String(p.id)) continue;
        const pGrams = pJobs.filter((i) => i.status === "Pendente" || i.status === "Em Impressão").reduce((acc, i) => acc + i.estimated_grams, 0);
        const pActive = pJobs.filter((i) => i.status === "Em Impressão").length;
        const pPend = pJobs.filter((i) => i.status === "Pendente").length;
        const liveStatus = pActive > 0 ? "Imprimindo" : p.status;
        const liveBadgeClass = pActive > 0 ? "badge-warn" : statusBadgeClass(p.status);
        sections.push(`
          <section class="printer-queue-section">
            <header class="printer-queue-header">
              <div class="printer-queue-title-wrap">
                <h3 class="printer-queue-title">${escapeHtml(p.name)}</h3>
                <span class="badge ${liveBadgeClass}">${escapeHtml(liveStatus)}</span>
                <span class="brand-sub tnum">${escapeHtml(p.brand_model)} • Bico ${p.nozzle_mm} mm • ${pActive} imprimindo · ${pPend} pendentes · ${formatGrams(pGrams)}</span>
              </div>
              <button class="btn btn-primary btn-xs printer-queue-add-btn" data-printer-id="${p.id}" type="button">+ Adicionar nesta impressora</button>
            </header>
            <div class="printer-queue-body">
              ${
                pJobs.length
                  ? pJobs.map(renderQueueCardHtml).join("")
                  : `<div class="brand-sub" style="padding:8px 4px;">Nenhum trabalho na fila desta impressora neste filtro.</div>`
              }
            </div>
          </section>
        `);
      }

      const unassigned = data.items.filter((j) => !j.printer_id);
      if (unassigned.length || printerVal === "__none__") {
        sections.push(`
          <section class="printer-queue-section">
            <header class="printer-queue-header">
              <div class="printer-queue-title-wrap">
                <h3 class="printer-queue-title">A definir / Sem impressora</h3>
                <span class="badge badge-muted">${unassigned.length} itens</span>
              </div>
              <button class="btn btn-secondary btn-xs printer-queue-add-btn" data-printer-id="" type="button">+ Novo Trabalho</button>
            </header>
            <div class="printer-queue-body">
              ${
                unassigned.length
                  ? unassigned.map(renderQueueCardHtml).join("")
                  : `<div class="brand-sub" style="padding:8px 4px;">Nenhum trabalho sem impressora definida.</div>`
              }
            </div>
          </section>
        `);
      }

      listEl.innerHTML = sections.length
        ? sections.join("")
        : `<div class="state-box"><h2>Fila vazia neste filtro</h2><p>Cadastre uma impressora ou ajuste os filtros acima.</p></div>`;
    } else if (groupMode === "rubric") {
      if (!data.items.length) {
        listEl.innerHTML = `<div class="state-box"><h2>Fila vazia neste filtro</h2><p>Adicione trabalhos na fila ou limpe os filtros.</p></div>`;
        return;
      }
      const byRubric = new Map();
      for (const j of data.items) {
        const key = j.rubric_name || "Sem rubrica";
        if (!byRubric.has(key)) byRubric.set(key, { color: j.rubric_color || "#94a3b8", rubricId: j.rubric_id, items: [] });
        byRubric.get(key).items.push(j);
      }
      listEl.innerHTML = Array.from(byRubric.entries())
        .map(([rName, grp]) => {
          const grams = grp.items.filter((i) => i.status === "Pendente" || i.status === "Em Impressão").reduce((acc, i) => acc + i.estimated_grams, 0);
          return `
            <section class="printer-queue-section">
              <header class="printer-queue-header">
                <div class="printer-queue-title-wrap">
                  <span class="rubric-dot" style="background:${escapeHtml(grp.color)}; width:11px; height:11px;"></span>
                  <h3 class="printer-queue-title">${escapeHtml(rName)}</h3>
                  <span class="badge badge-muted tnum">${grp.items.length} trabalhos · ${formatGrams(grams)}</span>
                </div>
                <button class="btn btn-primary btn-xs rubric-queue-add-btn" data-rubric-id="${grp.rubricId || ""}" type="button">+ Adicionar nesta rubrica</button>
              </header>
              <div class="printer-queue-body">${grp.items.map(renderQueueCardHtml).join("")}</div>
            </section>
          `;
        })
        .join("");
    } else {
      if (!data.items.length) {
        listEl.innerHTML = `<div class="state-box"><h2>Fila vazia neste filtro</h2><p>Adicione modelos da aba Modelos ou clique em "+ Novo Trabalho na Fila".</p></div>`;
        return;
      }
      listEl.innerHTML = data.items.map(renderQueueCardHtml).join("");
    }

    listEl.querySelectorAll(".printer-queue-add-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const pid = btn.dataset.printerId ? Number(btn.dataset.printerId) : null;
        openJobModal({ printer_id: pid });
      });
    });

    listEl.querySelectorAll(".rubric-queue-add-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const rid = btn.dataset.rubricId ? Number(btn.dataset.rubricId) : null;
        openJobModal({ rubric_id: rid });
      });
    });

    listEl.querySelectorAll(".job-edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const job = hubState.jobs.find((x) => x.id === Number(btn.dataset.id));
        if (job) openJobModal(job);
      });
    });

    listEl.querySelectorAll(".job-assign-printer").forEach((sel) => {
      sel.addEventListener("change", async () => {
        await apiJson(`/api/queue/${sel.dataset.id}`, {
          method: "PATCH",
          body: JSON.stringify({ printer_id: sel.value ? Number(sel.value) : null }),
        });
        showToast("Impressora atribuída.");
        await Promise.all([renderQueueTab(), refreshSummary()]);
      });
    });

    listEl.querySelectorAll(".job-start-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/queue/${btn.dataset.id}`, { method: "PATCH", body: JSON.stringify({ status: "Em Impressão" }) });
        showToast("Impressão iniciada!");
        await Promise.all([renderQueueTab(), refreshSummary()]);
      });
    });

    listEl.querySelectorAll(".job-complete-btn").forEach((btn) => {
      btn.addEventListener("click", () => openFinishModal(Number(btn.dataset.id), "Concluída"));
    });

    listEl.querySelectorAll(".job-fail-btn").forEach((btn) => {
      btn.addEventListener("click", () => openFinishModal(Number(btn.dataset.id), "Falhou"));
    });

    listEl.querySelectorAll(".job-post-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.getElementById("media-up-title").value = btn.dataset.title || "";
        document.getElementById("media-up-job").value = btn.dataset.id;
        switchTab("media");
      });
    });

    listEl.querySelectorAll(".job-archive-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/queue/${btn.dataset.id}`, {
          method: "PATCH",
          body: JSON.stringify({ status: "Arquivado" }),
        });
        showToast("Trabalho movido para Arquivados.");
        await Promise.all([renderQueueTab(), refreshSummary()]);
      });
    });

    listEl.querySelectorAll(".job-del-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/queue/${btn.dataset.id}`, { method: "DELETE" });
        showToast("Trabalho removido da fila.");
        await Promise.all([renderQueueTab(), refreshSummary()]);
      });
    });
  }

  function openFinishModal(jobId, targetStatus) {
    const job = hubState.jobs.find((j) => j.id === jobId);
    document.getElementById("finish-job-id").value = jobId;
    document.getElementById("finish-job-status").value = targetStatus;
    document.getElementById("finish-job-title").textContent =
      targetStatus === "Concluída" ? "Concluir Impressão & Dar Baixa no Filamento" : "Registrar Falha na Impressão";
    document.getElementById("finish-job-grams").value = job ? job.estimated_grams : 0;
    document.getElementById("finish-reason-wrap").hidden = targetStatus !== "Falhou";
    document.getElementById("finish-job-reason").value = "";
    document.getElementById("finish-job-backdrop").hidden = false;
  }

  // ---- TAB 3: IMPRESSORAS ---- //

  async function renderPrintersTab() {
    await loadPrintersAndSpools();
    const grid = document.getElementById("printers-grid");
    if (!hubState.printers.length) {
      grid.innerHTML = `<div class="state-box"><h2>Nenhuma impressora cadastrada</h2><p>Cadastre sua Bambu Lab A1 ou outras impressoras.</p></div>`;
      return;
    }
    grid.innerHTML = hubState.printers
      .map((p) => {
        const amsHtml = p.has_ams
          ? `<div class="specs-strip">${Array.from({ length: p.ams_slots || 4 })
              .map((_, idx) => `<span class="spec-pill">AMS #${idx + 1}</span>`)
              .join("")}</div>`
          : '<span class="spec-pill">Carretel Externo (Single)</span>';
        return `
          <article class="card">
            <div class="card-body">
              <div class="card-category-row">
                <span>${escapeHtml(p.brand_model)}</span>
                <span class="badge ${statusBadgeClass(p.status)}">${escapeHtml(p.status)}</span>
              </div>
              <h3 class="card-title">${escapeHtml(p.name)}</h3>
              <div class="specs-strip tnum">
                <span class="spec-pill">Mesa: <strong>${escapeHtml(p.build_volume_mm)}</strong></span>
                <span class="spec-pill">Bico: <strong>${p.nozzle_mm} mm</strong></span>
                <span class="spec-pill">Custo/h: <strong>${formatBrl(p.hourly_cost_brl)}</strong></span>
              </div>
              ${amsHtml}
              <div class="specs-strip tnum">
                <span class="spec-pill">Rodando: <strong>${p.active_jobs_count}</strong></span>
                <span class="spec-pill">Na fila dela: <strong>${p.queued_jobs_count}</strong></span>
              </div>
              ${p.notes ? `<p class="rec-reason">${escapeHtml(p.notes)}</p>` : ""}
            </div>
            <div class="card-footer">
              <button class="btn btn-secondary btn-xs pr-edit-btn" data-id="${p.id}" type="button">Editar</button>
              <button class="btn btn-danger btn-xs pr-del-btn" data-id="${p.id}" type="button">Excluir</button>
            </div>
          </article>
        `;
      })
      .join("");

    grid.querySelectorAll(".pr-edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = hubState.printers.find((x) => x.id === Number(btn.dataset.id));
        if (!p) return;
        document.getElementById("printer-modal-title").textContent = "Editar Impressora";
        document.getElementById("pr-id").value = p.id;
        document.getElementById("pr-name").value = p.name;
        document.getElementById("pr-model").value = p.brand_model;
        document.getElementById("pr-volume").value = p.build_volume_mm;
        document.getElementById("pr-max-dim").value = p.max_dim_mm;
        document.getElementById("pr-nozzle").value = p.nozzle_mm;
        document.getElementById("pr-ams-slots").value = p.ams_slots;
        document.getElementById("pr-hourly").value = p.hourly_cost_brl;
        document.getElementById("pr-status").value = p.status;
        document.getElementById("pr-notes").value = p.notes;
        document.getElementById("printer-backdrop").hidden = false;
      });
    });

    grid.querySelectorAll(".pr-del-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/printers/${btn.dataset.id}`, { method: "DELETE" });
        showToast("Impressora removida.");
        await Promise.all([renderPrintersTab(), refreshSummary()]);
      });
    });
  }

  // ---- TAB 4: ESTOQUE ---- //

  async function renderInventoryTab() {
    const material = document.getElementById("spool-filter-material").value;
    const lowOnly = document.getElementById("spool-filter-low").checked;
    const params = new URLSearchParams();
    if (material) params.set("material", material);
    if (lowOnly) params.set("low_only", "true");

    const [spData, catData] = await Promise.all([
      apiJson(`/api/spools?${params.toString()}`),
      apiJson("/api/catalog"),
    ]);
    hubState.spools = spData.items;
    hubState.catalog = catData.items;
    syncSelectOptions();

    document.getElementById("inventory-metrics").innerHTML = `
      <div class="metric-tile"><div class="metric-value tnum">${spData.total}</div><div class="metric-caption">Carretéis cadastrados</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${formatGrams(spData.total_remaining_grams)}</div><div class="metric-caption">Filamento em estoque</div></div>
      <div class="metric-tile"><div class="metric-value tnum" style="color:${spData.low_stock_count > 0 ? "var(--danger)" : "var(--success)"};">${spData.low_stock_count}</div><div class="metric-caption">Carretéis em alerta baixo</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${catData.total_ready_units} un.</div><div class="metric-caption">Peças em pronta entrega</div></div>
    `;

    const grid = document.getElementById("spools-grid");
    if (!spData.items.length) {
      grid.innerHTML = `<div class="state-box"><h2>Nenhum carretel neste filtro</h2><p>Cadastre seus rolos de PLA/PETG/ABS para baixar gramas automaticamente a cada impressão concluída.</p></div>`;
    } else {
      grid.innerHTML = spData.items
        .map((s) => `
          <article class="card">
            <div class="card-body">
              <div class="card-category-row">
                <span>${escapeHtml(s.material)} ${s.brand ? `• ${escapeHtml(s.brand)}` : ""}</span>
                <span class="badge ${s.is_low_stock ? "badge-danger" : "badge-success"}">${s.is_low_stock ? "Estoque Baixo" : "OK"}</span>
              </div>
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="swatch" style="background:${escapeHtml(s.color_hex)}; width:16px; height:16px; border:1px solid rgba(255,255,255,0.4); box-shadow:0 0 0 1px rgba(0,0,0,0.5);"></span>
                <h3 class="card-title">${escapeHtml(s.color_name)}</h3>
              </div>
              <div class="progress-track">
                <div class="progress-fill ${s.is_low_stock ? "low" : ""}" style="width:${s.percent_remaining}%;"></div>
              </div>
              <div class="specs-strip tnum">
                <span class="spec-pill">Restante: <strong>${formatGrams(s.remaining_grams)}</strong> / ${formatGrams(s.initial_grams)}</span>
                <span class="spec-pill">Valor: <strong>${formatBrl(s.estimated_value_brl)}</strong></span>
                ${s.location ? `<span class="spec-pill">${escapeHtml(s.location)}</span>` : ""}
              </div>
            </div>
            <div class="card-footer">
              <div class="card-actions">
                <button class="btn btn-secondary btn-xs sp-minus-btn" data-id="${s.id}" data-rem="${s.remaining_grams}" type="button">-50g</button>
                <button class="btn btn-secondary btn-xs sp-edit-btn" data-id="${s.id}" type="button">Editar</button>
              </div>
              <button class="btn btn-danger btn-xs sp-del-btn" data-id="${s.id}" type="button">Excluir</button>
            </div>
          </article>
        `)
        .join("");

      grid.querySelectorAll(".sp-minus-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const next = Math.max(0, Number(btn.dataset.rem) - 50);
          await apiJson(`/api/spools/${btn.dataset.id}`, { method: "PATCH", body: JSON.stringify({ remaining_grams: next }) });
          await Promise.all([renderInventoryTab(), refreshSummary()]);
        });
      });

      grid.querySelectorAll(".sp-edit-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const s = hubState.spools.find((x) => x.id === Number(btn.dataset.id));
          if (!s) return;
          document.getElementById("spool-modal-title").textContent = "Editar Carretel";
          document.getElementById("sp-id").value = s.id;
          document.getElementById("sp-brand").value = s.brand;
          document.getElementById("sp-material").value = s.material;
          document.getElementById("sp-color-name").value = s.color_name;
          document.getElementById("sp-hex").value = s.color_hex;
          document.getElementById("sp-initial").value = s.initial_grams;
          document.getElementById("sp-remaining").value = s.remaining_grams;
          document.getElementById("sp-alert").value = s.min_alert_grams;
          document.getElementById("sp-cost").value = s.cost_per_kg_brl;
          document.getElementById("sp-location").value = s.location;
          document.getElementById("spool-backdrop").hidden = false;
        });
      });

      grid.querySelectorAll(".sp-del-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await apiJson(`/api/spools/${btn.dataset.id}`, { method: "DELETE" });
          showToast("Carretel removido.");
          await Promise.all([renderInventoryTab(), refreshSummary()]);
        });
      });
    }

    const tbody = document.getElementById("ready-stock-tbody");
    tbody.innerHTML = catData.items
      .map(
        (c) => `
        <tr>
          <td><strong>${escapeHtml(c.code)}</strong> ${escapeHtml(c.name)}</td>
          <td>${escapeHtml(c.category)}</td>
          <td class="tnum">${formatBrl(c.sale_price_brl)}</td>
          <td class="tnum"><strong>${c.stock_qty}</strong> un.</td>
          <td>
            <div class="card-actions">
              <button class="btn btn-secondary btn-xs st-adj-btn" data-id="${c.id}" data-qty="${Math.max(0, c.stock_qty - 1)}" type="button">-1</button>
              <button class="btn btn-secondary btn-xs st-adj-btn" data-id="${c.id}" data-qty="${c.stock_qty + 1}" type="button">+1</button>
              <button class="btn btn-accent btn-xs st-rep-btn" data-id="${c.id}" type="button">+ Fila Estoque</button>
            </div>
          </td>
        </tr>
      `
      )
      .join("");

    tbody.querySelectorAll(".st-adj-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/catalog/${btn.dataset.id}`, {
          method: "PATCH",
          body: JSON.stringify({ stock_qty: Number(btn.dataset.qty) }),
        });
        await Promise.all([renderInventoryTab(), refreshSummary()]);
      });
    });

    tbody.querySelectorAll(".st-rep-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const c = hubState.catalog.find((x) => x.id === Number(btn.dataset.id));
        if (c) openJobModal({ catalog_item_id: c.id, model_id: c.model_id, title: `Reposição: ${c.name}`, target_type: "Estoque", estimated_grams: c.filament_grams || 50 });
      });
    });
  }

  // ---- TAB 5: CATÁLOGO & VENDAS ---- //

  async function renderCatalogTab() {
    const q = document.getElementById("catalog-filter-q").value.trim();
    const category = document.getElementById("catalog-filter-category").value;
    const subcategory = document.getElementById("catalog-filter-subcategory").value;
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (category) params.set("category", category);
    if (subcategory) params.set("subcategory", subcategory);
    const [catData, salesData] = await Promise.all([
      apiJson(`/api/catalog?${params.toString()}`),
      apiJson("/api/sales"),
      loadSubcategories(),
    ]);
    if (!category && !subcategory && !q) {
      hubState.catalog = catData.items;
    } else if (!hubState.catalog.length) {
      const fullCat = await apiJson("/api/catalog");
      hubState.catalog = fullCat.items;
    }
    hubState.sales = salesData.items;
    syncSelectOptions();
    syncCatalogFilterSelects();

    document.getElementById("catalog-metrics").innerHTML = `
      <div class="metric-tile"><div class="metric-value tnum">${catData.total}</div><div class="metric-caption">Produtos no catálogo</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${formatBrl(catData.total_stock_value_brl)}</div><div class="metric-caption">Valor pronta entrega</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${salesData.total}</div><div class="metric-caption">Pedidos registrados</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${formatBrl(salesData.total_revenue_brl)}</div><div class="metric-caption">Faturamento total</div></div>
    `;

    const grid = document.getElementById("catalog-grid");
    grid.innerHTML = catData.items
      .map((c) => {
        const catFallback = (msg, hiddenByDefault) => `
          <div class="card-thumb-fallback"${hiddenByDefault ? ' style="display:none;"' : ""}>
            <span>${escapeHtml(msg)}</span>
            <div class="thumb-config-actions">
              <button class="btn btn-secondary btn-xs cat-config-link-btn" data-id="${c.id}" type="button">Configurar link</button>
            </div>
          </div>
        `;
        return `
        <article class="card">
          <div class="card-thumb">
            ${
              c.image_url
                ? `<img src="${escapeHtml(c.image_url)}" alt="${escapeHtml(c.name)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.hidden=true; this.nextElementSibling.style.display='flex';" />${catFallback("Link indisponível", true)}`
                : catFallback("Ita Arte 3D • sem imagem", false)
            }
            ${c.code ? `<span class="thumb-source">${escapeHtml(c.code)}</span>` : ""}
            <span class="thumb-status ${c.stock_qty > 0 ? "status-impresso" : "status-na-fila"}">${c.stock_qty > 0 ? `Pronta entrega: ${c.stock_qty}` : "Sob encomenda"}</span>
          </div>
          <div class="card-body">
            <div class="card-category-row">
              <span>${escapeHtml(c.category)}${c.subcategory ? ` › <strong>${escapeHtml(c.subcategory)}</strong>` : ""}</span>
              <span class="price-text">${formatBrl(c.sale_price_brl)}</span>
            </div>
            ${renderCatExtraBadges(c)}
            <h3 class="card-title">${escapeHtml(c.name)}</h3>
            <div class="specs-strip tnum">
              <span class="spec-pill">Filamento: <strong>${formatGrams(c.filament_grams)}</strong></span>
              <span class="spec-pill">Custo est.: <strong>${formatBrl(c.unit_cost_brl)}</strong></span>
              <span class="spec-pill">Lucro est.: <strong>${formatBrl(c.estimated_profit_brl)}</strong></span>
            </div>
            ${c.dimensions_cm ? `<p class="rec-reason">${escapeHtml(c.dimensions_cm)}</p>` : ""}
          </div>
          <div class="card-footer">
            <div class="card-actions">
              <button class="btn btn-accent btn-xs cat-sell-btn" data-id="${c.id}" type="button">Vender</button>
              <button class="btn btn-secondary btn-xs cat-queue-btn" data-id="${c.id}" type="button">+ Fila</button>
              <button class="btn btn-ghost btn-xs cat-edit-btn" data-id="${c.id}" type="button">Editar</button>
            </div>
            <button class="btn btn-danger btn-xs cat-del-btn" data-id="${c.id}" type="button">Excluir</button>
          </div>
        </article>
      `;
      })
      .join("");

    grid.querySelectorAll(".cat-sell-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const c = hubState.catalog.find((x) => x.id === Number(btn.dataset.id));
        if (!c) return;
        document.getElementById("sale-catalog").value = c.id;
        document.getElementById("sale-price").value = c.sale_price_brl;
        document.getElementById("sale-qty").value = 1;
        document.getElementById("sale-backdrop").hidden = false;
      });
    });

    grid.querySelectorAll(".cat-queue-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const c = hubState.catalog.find((x) => x.id === Number(btn.dataset.id));
        if (c) openJobModal({ catalog_item_id: c.id, model_id: c.model_id, title: c.name, target_type: "Estoque", estimated_grams: c.filament_grams || 50 });
      });
    });

    const openCatalogEdit = (id, focusImage = false) => {
      const c = hubState.catalog.find((x) => x.id === Number(id));
      if (!c) return;
      document.getElementById("catalog-modal-title").textContent = "Editar Produto";
      document.getElementById("cat-id").value = c.id;
      document.getElementById("cat-model-id").value = c.model_id || "";
      document.getElementById("cat-code").value = c.code;
      document.getElementById("cat-name").value = c.name;
      document.getElementById("cat-category").value = c.category;
      syncCatalogSubcatSelect(c.category, c.subcategory || "");
      setCatalogClassifications(
        Array.isArray(c.classifications) && c.classifications.length
          ? c.classifications
          : [{ category: c.category, subcategory: c.subcategory || "" }]
      );
      catFormClassificationsDirty = false;
      document.getElementById("cat-dims").value = c.dimensions_cm;
      document.getElementById("cat-grams").value = c.filament_grams;
      document.getElementById("cat-mode").value = c.pricing_mode;
      document.getElementById("cat-rate").value = c.rate_per_gram_brl;
      document.getElementById("cat-extras").value = c.extras_cost_brl;
      document.getElementById("cat-stock").value = c.stock_qty;
      document.getElementById("cat-manual-price").value = c.sale_price_brl;
      document.getElementById("cat-image").value = c.image_url || "";
      const prev = document.getElementById("cat-image-preview");
      if (c.image_url) {
        prev.src = c.image_url;
        prev.hidden = false;
      } else {
        prev.hidden = true;
      }
      document.getElementById("catalog-backdrop").hidden = false;
      if (focusImage) {
        setTimeout(() => {
          const el = document.getElementById("cat-image");
          el.focus();
          el.select();
        }, 30);
      }
    };

    grid.querySelectorAll(".cat-edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => openCatalogEdit(btn.dataset.id, false));
    });
    grid.querySelectorAll(".cat-config-link-btn").forEach((btn) => {
      btn.addEventListener("click", () => openCatalogEdit(btn.dataset.id, true));
    });

    grid.querySelectorAll(".cat-del-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/catalog/${btn.dataset.id}`, { method: "DELETE" });
        showToast("Produto removido.");
        await Promise.all([renderCatalogTab(), refreshSummary()]);
      });
    });

    document.getElementById("sales-tbody").innerHTML = salesData.items
      .map(
        (s) => `
        <tr>
          <td class="tnum">${formatDateTimePtBr(s.created_at)}</td>
          <td>${escapeHtml(s.item_name)}</td>
          <td>${escapeHtml(s.customer_name || "Cliente")} • <span style="color:var(--muted);">${escapeHtml(s.channel)}</span></td>
          <td class="tnum">${s.quantity}x</td>
          <td class="tnum"><strong>${formatBrl(s.total_price_brl)}</strong></td>
          <td><span class="badge ${statusBadgeClass(s.payment_status)}">${escapeHtml(s.payment_status)}</span></td>
          <td><span class="badge ${statusBadgeClass(s.fulfillment_status)}">${escapeHtml(s.fulfillment_status)}</span></td>
          <td><button class="btn btn-ghost btn-xs sale-del-btn" data-id="${s.id}" type="button">Excluir</button></td>
        </tr>
      `
      )
      .join("");

    document.querySelectorAll(".sale-del-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/sales/${btn.dataset.id}`, { method: "DELETE" });
        await Promise.all([renderCatalogTab(), refreshSummary()]);
      });
    });
  }

  // ---- TAB 6: FOTOS & INSTAGRAM ---- //

  async function renderMediaTab() {
    await Promise.all([loadPrintersAndSpools(), apiJson("/api/catalog").then((d) => { hubState.catalog = d.items; }), apiJson("/api/queue").then((d) => { hubState.jobs = d.items; })]);
    syncSelectOptions();
    const status = document.getElementById("media-filter-status").value;
    const params = new URLSearchParams();
    if (status) params.set("status", status);

    const data = await apiJson(`/api/media?${params.toString()}`);
    hubState.media = data.items;

    document.getElementById("media-metrics").innerHTML = `
      <div class="metric-tile"><div class="metric-value tnum">${data.total}</div><div class="metric-caption">Fotos guardadas</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${data.ready_to_post_count}</div><div class="metric-caption">Prontas / Agendadas</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${data.posted_count}</div><div class="metric-caption">Já postadas</div></div>
      <div class="metric-tile"><div class="metric-value tnum">@itaarte3d</div><div class="metric-caption">Estúdio de conteúdo</div></div>
    `;

    const grid = document.getElementById("media-grid");
    if (!data.items.length) {
      grid.innerHTML = `<div class="state-box" style="grid-column:1/-1;"><h2>Nenhuma foto salva ainda</h2><p>Arraste fotos das suas peças impressas acima para montar seu banco de postagens do Instagram.</p></div>`;
      return;
    }

    grid.innerHTML = data.items
      .map((m) => {
        const mediaFallback = (msg, hiddenByDefault) => `
          <div class="card-thumb-fallback"${hiddenByDefault ? ' style="display:none;"' : ""}>
            <span>${escapeHtml(msg)}</span>
            <div class="thumb-config-actions">
              <button class="btn btn-secondary btn-xs med-config-link-btn" data-id="${m.id}" type="button">Configurar link</button>
            </div>
          </div>
        `;
        return `
        <article class="card">
          <div class="card-thumb" style="height:190px;">
            ${
              m.file_url
                ? `<img src="${escapeHtml(m.file_url)}" alt="${escapeHtml(m.title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.hidden=true; this.nextElementSibling.style.display='flex';" />${mediaFallback("Link indisponível", true)}`
                : mediaFallback("Sem imagem configurada", false)
            }
            <span class="thumb-source">${escapeHtml(m.post_format)}</span>
            <span class="thumb-status ${statusBadgeClass(m.status)}">${escapeHtml(m.status)}</span>
          </div>
          <div class="card-body">
            <div class="card-category-row">
              <span>${m.scheduled_date ? `Previsto: ${escapeHtml(m.scheduled_date)}` : "Sem data"}</span>
              <span class="tnum">${formatDateTimePtBr(m.created_at)}</span>
            </div>
            <h3 class="card-title">${escapeHtml(m.title || "Foto de Impressão")}</h3>
            <p class="rec-reason" style="-webkit-line-clamp:3; display:-webkit-box; -webkit-box-orient:vertical; overflow:hidden;">
              ${escapeHtml(m.caption || "Sem legenda ainda — clique em Editar / Legenda.")}
            </p>
            ${m.hashtags ? `<p class="rec-reason" style="color:var(--cyan);">${escapeHtml(m.hashtags)}</p>` : ""}
          </div>
          <div class="card-footer">
            <div class="card-actions">
              <button class="btn btn-secondary btn-xs med-edit-btn" data-id="${m.id}" type="button">Legenda / Status</button>
              <button class="btn btn-ghost btn-xs med-copy-btn" data-id="${m.id}" type="button">Copiar</button>
              <a class="btn btn-ghost btn-xs" href="${escapeHtml(m.file_url)}" download>Baixar</a>
            </div>
            <button class="btn btn-danger btn-xs med-del-btn" data-id="${m.id}" type="button">Excluir</button>
          </div>
        </article>
      `;
      })
      .join("");

    const openMediaEdit = (id, focusUrl = false) => {
      const m = hubState.media.find((x) => x.id === Number(id));
      if (!m) return;
      document.getElementById("med-id").value = m.id;
      document.getElementById("med-title").value = m.title;
      document.getElementById("med-file-url").value = m.file_url || "";
      const prev = document.getElementById("med-image-preview");
      if (m.file_url) {
        prev.src = m.file_url;
        prev.hidden = false;
      } else {
        prev.hidden = true;
      }
      document.getElementById("med-format").value = m.post_format;
      document.getElementById("med-status").value = m.status;
      document.getElementById("med-date").value = m.scheduled_date;
      document.getElementById("med-caption").value = m.caption;
      document.getElementById("med-hashtags").value = m.hashtags;
      document.getElementById("media-backdrop").hidden = false;
      if (focusUrl) {
        setTimeout(() => {
          const el = document.getElementById("med-file-url");
          el.focus();
          el.select();
        }, 30);
      }
    };

    grid.querySelectorAll(".med-edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => openMediaEdit(btn.dataset.id, false));
    });
    grid.querySelectorAll(".med-config-link-btn").forEach((btn) => {
      btn.addEventListener("click", () => openMediaEdit(btn.dataset.id, true));
    });

    grid.querySelectorAll(".med-copy-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const m = hubState.media.find((x) => x.id === Number(btn.dataset.id));
        if (!m) return;
        const text = [m.caption, m.hashtags].filter(Boolean).join("\n\n");
        if (!text) {
          showToast("Gere ou escreva uma legenda antes de copiar.");
          return;
        }
        await navigator.clipboard.writeText(text);
        showToast("Legenda + hashtags copiadas!");
      });
    });

    grid.querySelectorAll(".med-del-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/media/${btn.dataset.id}`, { method: "DELETE" });
        showToast("Foto removida.");
        await Promise.all([renderMediaTab(), refreshSummary()]);
      });
    });
  }

  // ---- Shared Public Openers & Event Listeners ---- //

  function updateJobVerifyBanner() {
    const banner = document.getElementById("job-verify-banner");
    if (!banner) return;
    const printerId = document.getElementById("job-printer").value;
    const spoolId = document.getElementById("job-spool").value;
    const slicingId = document.getElementById("job-slicing-profile").value;
    const estGrams = Number(document.getElementById("job-grams").value || 0);

    const printer = hubState.printers.find((p) => String(p.id) === printerId);
    const spool = hubState.spools.find((s) => String(s.id) === spoolId);
    const slicing = hubState.slicingProfiles.find((s) => String(s.id) === slicingId);

    const checks = [];
    let allOk = true;

    if (printer) {
      checks.push(`✔ Impressora: <strong>${escapeHtml(printer.name)}</strong> (${escapeHtml(printer.status)})`);
    } else {
      allOk = false;
      checks.push("⚠ Impressora: não selecionada");
    }

    if (!spool) {
      allOk = false;
      checks.push("⚠ Filamento: selecione um carretel para verificar saldo");
    } else if (spool.remaining_grams < estGrams) {
      allOk = false;
      checks.push(`⚠ Filamento insuficiente: ${escapeHtml(spool.color_name)} tem <strong>${formatGrams(spool.remaining_grams)}</strong> (pede ${formatGrams(estGrams)})`);
    } else {
      checks.push(`✔ Filamento: <strong>${escapeHtml(spool.material)} ${escapeHtml(spool.color_name)}</strong> (${formatGrams(spool.remaining_grams)} livres)`);
    }

    if (slicing) {
      checks.push(`✔ Fatiamento: <strong>${escapeHtml(slicing.name)}</strong>`);
    } else {
      allOk = false;
      checks.push("⚠ Fatiamento: selecione a altura de camada / perfil");
    }

    banner.className = `verify-banner ${allOk ? "ok" : "warn"}`;
    banner.innerHTML = `<strong>Verificação Pré-Impressão:</strong><br>${checks.join(" &nbsp;|&nbsp; ")}`;
  }

  function renderRubricsManagerList() {
    const listEl = document.getElementById("rubrics-list");
    if (!listEl) return;
    if (!hubState.rubrics.length) {
      listEl.innerHTML = `<div class="empty-state"><h3>Nenhuma rubrica cadastrada</h3><p>Crie acima (ex: Larissa Advogada).</p></div>`;
      return;
    }
    listEl.innerHTML = hubState.rubrics
      .map((r) => {
        if (editingRubricId === r.id) {
          return `
            <div class="subcat-item" style="flex-direction:column; align-items:stretch;">
              <div style="display:grid; grid-template-columns:1.2fr auto 1.4fr; gap:8px;">
                <input class="input rubric-edit-name" data-id="${r.id}" type="text" value="${escapeHtml(r.name)}" />
                <input class="input rubric-edit-color" data-id="${r.id}" type="color" value="${escapeHtml(r.color_hex || "#22d3ee")}" style="width:46px; padding:2px; height:36px;" />
                <input class="input rubric-edit-notes" data-id="${r.id}" type="text" value="${escapeHtml(r.notes || "")}" placeholder="Observações" />
              </div>
              <div style="display:flex; justify-content:flex-end; gap:6px;">
                <button class="btn btn-secondary btn-xs rubric-edit-cancel" type="button">Cancelar</button>
                <button class="btn btn-primary btn-xs rubric-edit-save" data-id="${r.id}" type="button">Salvar</button>
              </div>
            </div>
          `;
        }
        return `
          <div class="subcat-item">
            <div class="subcat-meta">
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="rubric-dot" style="background:${escapeHtml(r.color_hex || "#22d3ee")}; width:10px; height:10px;"></span>
                <span class="subcat-name-label">${escapeHtml(r.name)}</span>
              </div>
              ${r.notes ? `<span class="brand-sub">${escapeHtml(r.notes)}</span>` : ""}
            </div>
            <div class="card-actions">
              <button class="btn btn-secondary btn-xs rubric-filter-btn" data-id="${r.id}" type="button">${r.jobs_count} trabalhos</button>
              <button class="btn btn-ghost btn-xs rubric-edit-btn" data-id="${r.id}" type="button">Editar</button>
              <button class="btn btn-danger btn-xs rubric-del-btn" data-id="${r.id}" type="button">Excluir</button>
            </div>
          </div>
        `;
      })
      .join("");

    listEl.querySelectorAll(".rubric-edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        editingRubricId = Number(btn.dataset.id);
        renderRubricsManagerList();
      });
    });
    listEl.querySelectorAll(".rubric-edit-cancel").forEach((btn) => {
      btn.addEventListener("click", () => {
        editingRubricId = null;
        renderRubricsManagerList();
      });
    });
    listEl.querySelectorAll(".rubric-edit-save").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.dataset.id);
        const name = listEl.querySelector(`.rubric-edit-name[data-id="${id}"]`)?.value.trim() || "";
        const color_hex = listEl.querySelector(`.rubric-edit-color[data-id="${id}"]`)?.value || "#22d3ee";
        const notes = listEl.querySelector(`.rubric-edit-notes[data-id="${id}"]`)?.value.trim() || "";
        await apiJson(`/api/rubrics/${id}`, { method: "PATCH", body: JSON.stringify({ name, color_hex, notes }) });
        editingRubricId = null;
        showToast("Rubrica atualizada!");
        await loadPrintersAndSpools();
        renderRubricsManagerList();
        await renderQueueTab();
      });
    });
    listEl.querySelectorAll(".rubric-filter-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        document.getElementById("queue-filter-rubric").value = btn.dataset.id;
        document.getElementById("rubrics-backdrop").hidden = true;
        await renderQueueTab();
      });
    });
    listEl.querySelectorAll(".rubric-del-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/rubrics/${btn.dataset.id}`, { method: "DELETE" });
        editingRubricId = null;
        showToast("Rubrica removida.");
        await loadPrintersAndSpools();
        renderRubricsManagerList();
        await renderQueueTab();
      });
    });
  }

  function renderSlicingManagerList() {
    const listEl = document.getElementById("slicing-list");
    if (!listEl) return;
    if (!hubState.slicingProfiles.length) {
      listEl.innerHTML = `<div class="empty-state"><h3>Nenhum perfil cadastrado</h3></div>`;
      return;
    }
    listEl.innerHTML = hubState.slicingProfiles
      .map((s) => {
        if (editingSlicingId === s.id) {
          return `
            <div class="subcat-item" style="flex-direction:column; align-items:stretch;">
              <div style="display:grid; grid-template-columns:1.2fr 0.6fr 1.6fr; gap:8px;">
                <input class="input slicing-edit-name" data-id="${s.id}" type="text" value="${escapeHtml(s.name)}" />
                <input class="input tnum slicing-edit-layer" data-id="${s.id}" type="number" step="0.01" value="${s.layer_height_mm}" />
                <input class="input slicing-edit-notes" data-id="${s.id}" type="text" value="${escapeHtml(s.notes || "")}" placeholder="Alterações nas variáveis de fatiamento..." />
              </div>
              <div style="display:flex; justify-content:flex-end; gap:6px;">
                <button class="btn btn-secondary btn-xs slicing-edit-cancel" type="button">Cancelar</button>
                <button class="btn btn-primary btn-xs slicing-edit-save" data-id="${s.id}" type="button">Salvar</button>
              </div>
            </div>
          `;
        }
        return `
          <div class="subcat-item">
            <div class="subcat-meta">
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="slicing-pill">${Number(s.layer_height_mm).toFixed(2)} mm</span>
                <span class="subcat-name-label">${escapeHtml(s.name)}</span>
                ${s.is_default ? `<span class="badge badge-success">Padrão</span>` : ""}
              </div>
              ${s.notes ? `<span class="brand-sub">${escapeHtml(s.notes)}</span>` : `<span class="brand-sub">Sem observações de variáveis</span>`}
            </div>
            <div class="card-actions">
              <button class="btn btn-ghost btn-xs slicing-edit-btn" data-id="${s.id}" type="button">Editar Obs./Altura</button>
              <button class="btn btn-danger btn-xs slicing-del-btn" data-id="${s.id}" type="button">Excluir</button>
            </div>
          </div>
        `;
      })
      .join("");

    listEl.querySelectorAll(".slicing-edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        editingSlicingId = Number(btn.dataset.id);
        renderSlicingManagerList();
      });
    });
    listEl.querySelectorAll(".slicing-edit-cancel").forEach((btn) => {
      btn.addEventListener("click", () => {
        editingSlicingId = null;
        renderSlicingManagerList();
      });
    });
    listEl.querySelectorAll(".slicing-edit-save").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.dataset.id);
        const name = listEl.querySelector(`.slicing-edit-name[data-id="${id}"]`)?.value.trim() || "";
        const layer_height_mm = Number(listEl.querySelector(`.slicing-edit-layer[data-id="${id}"]`)?.value || 0.2);
        const notes = listEl.querySelector(`.slicing-edit-notes[data-id="${id}"]`)?.value.trim() || "";
        await apiJson(`/api/slicing-profiles/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ name, layer_height_mm, notes }),
        });
        editingSlicingId = null;
        showToast("Perfil de fatiamento atualizado!");
        await loadPrintersAndSpools();
        renderSlicingManagerList();
        await renderQueueTab();
      });
    });
    listEl.querySelectorAll(".slicing-del-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/slicing-profiles/${btn.dataset.id}`, { method: "DELETE" });
        editingSlicingId = null;
        showToast("Perfil removido.");
        await loadPrintersAndSpools();
        renderSlicingManagerList();
        await renderQueueTab();
      });
    });
  }

  async function openJobModal(prefill = {}) {
    await loadPrintersAndSpools();
    const isEdit = Boolean(prefill.id);
    document.getElementById("job-modal-title").textContent = isEdit ? `Editar Trabalho #${prefill.id}` : "Adicionar na Fila de Impressão";
    document.getElementById("job-submit-btn").textContent = isEdit ? "Salvar Alterações" : "Adicionar na Fila";
    document.getElementById("job-id").value = prefill.id || "";
    document.getElementById("job-model-id").value = prefill.model_id || "";
    document.getElementById("job-catalog-id").value = prefill.catalog_item_id || "";
    document.getElementById("job-title").value = prefill.title || "";
    document.getElementById("job-target").value = prefill.target_type || "Encomenda";
    document.getElementById("job-qty").value = prefill.quantity || 1;
    document.getElementById("job-priority").value = prefill.priority || "Normal";
    document.getElementById("job-grams").value = prefill.estimated_grams ?? 50;
    document.getElementById("job-time").value = prefill.estimated_time_min ?? 60;
    document.getElementById("job-customer").value = prefill.customer_name || "";
    document.getElementById("job-notes").value = prefill.notes || "";
    document.getElementById("job-rubric-new").value = "";

    const printerSel = document.getElementById("job-printer");
    if (prefill.printer_id !== undefined) {
      printerSel.value = prefill.printer_id ? String(prefill.printer_id) : "";
    } else if (hubState.printers.length) {
      printerSel.value = String(hubState.printers[0].id);
    }

    document.getElementById("job-spool").value = prefill.spool_id ? String(prefill.spool_id) : "";
    document.getElementById("job-rubric").value = prefill.rubric_id ? String(prefill.rubric_id) : "";

    const slicingSel = document.getElementById("job-slicing-profile");
    if (prefill.slicing_profile_id) {
      slicingSel.value = String(prefill.slicing_profile_id);
      lastProfileAutoNote = "";
    } else {
      const defProf = hubState.slicingProfiles.find((s) => s.is_default) || hubState.slicingProfiles.find((s) => Math.abs(s.layer_height_mm - 0.2) < 0.01) || hubState.slicingProfiles[0];
      slicingSel.value = defProf ? String(defProf.id) : "";
      lastProfileAutoNote = defProf?.notes || "";
    }
    document.getElementById("job-slicing-notes").value =
      prefill.slicing_notes !== undefined ? prefill.slicing_notes : (isEdit ? "" : lastProfileAutoNote);

    updateJobVerifyBanner();
    document.getElementById("job-backdrop").hidden = false;
  }

  function bindEvents() {
    document.getElementById("quick-new-job-btn").addEventListener("click", () => openJobModal());
    document.getElementById("queue-add-btn").addEventListener("click", () => openJobModal());
    document.getElementById("job-cancel-btn").addEventListener("click", () => { document.getElementById("job-backdrop").hidden = true; });
    ["job-printer", "job-spool", "job-grams"].forEach((id) => {
      document.getElementById(id).addEventListener("change", updateJobVerifyBanner);
      document.getElementById(id).addEventListener("input", updateJobVerifyBanner);
    });
    document.getElementById("job-slicing-profile").addEventListener("change", (e) => {
      const prof = hubState.slicingProfiles.find((s) => String(s.id) === e.target.value);
      const notesEl = document.getElementById("job-slicing-notes");
      if (!notesEl.value.trim() || notesEl.value.trim() === lastProfileAutoNote) {
        notesEl.value = prof?.notes || "";
      }
      lastProfileAutoNote = prof?.notes || "";
      updateJobVerifyBanner();
    });
    document.getElementById("job-rubric-quick-add").addEventListener("click", async () => {
      const inp = document.getElementById("job-rubric-new");
      const name = inp.value.trim();
      if (!name) return;
      const created = await apiJson("/api/rubrics", { method: "POST", body: JSON.stringify({ name }) });
      inp.value = "";
      await loadPrintersAndSpools();
      document.getElementById("job-rubric").value = String(created.id);
      showToast(`Rubrica "${created.name}" selecionada!`);
    });
    document.getElementById("job-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const jobId = document.getElementById("job-id").value;
      const newRubricName = document.getElementById("job-rubric-new").value.trim();
      const rubricIdVal = document.getElementById("job-rubric").value;
      const payload = {
        model_id: document.getElementById("job-model-id").value ? Number(document.getElementById("job-model-id").value) : null,
        catalog_item_id: document.getElementById("job-catalog-id").value ? Number(document.getElementById("job-catalog-id").value) : null,
        printer_id: document.getElementById("job-printer").value ? Number(document.getElementById("job-printer").value) : null,
        spool_id: document.getElementById("job-spool").value ? Number(document.getElementById("job-spool").value) : null,
        rubric_id: newRubricName ? null : (rubricIdVal ? Number(rubricIdVal) : null),
        rubric_name: newRubricName || "",
        slicing_profile_id: document.getElementById("job-slicing-profile").value ? Number(document.getElementById("job-slicing-profile").value) : null,
        slicing_notes: document.getElementById("job-slicing-notes").value.trim(),
        title: document.getElementById("job-title").value.trim(),
        target_type: document.getElementById("job-target").value,
        quantity: Number(document.getElementById("job-qty").value || 1),
        priority: document.getElementById("job-priority").value,
        estimated_grams: Number(document.getElementById("job-grams").value || 0),
        estimated_time_min: Number(document.getElementById("job-time").value || 0),
        customer_name: document.getElementById("job-customer").value.trim(),
        notes: document.getElementById("job-notes").value.trim(),
      };
      await apiJson(jobId ? `/api/queue/${jobId}` : "/api/queue", {
        method: jobId ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      document.getElementById("job-backdrop").hidden = true;
      showToast(jobId ? "Trabalho atualizado na fila!" : "Peça adicionada na fila de impressão!");
      await Promise.all([refreshSummary(), renderQueueTab()]);
    });

    [
      "queue-filter-status",
      "queue-filter-printer",
      "queue-filter-rubric",
      "queue-filter-slicing",
      "queue-filter-spool",
      "queue-filter-target",
      "queue-filter-priority",
      "queue-group-mode",
    ].forEach((id) => {
      document.getElementById(id)?.addEventListener("change", renderQueueTab);
    });
    document.getElementById("queue-filter-q")?.addEventListener("input", renderQueueTab);
    document.getElementById("queue-clear-filters-btn")?.addEventListener("click", () => {
      [
        "queue-filter-q",
        "queue-filter-printer",
        "queue-filter-rubric",
        "queue-filter-slicing",
        "queue-filter-spool",
        "queue-filter-target",
        "queue-filter-status",
        "queue-filter-priority",
      ].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.value = "";
      });
      renderQueueTab();
    });

    document.getElementById("queue-rubrics-btn").addEventListener("click", async () => {
      editingRubricId = null;
      await loadPrintersAndSpools();
      renderRubricsManagerList();
      document.getElementById("rubrics-backdrop").hidden = false;
    });
    document.getElementById("rubrics-close-btn").addEventListener("click", () => { document.getElementById("rubrics-backdrop").hidden = true; });
    document.getElementById("rubric-create-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      await apiJson("/api/rubrics", {
        method: "POST",
        body: JSON.stringify({
          name: document.getElementById("rubric-new-name").value.trim(),
          color_hex: document.getElementById("rubric-new-color").value,
          notes: document.getElementById("rubric-new-notes").value.trim(),
        }),
      });
      document.getElementById("rubric-new-name").value = "";
      document.getElementById("rubric-new-notes").value = "";
      showToast("Rubrica criada!");
      await loadPrintersAndSpools();
      renderRubricsManagerList();
      await renderQueueTab();
    });

    document.getElementById("queue-slicing-btn").addEventListener("click", async () => {
      editingSlicingId = null;
      await loadPrintersAndSpools();
      renderSlicingManagerList();
      document.getElementById("slicing-backdrop").hidden = false;
    });
    document.getElementById("slicing-close-btn").addEventListener("click", () => { document.getElementById("slicing-backdrop").hidden = true; });
    document.getElementById("slicing-create-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      await apiJson("/api/slicing-profiles", {
        method: "POST",
        body: JSON.stringify({
          name: document.getElementById("slicing-new-name").value.trim(),
          layer_height_mm: Number(document.getElementById("slicing-new-layer").value || 0.2),
          notes: document.getElementById("slicing-new-notes").value.trim(),
        }),
      });
      document.getElementById("slicing-new-name").value = "";
      document.getElementById("slicing-new-notes").value = "";
      showToast("Perfil de fatiamento salvo!");
      await loadPrintersAndSpools();
      renderSlicingManagerList();
      await renderQueueTab();
    });

    document.getElementById("finish-cancel-btn").addEventListener("click", () => { document.getElementById("finish-job-backdrop").hidden = true; });
    document.getElementById("finish-job-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = document.getElementById("finish-job-id").value;
      const status = document.getElementById("finish-job-status").value;
      await apiJson(`/api/queue/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          status,
          actual_grams_used: Number(document.getElementById("finish-job-grams").value || 0),
          failure_reason: document.getElementById("finish-job-reason").value.trim(),
        }),
      });
      document.getElementById("finish-job-backdrop").hidden = true;
      showToast(status === "Concluída" ? "Impressão concluída e estoque atualizado!" : "Falha registrada.");
      await Promise.all([refreshSummary(), renderQueueTab()]);
    });

    document.getElementById("printer-add-btn").addEventListener("click", () => {
      document.getElementById("printer-form").reset();
      document.getElementById("pr-id").value = "";
      document.getElementById("printer-modal-title").textContent = "Cadastrar Impressora";
      document.getElementById("printer-backdrop").hidden = false;
    });
    document.getElementById("pr-cancel-btn").addEventListener("click", () => { document.getElementById("printer-backdrop").hidden = true; });
    document.getElementById("printer-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = document.getElementById("pr-id").value;
      const slots = Number(document.getElementById("pr-ams-slots").value || 0);
      const body = {
        name: document.getElementById("pr-name").value.trim(),
        brand_model: document.getElementById("pr-model").value.trim(),
        build_volume_mm: document.getElementById("pr-volume").value.trim(),
        max_dim_mm: Number(document.getElementById("pr-max-dim").value || 256),
        nozzle_mm: Number(document.getElementById("pr-nozzle").value || 0.4),
        has_ams: slots > 0,
        ams_slots: slots,
        hourly_cost_brl: Number(document.getElementById("pr-hourly").value || 0),
        status: document.getElementById("pr-status").value,
        notes: document.getElementById("pr-notes").value.trim(),
      };
      await apiJson(id ? `/api/printers/${id}` : "/api/printers", { method: id ? "PATCH" : "POST", body: JSON.stringify(body) });
      document.getElementById("printer-backdrop").hidden = true;
      showToast("Impressora salva!");
      await Promise.all([renderPrintersTab(), refreshSummary()]);
    });

    document.getElementById("spool-filter-material").addEventListener("change", renderInventoryTab);
    document.getElementById("spool-filter-low").addEventListener("change", renderInventoryTab);
    document.getElementById("spool-add-btn").addEventListener("click", () => {
      document.getElementById("spool-form").reset();
      document.getElementById("sp-id").value = "";
      document.getElementById("spool-modal-title").textContent = "Adicionar Carretel";
      document.getElementById("spool-backdrop").hidden = false;
    });
    document.getElementById("sp-cancel-btn").addEventListener("click", () => { document.getElementById("spool-backdrop").hidden = true; });
    document.getElementById("spool-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = document.getElementById("sp-id").value;
      const body = {
        brand: document.getElementById("sp-brand").value.trim(),
        material: document.getElementById("sp-material").value,
        color_name: document.getElementById("sp-color-name").value.trim(),
        color_hex: document.getElementById("sp-hex").value,
        initial_grams: Number(document.getElementById("sp-initial").value || 1000),
        remaining_grams: Number(document.getElementById("sp-remaining").value || 1000),
        min_alert_grams: Number(document.getElementById("sp-alert").value || 150),
        cost_per_kg_brl: Number(document.getElementById("sp-cost").value || 120),
        location: document.getElementById("sp-location").value.trim(),
      };
      await apiJson(id ? `/api/spools/${id}` : "/api/spools", { method: id ? "PATCH" : "POST", body: JSON.stringify(body) });
      document.getElementById("spool-backdrop").hidden = true;
      showToast("Carretel salvo!");
      await Promise.all([renderInventoryTab(), refreshSummary()]);
    });

    document.getElementById("catalog-filter-q").addEventListener("input", renderCatalogTab);
    document.getElementById("catalog-filter-category").addEventListener("change", () => {
      syncCatalogFilterSelects();
      renderCatalogTab();
    });
    document.getElementById("catalog-filter-subcategory").addEventListener("change", renderCatalogTab);
    document.getElementById("catalog-manage-subs-btn").addEventListener("click", () => {
      openSubcategoriesModal("sales_catalog", document.getElementById("catalog-filter-category").value);
    });
    document.getElementById("cat-category").addEventListener("input", (e) => {
      syncCatalogSubcatSelect(e.target.value, document.getElementById("cat-subcategory").value);
    });
    document.getElementById("catalog-import-ita-btn").addEventListener("click", async () => {
      const res = await apiJson("/api/catalog/import-ita-arte", { method: "POST" });
      showToast(`${res.imported} produto(s) importado(s) do catalogo-ita-arte-3d.`);
      await Promise.all([renderCatalogTab(), refreshSummary()]);
    });
    document.getElementById("catalog-add-btn").addEventListener("click", () => {
      document.getElementById("catalog-form").reset();
      document.getElementById("cat-id").value = "";
      document.getElementById("cat-model-id").value = "";
      document.getElementById("cat-image-preview").hidden = true;
      syncCatalogSubcatSelect(document.getElementById("cat-category").value, "");
      setCatalogClassifications([{ category: document.getElementById("cat-category").value.trim() || "Decoração", subcategory: "" }]);
      catFormClassificationsDirty = false;
      document.getElementById("catalog-modal-title").textContent = "Novo Produto no Catálogo";
      document.getElementById("catalog-backdrop").hidden = false;
    });
    document.getElementById("cat-add-class-btn").addEventListener("click", () => {
      const category = document.getElementById("cat-category").value.trim() || "Outros";
      const subcategory = document.getElementById("cat-subcategory").value;
      const exists = catFormClassifications.some(
        (c) => c.category === category && (c.subcategory || "") === (subcategory || "")
      );
      if (!exists) {
        catFormClassifications.push({ category, subcategory });
        catFormClassificationsDirty = true;
        renderCatFormClassifications();
      } else {
        showToast("Essa categoria/subcategoria já está vinculada.");
      }
    });
    document.getElementById("cat-classifications-list").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-cat-remove-class]");
      if (!btn || catFormClassifications.length <= 1) return;
      const idx = Number(btn.dataset.catRemoveClass);
      catFormClassifications.splice(idx, 1);
      catFormClassificationsDirty = true;
      const first = catFormClassifications[0];
      if (first) {
        document.getElementById("cat-category").value = first.category;
        syncCatalogSubcatSelect(first.category, first.subcategory || "");
      }
      renderCatFormClassifications();
    });
    document.getElementById("subcat-close-btn").addEventListener("click", () => {
      document.getElementById("subcat-backdrop").hidden = true;
    });
    document.getElementById("subcat-reclassify-btn").addEventListener("click", async () => {
      const btn = document.getElementById("subcat-reclassify-btn");
      btn.disabled = true;
      const orig = btn.textContent;
      btn.textContent = "Reclassificando...";
      try {
        const res = await apiJson("/api/subcategories/reclassify", { method: "POST" });
        await loadSubcategories();
        renderSubcategoriesManagerList();
        await Promise.all([
          onSubcategoriesChanged ? onSubcategoriesChanged() : Promise.resolve(),
          reloadModels ? reloadModels() : Promise.resolve(),
          renderCatalogTab(),
        ]);
        showToast(
          `Reclassificado: ${res.models_updated} modelos e ${res.catalog_updated} produtos (multi-categoria)!`
        );
      } catch (err) {
        showToast(err.message || "Falha ao reclassificar itens.");
      } finally {
        btn.disabled = false;
        btn.textContent = orig;
      }
    });
    document.getElementById("subcat-scope").addEventListener("change", () => {
      editingSubId = null;
      document.getElementById("subcat-parent-cat").value = "";
      renderSubcategoriesManagerList();
    });
    document.getElementById("subcat-filter-cat").addEventListener("change", renderSubcategoriesManagerList);
    document.getElementById("subcat-create-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const scope = document.getElementById("subcat-scope").value;
      const category = document.getElementById("subcat-parent-cat").value.trim();
      const name = document.getElementById("subcat-new-name").value.trim();
      try {
        await apiJson("/api/subcategories", {
          method: "POST",
          body: JSON.stringify({ scope, category, name }),
        });
        document.getElementById("subcat-new-name").value = "";
        showToast("Subcategoria criada!");
        await loadSubcategories();
        renderSubcategoriesManagerList();
        if (scope === "models" && onSubcategoriesChanged) await onSubcategoriesChanged();
        if (scope === "sales_catalog") await renderCatalogTab();
      } catch (err) {
        showToast(err.message || "Falha ao criar subcategoria.");
      }
    });
    document.getElementById("cat-image").addEventListener("input", (e) => {
      const val = e.target.value.trim();
      const prev = document.getElementById("cat-image-preview");
      if (val) {
        prev.src = val;
        prev.hidden = false;
      } else {
        prev.hidden = true;
      }
    });
    document.getElementById("cat-cancel-btn").addEventListener("click", () => { document.getElementById("catalog-backdrop").hidden = true; });
    document.getElementById("catalog-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = document.getElementById("cat-id").value;
      const mode = document.getElementById("cat-mode").value;
      const curCat = document.getElementById("cat-category").value.trim() || "Outros";
      const curSub = document.getElementById("cat-subcategory").value;
      const payloadClasses =
        catFormClassificationsDirty || catFormClassifications.length > 1
          ? catFormClassifications
          : [{ category: curCat, subcategory: curSub }];
      const body = {
        code: document.getElementById("cat-code").value.trim(),
        model_id: document.getElementById("cat-model-id").value ? Number(document.getElementById("cat-model-id").value) : null,
        name: document.getElementById("cat-name").value.trim(),
        category: payloadClasses[0].category,
        subcategory: payloadClasses[0].subcategory || "",
        classifications: payloadClasses,
        dimensions_cm: document.getElementById("cat-dims").value.trim(),
        filament_grams: Number(document.getElementById("cat-grams").value || 0),
        pricing_mode: mode,
        rate_per_gram_brl: mode === "rate_per_gram" ? Number(document.getElementById("cat-rate").value || 0.4) : 0.4,
        margin_percent: mode === "cost_markup" ? Number(document.getElementById("cat-rate").value || 150) : 150,
        sale_price_brl: mode === "manual" ? Number(document.getElementById("cat-manual-price").value || 0) : null,
        extras_cost_brl: Number(document.getElementById("cat-extras").value || 0),
        stock_qty: Number(document.getElementById("cat-stock").value || 0),
        image_url: document.getElementById("cat-image").value.trim(),
      };
      await apiJson(id ? `/api/catalog/${id}` : "/api/catalog", { method: id ? "PATCH" : "POST", body: JSON.stringify(body) });
      document.getElementById("catalog-backdrop").hidden = true;
      showToast("Produto salvo no catálogo!");
      const fullCat = await apiJson("/api/catalog");
      hubState.catalog = fullCat.items;
      await Promise.all([renderCatalogTab(), refreshSummary()]);
    });

    document.getElementById("sale-add-btn").addEventListener("click", () => {
      if (hubState.catalog.length) {
        const first = hubState.catalog[0];
        document.getElementById("sale-catalog").value = first.id;
        document.getElementById("sale-price").value = first.sale_price_brl;
      }
      document.getElementById("sale-backdrop").hidden = false;
    });
    document.getElementById("sale-catalog").addEventListener("change", (e) => {
      const c = hubState.catalog.find((x) => x.id === Number(e.target.value));
      if (c) document.getElementById("sale-price").value = c.sale_price_brl;
    });
    document.getElementById("sale-cancel-btn").addEventListener("click", () => { document.getElementById("sale-backdrop").hidden = true; });
    document.getElementById("sale-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const res = await apiJson("/api/sales", {
        method: "POST",
        body: JSON.stringify({
          catalog_item_id: Number(document.getElementById("sale-catalog").value || 0) || null,
          customer_name: document.getElementById("sale-customer").value.trim(),
          channel: document.getElementById("sale-channel").value,
          quantity: Number(document.getElementById("sale-qty").value || 1),
          unit_price_brl: Number(document.getElementById("sale-price").value || 0),
          payment_status: document.getElementById("sale-payment").value,
          auto_queue_missing: document.getElementById("sale-auto-queue").checked,
        }),
      });
      document.getElementById("sale-backdrop").hidden = true;
      showToast(res.queued_job ? "Venda registrada e saldo enviado para a Fila!" : "Venda registrada com sucesso!");
      await Promise.all([renderCatalogTab(), refreshSummary()]);
    });

    // Media dropzone & upload
    const fileInput = document.getElementById("media-file-input");
    const dropzone = document.getElementById("media-dropzone");
    const updateCount = () => {
      document.getElementById("media-selected-count").textContent = pendingFiles.length
        ? `${pendingFiles.length} foto(s) pronta(s) para enviar.`
        : "Cole um link URL acima (preferencial) ou selecione arquivo.";
    };
    fileInput.addEventListener("change", () => {
      pendingFiles = Array.from(fileInput.files || []);
      updateCount();
    });
    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      pendingFiles = Array.from(e.dataTransfer.files || []).filter((f) => f.type.startsWith("image/"));
      updateCount();
    });

    document.getElementById("media-upload-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const imageUrl = document.getElementById("media-up-url").value.trim();
      const title = document.getElementById("media-up-title").value.trim();
      const postFormat = document.getElementById("media-up-format").value;
      const catalogId = document.getElementById("media-up-catalog").value;
      const jobId = document.getElementById("media-up-job").value;

      if (imageUrl) {
        const fd = new FormData();
        fd.append("image_url", imageUrl);
        fd.append("title", title);
        fd.append("post_format", postFormat);
        if (catalogId) fd.append("catalog_item_id", catalogId);
        if (jobId) fd.append("print_job_id", jobId);
        await apiJson("/api/media", { method: "POST", body: fd });
        document.getElementById("media-up-url").value = "";
        document.getElementById("media-up-title").value = "";
        showToast("Foto salva por link URL!");
        await Promise.all([renderMediaTab(), refreshSummary()]);
        return;
      }

      if (!pendingFiles.length) {
        showToast("Cole um link de imagem (URL) ou selecione pelo menos uma foto.");
        return;
      }
      for (const file of pendingFiles) {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("title", title || file.name.replace(/\.[^.]+$/, ""));
        fd.append("post_format", postFormat);
        if (catalogId) fd.append("catalog_item_id", catalogId);
        if (jobId) fd.append("print_job_id", jobId);
        await apiJson("/api/media", { method: "POST", body: fd });
      }
      pendingFiles = [];
      fileInput.value = "";
      document.getElementById("media-up-title").value = "";
      updateCount();
      showToast("Foto(s) salva(s) no estúdio!");
      await Promise.all([renderMediaTab(), refreshSummary()]);
    });

    document.getElementById("med-file-url").addEventListener("input", (e) => {
      const val = e.target.value.trim();
      const prev = document.getElementById("med-image-preview");
      if (val) {
        prev.src = val;
        prev.hidden = false;
      } else {
        prev.hidden = true;
      }
    });

    document.getElementById("media-filter-status").addEventListener("change", renderMediaTab);
    document.getElementById("med-cancel-btn").addEventListener("click", () => { document.getElementById("media-backdrop").hidden = true; });
    document.getElementById("med-gen-caption-btn").addEventListener("click", async () => {
      const m = hubState.media.find((x) => x.id === Number(document.getElementById("med-id").value));
      const cat = m?.catalog_item_id ? hubState.catalog.find((c) => c.id === m.catalog_item_id) : null;
      const res = await apiJson("/api/media/generate-caption", {
        method: "POST",
        body: JSON.stringify({
          title: document.getElementById("med-title").value.trim(),
          category: cat?.category || "",
          price_brl: cat?.sale_price_brl || null,
        }),
      });
      document.getElementById("med-caption").value = res.caption;
      document.getElementById("med-hashtags").value = res.hashtags;
      if (document.getElementById("med-status").value === "Banco de Fotos") {
        document.getElementById("med-status").value = "Legenda Pronta";
      }
      showToast("Legenda gerada!");
    });
    document.getElementById("media-edit-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = document.getElementById("med-id").value;
      await apiJson(`/api/media/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: document.getElementById("med-title").value.trim(),
          file_url: document.getElementById("med-file-url").value.trim(),
          post_format: document.getElementById("med-format").value,
          status: document.getElementById("med-status").value,
          scheduled_date: document.getElementById("med-date").value,
          caption: document.getElementById("med-caption").value.trim(),
          hashtags: document.getElementById("med-hashtags").value.trim(),
        }),
      });
      document.getElementById("media-backdrop").hidden = true;
      showToast("Post atualizado!");
      await Promise.all([renderMediaTab(), refreshSummary()]);
    });
  }

  async function renderArchivedTab() {
    const [modelsData, jobsData] = await Promise.all([
      apiJson("/api/models?status=Arquivado&limit=100"),
      apiJson("/api/queue?status=Arquivado"),
    ]);
    const archivedModels = modelsData.items || [];
    const archivedJobs = jobsData.items || [];

    const savedGrams =
      archivedModels.reduce((acc, m) => acc + (Number(m.filament_grams) || 0), 0) +
      archivedJobs.reduce((acc, j) => acc + (Number(j.estimated_grams) || 0), 0);

    document.getElementById("archived-metrics").innerHTML = `
      <div class="metric-card"><span class="metric-label">Total Arquivado</span><span class="metric-value tnum">${modelsData.total + archivedJobs.length}</span></div>
      <div class="metric-tile"><div class="metric-value tnum">${modelsData.total}</div><div class="metric-caption">Modelos Arquivados</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${archivedJobs.length}</div><div class="metric-caption">Trabalhos na Fila</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${formatGrams(savedGrams)}</div><div class="metric-caption">Filamento Poupado</div></div>
    `;

    const modelsGrid = document.getElementById("archived-models-grid");
    if (archivedModels.length === 0) {
      modelsGrid.innerHTML = `<div class="empty-state" style="grid-column:1/-1;"><h3>Nenhum modelo arquivado</h3><p>Clique em "Arquivar" nos cards da aba Modelos para ocultar impressões que não precisa.</p></div>`;
    } else {
      modelsGrid.innerHTML = archivedModels
        .map(
          (item) => `
          <article class="card">
            <div class="card-thumb">
              ${
                item.image_url
                  ? `<img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.hidden=true; this.nextElementSibling.style.display='flex';" /><div class="card-thumb-fallback" style="display:none;"><span>Link indisponível</span></div>`
                  : `<div class="card-thumb-fallback"><span>Sem imagem configurada</span></div>`
              }
              <span class="thumb-source">${escapeHtml(item.source)}</span>
              <span class="thumb-status">${escapeHtml(item.size_tier)}</span>
            </div>
            <div class="card-body">
              <div class="card-category-row">
                <span>${escapeHtml(item.category)}${item.subcategory ? ` › <strong>${escapeHtml(item.subcategory)}</strong>` : ""}</span>
                <span class="tnum">${escapeHtml(formatGrams(item.filament_grams))} • ${escapeHtml(formatDuration(item.print_time_min) || "—")}</span>
              </div>
              ${renderCatExtraBadges(item)}
              <h3 class="card-title">${escapeHtml(item.title)}</h3>
            </div>
            <div class="card-footer">
              <a class="btn btn-ghost btn-xs" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">Abrir link ↗</a>
              <div class="card-actions">
                <button class="btn btn-primary btn-xs arch-model-restore-btn" data-id="${item.id}" type="button">Restaurar</button>
                <button class="btn btn-danger btn-xs arch-model-del-btn" data-id="${item.id}" type="button">Excluir</button>
              </div>
            </div>
          </article>
        `
        )
        .join("");

      modelsGrid.querySelectorAll(".arch-model-restore-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await apiJson(`/api/models/${btn.dataset.id}`, {
            method: "PATCH",
            body: JSON.stringify({ status: "Na Fila" }),
          });
          showToast("Modelo restaurado para Modelos!");
          await Promise.all([renderArchivedTab(), refreshSummary(), reloadModels ? reloadModels() : Promise.resolve()]);
        });
      });

      modelsGrid.querySelectorAll(".arch-model-del-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await apiJson(`/api/models/${btn.dataset.id}`, { method: "DELETE" });
          showToast("Modelo excluído definitivamente.");
          await Promise.all([renderArchivedTab(), refreshSummary(), reloadModels ? reloadModels() : Promise.resolve()]);
        });
      });
    }

    const jobsList = document.getElementById("archived-jobs-list");
    if (archivedJobs.length === 0) {
      jobsList.innerHTML = `<div class="empty-state"><h3>Nenhum trabalho arquivado</h3><p>Trabalhos arquivados na Fila de Impressão aparecerão aqui.</p></div>`;
    } else {
      jobsList.innerHTML = archivedJobs
        .map(
          (j) => `
          <div class="queue-card">
            <div class="queue-main">
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <h3 class="queue-title">${escapeHtml(j.title)}</h3>
                <span class="badge">${escapeHtml(j.target_type)}</span>
                <span class="badge">${escapeHtml(j.priority)}</span>
              </div>
              <div class="queue-meta">
                <span>Impressora: <strong>${escapeHtml(j.printer_name || "Não definida")}</strong></span>
                <span>Filamento: <strong>${formatGrams(j.estimated_grams)}</strong></span>
                <span>Tempo: <strong>${formatDuration(j.estimated_time_min)}</strong></span>
                ${j.customer_name ? `<span>Cliente: <strong>${escapeHtml(j.customer_name)}</strong></span>` : ""}
              </div>
            </div>
            <div class="queue-actions">
              <button class="btn btn-primary btn-sm arch-job-restore-btn" data-id="${j.id}" type="button">Restaurar para Fila</button>
              <button class="btn btn-ghost btn-sm arch-job-del-btn" data-id="${j.id}" type="button">Remover</button>
            </div>
          </div>
        `
        )
        .join("");

      jobsList.querySelectorAll(".arch-job-restore-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await apiJson(`/api/queue/${btn.dataset.id}`, {
            method: "PATCH",
            body: JSON.stringify({ status: "Pendente" }),
          });
          showToast("Trabalho restaurado para a Fila!");
          await Promise.all([renderArchivedTab(), refreshSummary()]);
        });
      });

      jobsList.querySelectorAll(".arch-job-del-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await apiJson(`/api/queue/${btn.dataset.id}`, { method: "DELETE" });
          showToast("Trabalho removido definitivamente.");
          await Promise.all([renderArchivedTab(), refreshSummary()]);
        });
      });
    }
  }

  return {
    bindEvents,
    openJobModal,
    openSubcategoriesModal,
    syncCatalogSubcatSelect,
    setCatalogClassifications,
    renderQueueTab,
    renderPrintersTab,
    renderInventoryTab,
    renderCatalogTab,
    renderMediaTab,
    renderArchivedTab,
  };
}
