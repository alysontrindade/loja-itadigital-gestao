import {
  exportFullHubBackupJson,
  getFullErpState,
  importFullHubBackupJson,
  mergeRemoteErpData,
} from "./serverless_hub.js?v=2.1.0";
import { apiJson, escapeHtml, formatBrl, formatDateTimePtBr, formatDuration, formatGrams, showToast } from "./utils.js?v=2.1.0";

function cleanPhone(raw) {
  let digits = String(raw || "").replace(/\D+/g, "");
  if (!digits) return "";
  if (digits.length === 10 || digits.length === 11) digits = "55" + digits;
  return digits;
}

function waLink(phone, message) {
  const clean = cleanPhone(phone);
  const txt = encodeURIComponent(message || "");
  return clean ? `https://wa.me/${clean}?text=${txt}` : `https://wa.me/?text=${txt}`;
}

function renderBarcodeSvg(codeText) {
  const raw = String(codeText || "ITA3D").toUpperCase().slice(0, 16);
  let x = 4;
  const bars = [];
  for (let i = 0; i < raw.length; i++) {
    const ch = raw.charCodeAt(i);
    for (let b = 0; b < 4; b++) {
      const w = ((ch >> b) & 1) ? 2.4 : 1.1;
      if (b % 2 === 0) {
        bars.push(`<rect x="${x.toFixed(1)}" y="2" width="${w}" height="32" fill="#000"/>`);
      }
      x += w + 1.2;
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${Math.ceil(x + 4)} 48" width="160" height="44" style="background:#fff;padding:2px;border-radius:4px;">${bars.join("")}<text x="${Math.ceil(x / 2)}" y="44" font-family="monospace" font-size="9" text-anchor="middle" fill="#000">${escapeHtml(raw)}</text></svg>`;
}

export function createErpController({ refreshSummary, switchTab }) {
  const erpState = {
    customers: [],
    quotes: [],
    suppliers: [],
    purchases: [],
    kits: [],
    nichos: [],
    catalog: [],
    printers: [],
    spools: [],
    models: [],
    sales: [],
  };

  async function loadBaseRefs() {
    const [cust, sup, cat, pr, sp, kits, nichos] = await Promise.all([
      apiJson("/api/customers"),
      apiJson("/api/suppliers"),
      apiJson("/api/catalog"),
      apiJson("/api/printers"),
      apiJson("/api/spools"),
      apiJson("/api/kits"),
      apiJson("/api/nichos"),
    ]);
    erpState.customers = cust.items || [];
    erpState.suppliers = sup.items || [];
    erpState.catalog = cat.items || [];
    erpState.printers = pr.items || [];
    erpState.spools = sp.items || [];
    erpState.kits = kits.items || [];
    erpState.nichos = nichos.items || [];
    syncErpSelects();
  }

  function syncErpSelects() {
    const custOpts =
      '<option value="">Consumidor Final / Avulso</option>' +
      erpState.customers.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}${c.whatsapp ? ` (${escapeHtml(c.whatsapp)})` : ""}</option>`).join("");

    const ordCust = document.getElementById("ord-customer-sel");
    if (ordCust) {
      const cur = ordCust.value;
      ordCust.innerHTML = custOpts;
      if (cur) ordCust.value = cur;
    }

    const qCust = document.getElementById("qt-customer-sel");
    if (qCust) {
      const cur = qCust.value;
      qCust.innerHTML = custOpts;
      if (cur) qCust.value = cur;
    }

    const ordProd = document.getElementById("ord-product-sel");
    if (ordProd) {
      const cur = ordProd.value;
      ordProd.innerHTML =
        '<option value="">Selecione produto 3D / peça ou deixe avulso...</option>' +
        erpState.catalog
          .map(
            (c) =>
              `<option value="${c.id}">${escapeHtml(c.code ? `${c.code} ` : "")}${escapeHtml(c.name)} — ${formatBrl(c.sale_price_brl)} (Estq: ${c.stock_qty})</option>`
          )
          .join("");
      if (cur) ordProd.value = cur;
    }

    const ordKit = document.getElementById("ord-kit-sel");
    if (ordKit) {
      const cur = ordKit.value;
      ordKit.innerHTML =
        '<option value="">Nenhum (usar produto ou avulso)</option>' +
        erpState.kits.map((k) => `<option value="${k.id}">${escapeHtml(k.name)} (${formatBrl(k.sale_price_brl)})</option>`).join("");
      if (cur) ordKit.value = cur;
    }

    const qPrinter = document.getElementById("qt-printer");
    if (qPrinter) {
      const cur = qPrinter.value;
      qPrinter.innerHTML =
        '<option value="">Padrão (R$ 2,50/h)</option>' +
        erpState.printers.map((p) => `<option value="${p.id}">${escapeHtml(p.name)} (${formatBrl(p.hourly_cost_brl)}/h)</option>`).join("");
      if (cur) qPrinter.value = cur;
    }

    const qSpool = document.getElementById("qt-spool");
    if (qSpool) {
      const cur = qSpool.value;
      qSpool.innerHTML =
        '<option value="">Padrão (R$ 120/kg)</option>' +
        erpState.spools
          .map((s) => `<option value="${s.id}">${escapeHtml(s.material)} ${escapeHtml(s.color_name)} (${formatBrl(s.cost_per_kg_brl)}/kg)</option>`)
          .join("");
      if (cur) qSpool.value = cur;
    }

    const qProd = document.getElementById("qt-catalog-ref");
    if (qProd) {
      qProd.innerHTML =
        '<option value="">Preencher de Produto do Catálogo (opcional)</option>' +
        erpState.catalog.map((c) => `<option value="${c.id}">${escapeHtml(c.name)} (${c.filament_grams}g)</option>`).join("");
    }

    const supSel = document.getElementById("pur-supplier");
    if (supSel) {
      supSel.innerHTML =
        '<option value="">Fornecedor Avulso</option>' +
        erpState.suppliers.map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join("");
    }

    const purTarget = document.getElementById("pur-target-id");
    const purKind = document.getElementById("pur-target-kind")?.value || "catalog";
    if (purTarget) {
      if (purKind === "spool") {
        purTarget.innerHTML =
          '<option value="">Carretel novo/avulso</option>' +
          erpState.spools.map((s) => `<option value="${s.id}">${escapeHtml(s.material)} ${escapeHtml(s.color_name)} (Resta ${formatGrams(s.remaining_grams)})</option>`).join("");
      } else {
        purTarget.innerHTML =
          '<option value="">Produto avulso</option>' +
          erpState.catalog.map((c) => `<option value="${c.id}">${escapeHtml(c.code ? `${c.code} ` : "")}${escapeHtml(c.name)} (Estq: ${c.stock_qty})</option>`).join("");
      }
    }

    const kitProdSel = document.getElementById("kit-comp-prod");
    if (kitProdSel) {
      kitProdSel.innerHTML =
        '<option value="">Selecione um produto...</option>' +
        erpState.catalog.map((c) => `<option value="${c.id}">${escapeHtml(c.name)} (Custo ${formatBrl(c.unit_cost_brl)})</option>`).join("");
    }

    const kitNicheSel = document.getElementById("kit-niche");
    if (kitNicheSel) {
      kitNicheSel.innerHTML = erpState.nichos
        .map((n) => `<option value="${escapeHtml(n.nome)}">${escapeHtml(n.nome)}</option>`)
        .join("");
    }

    const labelProdSel = document.getElementById("lbl-product");
    if (labelProdSel) {
      labelProdSel.innerHTML = erpState.catalog
        .map((c) => `<option value="${c.id}">${escapeHtml(c.code ? `${c.code} ` : "")}${escapeHtml(c.name)} — ${formatBrl(c.sale_price_brl)}</option>`)
        .join("");
    }
  }

  // ---- TAB DASHBOARD GERAL ---- //
  async function renderDashboardTab() {
    const d = await apiJson("/api/erp/dashboard");
    const badgeOrd = document.getElementById("badge-orders");
    const badgeQt = document.getElementById("badge-quotes");
    const badgeCrm = document.getElementById("badge-crm");
    if (badgeOrd) badgeOrd.textContent = d.sales_total ?? 0;
    if (badgeQt) badgeQt.textContent = d.quotes_open ?? 0;
    if (badgeCrm) badgeCrm.textContent = d.customers_total ?? 0;

    const metricsEl = document.getElementById("dash-metrics");
    if (metricsEl) {
      metricsEl.innerHTML = `
        <div class="metric-tile"><div class="metric-value tnum">${formatBrl(d.revenue_brl)}</div><div class="metric-caption">Faturamento Total</div></div>
        <div class="metric-tile"><div class="metric-value tnum" style="color:var(--success);">${formatBrl(d.estimated_profit_brl)}</div><div class="metric-caption">Lucro Estimado</div></div>
        <div class="metric-tile"><div class="metric-value tnum">${d.queue_active} / ${d.queue_pending}</div><div class="metric-caption">Fila 3D (Rodando / Pendentes)</div></div>
        <div class="metric-tile"><div class="metric-value tnum">${d.quotes_open}</div><div class="metric-caption">Cotações em Aberto</div></div>
        <div class="metric-tile"><div class="metric-value tnum">${d.models_total}</div><div class="metric-caption">Modelos 3D Catalogados</div></div>
        <div class="metric-tile"><div class="metric-value tnum">${formatGrams(d.spools_grams)}</div><div class="metric-caption">Filamento Total (${d.spools_total} rolos)</div></div>
        <div class="metric-tile"><div class="metric-value tnum">${d.ready_stock_units} un.</div><div class="metric-caption">Pronta Entrega (${d.catalog_total} itens)</div></div>
        <div class="metric-tile"><div class="metric-value tnum">${d.customers_total}</div><div class="metric-caption">Clientes Cadastrados</div></div>
      `;
    }

    const alertsEl = document.getElementById("dash-alerts");
    if (alertsEl) {
      const spoolAlerts = (d.low_spools || []).map(
        (s) => `<li>🧵 Carretel <strong>${escapeHtml(s.material)} ${escapeHtml(s.color_name)}</strong> com apenas <strong>${formatGrams(s.remaining_grams)}</strong></li>`
      );
      const prodAlerts = (d.low_products || []).map(
        (p) => `<li>📦 Produto <strong>${escapeHtml(p.name)}</strong> com estoque <strong>${p.stock_qty} un.</strong></li>`
      );
      const bdays = (d.birthday_customers || []).map((c) => {
        const msg = `Olá ${c.name.split(" ")[0]}! A Ita Arte 3D / Loja ItaDigital passa para desejar um feliz aniversário! Temos uma condição especial esperando por você.`;
        return `<li>🎂 Aniversariante (${escapeHtml(c.birthday)}): <strong>${escapeHtml(c.name)}</strong> — <a href="${waLink(c.whatsapp, msg)}" target="_blank" rel="noopener noreferrer" style="color:var(--cyan);">Enviar Parabéns no WhatsApp ↗</a></li>`;
      });
      const all = [...spoolAlerts, ...bdays, ...prodAlerts];
      alertsEl.innerHTML = all.length
        ? `<ul style="margin:0; padding-left:18px; display:grid; gap:6px;">${all.join("")}</ul>`
        : `<p class="brand-sub">Tudo em dia! Nenhum filamento crítico no momento.</p>`;
    }

    const ordEl = document.getElementById("dash-recent-orders");
    if (ordEl) {
      ordEl.innerHTML = (d.recent_orders || []).length
        ? (d.recent_orders || [])
            .map(
              (o) => `
              <div class="queue-row" style="padding:10px 12px;">
                <div class="queue-main">
                  <div class="queue-top">
                    <span class="badge badge-info">${escapeHtml(o.fulfillment_status)}</span>
                    <span class="badge badge-success">${escapeHtml(o.payment_status)}</span>
                    <strong>${escapeHtml(o.item_name)} (${o.quantity}x)</strong>
                  </div>
                  <div class="queue-meta tnum">
                    <span>Cliente: <strong>${escapeHtml(o.customer_name)}</strong></span>
                    <span>Total: <strong>${formatBrl(o.total_price_brl)}</strong></span>
                    <span>${formatDateTimePtBr(o.created_at)}</span>
                  </div>
                </div>
              </div>`
            )
            .join("")
        : `<p class="brand-sub">Nenhum pedido lançado ainda. Use "+ Novo Pedido / PDV" ao lado.</p>`;
    }

    const jobEl = document.getElementById("dash-active-jobs");
    if (jobEl) {
      jobEl.innerHTML = (d.active_jobs || []).length
        ? (d.active_jobs || [])
            .map(
              (j) => `
              <div class="queue-row" style="padding:10px 12px;">
                <div class="queue-main">
                  <div class="queue-top">
                    <span class="badge ${j.status === "Em Impressão" ? "badge-warn" : "badge-info"}">${escapeHtml(j.status)}</span>
                    <strong>${escapeHtml(j.title)} (${j.quantity}x)</strong>
                  </div>
                  <div class="queue-meta tnum">
                    <span>Impressora: <strong>${escapeHtml(j.printer_name || "A definir")}</strong></span>
                    <span>Filamento: <strong>${formatGrams(j.estimated_grams)}</strong></span>
                    ${j.customer_name ? `<span>Cliente: <strong>${escapeHtml(j.customer_name)}</strong></span>` : ""}
                  </div>
                </div>
              </div>`
            )
            .join("")
        : `<p class="brand-sub">Fila de impressão vazia no momento.</p>`;
    }
  }

  // ---- TAB PEDIDOS DE CLIENTES & PDV ---- //
  function updateOrderLiveTotal() {
    const qty = Math.max(1, Number(document.getElementById("ord-qty")?.value || 1));
    const unit = Math.max(0, Number(document.getElementById("ord-unit-price")?.value || 0));
    const disc = Math.max(0, Number(document.getElementById("ord-discount")?.value || 0));
    const freight = Math.max(0, Number(document.getElementById("ord-freight")?.value || 0));
    const total = Math.max(0, qty * unit - disc + freight);
    const out = document.getElementById("ord-live-total");
    if (out) out.textContent = formatBrl(total);
  }

  async function renderOrdersTab() {
    await loadBaseRefs();
    const fStatus = document.getElementById("ord-filter-status")?.value || "";
    const pStatus = document.getElementById("ord-filter-payment")?.value || "";
    const q = document.getElementById("ord-filter-q")?.value.trim() || "";
    const params = new URLSearchParams();
    if (fStatus) params.set("fulfillment_status", fStatus);
    if (pStatus) params.set("payment_status", pStatus);
    if (q) params.set("q", q);

    const data = await apiJson(`/api/sales?${params.toString()}`);
    erpState.sales = data.items || [];

    const badgeOrd = document.getElementById("badge-orders");
    if (badgeOrd) badgeOrd.textContent = erpState.sales.length;

    const metrics = document.getElementById("orders-metrics");
    if (metrics) {
      const pending = erpState.sales.filter((s) => s.fulfillment_status !== "Entregue").length;
      const toReceive = erpState.sales
        .filter((s) => s.payment_status !== "Pago")
        .reduce((a, s) => a + Number(s.total_price_brl || 0) * (s.payment_status === "Sinal 50%" ? 0.5 : 1), 0);
      metrics.innerHTML = `
        <div class="metric-tile"><div class="metric-value tnum">${data.total}</div><div class="metric-caption">Pedidos / Vendas</div></div>
        <div class="metric-tile"><div class="metric-value tnum">${formatBrl(data.total_revenue_brl)}</div><div class="metric-caption">Total Vendido</div></div>
        <div class="metric-tile"><div class="metric-value tnum">${pending}</div><div class="metric-caption">Em Produção / A Entregar</div></div>
        <div class="metric-tile"><div class="metric-value tnum" style="color:var(--warn);">${formatBrl(toReceive)}</div><div class="metric-caption">Saldo a Receber</div></div>
      `;
    }

    const tbody = document.getElementById("orders-tbody");
    if (!tbody) return;
    if (!erpState.sales.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--muted);">Nenhum pedido encontrado neste filtro.</td></tr>`;
      return;
    }

    tbody.innerHTML = erpState.sales
      .map((s) => {
        const msg = `Olá ${s.customer_name || ""}! Atualização do seu pedido na *Ita Arte 3D / Loja ItaDigital*: ${s.quantity}x ${s.item_name} (${formatBrl(s.total_price_brl)}). Status: *${s.fulfillment_status}* | Pagamento: *${s.payment_status}*.`;
        const fulfillOpts = ["Aguardando Sinal", "Na Fila", "Em Produção", "Pronto para Entrega", "Pronta Entrega", "Entregue"]
          .map((st) => `<option value="${st}" ${s.fulfillment_status === st ? "selected" : ""}>${st}</option>`)
          .join("");
        const payOpts = ["Pendente", "Sinal 50%", "Pago"]
          .map((st) => `<option value="${st}" ${s.payment_status === st ? "selected" : ""}>${st}</option>`)
          .join("");
        return `
          <tr>
            <td class="tnum">#${s.id}<br><span style="color:var(--muted); font-size:11px;">${formatDateTimePtBr(s.created_at)}</span></td>
            <td><strong>${escapeHtml(s.item_name)}</strong><br><span style="color:var(--muted); font-size:11px;">${s.quantity}x • ${escapeHtml(s.channel)} • ${escapeHtml(s.payment_method || "Pix")}</span></td>
            <td><strong>${escapeHtml(s.customer_name || "Cliente")}</strong>${s.customer_whatsapp ? `<br><span style="color:var(--muted); font-size:11px;">${escapeHtml(s.customer_whatsapp)}</span>` : ""}</td>
            <td class="tnum"><strong>${formatBrl(s.total_price_brl)}</strong></td>
            <td><select class="select ord-pay-sel" data-id="${s.id}" style="min-width:110px;">${payOpts}</select></td>
            <td><select class="select ord-status-sel" data-id="${s.id}" style="min-width:140px;">${fulfillOpts}</select></td>
            <td>
              <div class="card-actions">
                <a class="btn btn-secondary btn-xs" href="${waLink(s.customer_whatsapp, msg)}" target="_blank" rel="noopener noreferrer">WhatsApp</a>
                <button class="btn btn-secondary btn-xs ord-print-btn" data-id="${s.id}" type="button">Recibo</button>
                <button class="btn btn-danger btn-xs ord-del-btn" data-id="${s.id}" type="button">Excluir</button>
              </div>
            </td>
          </tr>
        `;
      })
      .join("");

    tbody.querySelectorAll(".ord-pay-sel").forEach((sel) => {
      sel.addEventListener("change", async () => {
        await apiJson(`/api/sales/${sel.dataset.id}`, { method: "PATCH", body: JSON.stringify({ payment_status: sel.value }) });
        showToast("Pagamento atualizado!");
        await Promise.all([renderOrdersTab(), refreshSummary()]);
      });
    });

    tbody.querySelectorAll(".ord-status-sel").forEach((sel) => {
      sel.addEventListener("change", async () => {
        await apiJson(`/api/sales/${sel.dataset.id}`, { method: "PATCH", body: JSON.stringify({ fulfillment_status: sel.value }) });
        showToast("Status do pedido atualizado!");
        await Promise.all([renderOrdersTab(), refreshSummary()]);
      });
    });

    tbody.querySelectorAll(".ord-print-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const s = erpState.sales.find((x) => Number(x.id) === Number(btn.dataset.id));
        if (!s) return;
        const win = window.open("", "_blank", "width=520,height=680");
        if (!win) return;
        win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Recibo Pedido #${s.id}</title>
          <style>body{font-family:Arial,sans-serif;padding:24px;color:#111}h2{margin:0 0 6px}table{width:100%;border-collapse:collapse;margin:16px 0}th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left}</style></head>
          <body><h2>Ita Arte 3D / Loja ItaDigital</h2><p>Comprovante de Pedido #${s.id} • ${formatDateTimePtBr(s.created_at)}</p><hr>
          <p><strong>Cliente:</strong> ${escapeHtml(s.customer_name)} ${s.customer_whatsapp ? `(${escapeHtml(s.customer_whatsapp)})` : ""}<br>
          <strong>Canal:</strong> ${escapeHtml(s.channel)} • <strong>Entrega:</strong> ${escapeHtml(s.fulfillment_status)}</p>
          <table><thead><tr><th>Item</th><th>Qtd</th><th>Unit.</th><th>Total</th></tr></thead>
          <tbody><tr><td>${escapeHtml(s.item_name)}</td><td>${s.quantity}x</td><td>${formatBrl(s.unit_price_brl)}</td><td><strong>${formatBrl(s.total_price_brl)}</strong></td></tr></tbody></table>
          <p><strong>Pagamento (${escapeHtml(s.payment_method || "Pix")}):</strong> ${escapeHtml(s.payment_status)}</p>
          ${s.notes ? `<p>Obs.: ${escapeHtml(s.notes)}</p>` : ""}
          <script>window.print();</script></body></html>`);
        win.document.close();
      });
    });

    tbody.querySelectorAll(".ord-del-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/sales/${btn.dataset.id}`, { method: "DELETE" });
        showToast("Pedido removido.");
        await Promise.all([renderOrdersTab(), refreshSummary()]);
      });
    });
  }

  // ---- TAB COTAÇÕES 3D & FORNECEDORES ---- //
  function getQuoteLiveValues() {
    const qty = Math.max(1, Number(document.getElementById("qt-qty")?.value || 1));
    const grams = Math.max(0, Number(document.getElementById("qt-grams")?.value || 0));
    const timeMin = Math.max(0, Number(document.getElementById("qt-time")?.value || 0));
    const spId = document.getElementById("qt-spool")?.value;
    const prId = document.getElementById("qt-printer")?.value;
    const spoolObj = erpState.spools.find((s) => String(s.id) === String(spId));
    const printerObj = erpState.printers.find((p) => String(p.id) === String(prId));

    const rawCostKg = document.getElementById("qt-cost-kg")?.value;
    const rawHourly = document.getElementById("qt-hourly")?.value;
    const costKg = Math.max(0, Number(rawCostKg !== undefined && rawCostKg !== "" ? rawCostKg : 120));
    const hourly = Math.max(0, Number(rawHourly !== undefined && rawHourly !== "" ? rawHourly : 2.5));
    const energyWear = Math.max(0, Number(document.getElementById("qt-energy")?.value || 0));
    const extras = Math.max(0, Number(document.getElementById("qt-extras")?.value || 0));
    const mode = document.getElementById("qt-mode")?.value || "cost_markup";
    const marginPct = Math.max(0, Number(document.getElementById("qt-margin")?.value || 160));
    const rateG = Math.max(0, Number(document.getElementById("qt-rate-g")?.value || 0.45));
    const manualPrice = Math.max(0, Number(document.getElementById("qt-manual-price")?.value || 0));

    const filamentCost = (grams / 1000) * costKg;
    const machineCost = (timeMin / 60) * hourly + energyWear;
    const unitCost = filamentCost + machineCost + extras;
    let unitPrice = manualPrice;
    if (mode === "rate_per_gram") unitPrice = grams * rateG + extras;
    else if (mode === "cost_markup") unitPrice = unitCost * (1 + marginPct / 100);
    const total = unitPrice * qty;
    const profit = total - unitCost * qty;
    return { filamentCost, machineCost, unitCost, unitPrice, total, profit, costKg, hourly };
  }

  function updateQuoteLivePreview() {
    const res = getQuoteLiveValues();
    const box = document.getElementById("qt-live-preview");
    if (!box) return;
    box.innerHTML = `
      <div class="metric-tile"><div class="metric-value tnum">${formatBrl(res.filamentCost)}</div><div class="metric-caption">Filamento (un.)</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${formatBrl(res.machineCost)}</div><div class="metric-caption">Máquina + Energia</div></div>
      <div class="metric-tile"><div class="metric-value tnum">${formatBrl(res.unitCost)}</div><div class="metric-caption">Custo Total (un.)</div></div>
      <div class="metric-tile"><div class="metric-value tnum" style="color:var(--cyan);">${formatBrl(res.total)}</div><div class="metric-caption">Preço Orçamento (${formatBrl(res.unitPrice)}/un.) • Lucro ${formatBrl(res.profit)}</div></div>
    `;
  }

  function updateSupplierCalcLive() {
    const currency = document.getElementById("supcalc-currency")?.value || "BRL";
    const lotVal = Math.max(0, Number(document.getElementById("supcalc-lot")?.value || 0));
    const usdRate = Math.max(0.1, Number(document.getElementById("supcalc-usd")?.value || 5.8));
    const freight = Math.max(0, Number(document.getElementById("supcalc-freight")?.value || 0));
    const taxPct = Math.max(0, Number(document.getElementById("supcalc-tax")?.value || 0));
    const others = Math.max(0, Number(document.getElementById("supcalc-others")?.value || 0));
    const qty = Math.max(1, Number(document.getElementById("supcalc-qty")?.value || 1));
    const marginPct = Math.max(0, Number(document.getElementById("supcalc-margin")?.value || 60));
    const feePct = Math.max(0, Math.min(80, Number(document.getElementById("supcalc-fee")?.value || 18)));

    const goodsBrl = currency === "USD" ? lotVal * usdRate : lotVal;
    const taxBrl = goodsBrl * (taxPct / 100);
    const totalBrl = goodsBrl + freight + taxBrl + others;
    const unitCost = totalBrl / qty;
    const directPrice = unitCost * (1 + marginPct / 100);
    const mktPrice = directPrice / (1 - feePct / 100);

    const out = document.getElementById("supcalc-result");
    if (out) {
      out.innerHTML = `
        <div class="metric-tile"><div class="metric-value tnum">${formatBrl(totalBrl)}</div><div class="metric-caption">Custo Total Lote (Impostos ${formatBrl(taxBrl)})</div></div>
        <div class="metric-tile"><div class="metric-value tnum">${formatBrl(unitCost)}</div><div class="metric-caption">Custo Unitário Rateado</div></div>
        <div class="metric-tile"><div class="metric-value tnum" style="color:var(--success);">${formatBrl(directPrice)}</div><div class="metric-caption">Venda Direta (Loja / Pix)</div></div>
        <div class="metric-tile"><div class="metric-value tnum" style="color:var(--cyan);">${formatBrl(mktPrice)}</div><div class="metric-caption">Venda Marketplace (Taxa ${feePct}%)</div></div>
      `;
    }
  }

  async function renderQuotesTab() {
    await loadBaseRefs();
    updateQuoteLivePreview();
    updateSupplierCalcLive();
    const status = document.getElementById("qt-filter-status")?.value || "";
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    const data = await apiJson(`/api/quotes?${params.toString()}`);
    erpState.quotes = data.items || [];

    const badgeQt = document.getElementById("badge-quotes");
    if (badgeQt) badgeQt.textContent = erpState.quotes.filter((q) => q.status === "Rascunho" || q.status === "Enviada").length;

    const listEl = document.getElementById("quotes-list");
    if (!listEl) return;
    if (!erpState.quotes.length) {
      listEl.innerHTML = `<div class="state-box"><h2>Nenhuma cotação salva ainda</h2><p>Preencha a calculadora acima para gerar seu primeiro orçamento 3D.</p></div>`;
      return;
    }

    listEl.innerHTML = erpState.quotes
      .map((q) => {
        const badgeCls = q.status === "Aprovada" ? "badge-success" : q.status === "Recusada" ? "badge-danger" : "badge-info";
        const msg =
          `Olá *${q.customer_name || ""}*! Segue o orçamento *${q.code}* da *Ita Arte 3D*:\n` +
          `🖨️ Peça: *${q.title}* (${q.quantity}x)\n` +
          `💰 Valor total: *${formatBrl(q.total_price_brl)}* (${formatBrl(q.unit_price_brl)}/un.)\n` +
          `⏳ Prazo estimado: *${q.lead_days} dia(s)*\n` +
          (q.notes ? `📝 Detalhes: ${q.notes}\n` : "") +
          `Para aprovar e iniciar a impressão, basta confirmar por aqui (sinal 50% via Pix)!`;
        return `
          <article class="queue-row">
            <div class="queue-main">
              <div class="queue-top">
                <span class="badge ${badgeCls}">${escapeHtml(q.status)}</span>
                <span class="badge badge-muted">${escapeHtml(q.code)}</span>
                <h3 class="queue-title">${escapeHtml(q.title)} <span class="tnum" style="color:var(--muted);">(${q.quantity}x)</span></h3>
              </div>
              <div class="queue-meta tnum">
                <span>Cliente: <strong>${escapeHtml(q.customer_name)}</strong></span>
                <span>Custo: <strong>${formatBrl(q.unit_cost_brl)}</strong></span>
                <span>Total: <strong style="color:var(--cyan);">${formatBrl(q.total_price_brl)}</strong></span>
                <span>Lucro est.: <strong style="color:var(--success);">${formatBrl(q.estimated_profit_brl)}</strong></span>
                <span>Fil.: <strong>${formatGrams(q.grams)}</strong> • <strong>${formatDuration(q.time_min) || `${q.time_min}m`}</strong></span>
                <span>Prazo: <strong>${q.lead_days}d</strong></span>
              </div>
              ${q.notes ? `<div class="slicing-note-line">${escapeHtml(q.notes)}</div>` : ""}
            </div>
            <div class="queue-actions">
              <a class="btn btn-secondary btn-sm" href="${waLink(q.customer_whatsapp, msg)}" target="_blank" rel="noopener noreferrer">WhatsApp</a>
              <button class="btn btn-secondary btn-sm qt-print-btn" data-id="${q.id}" type="button">Imprimir PDF</button>
              ${q.status !== "Aprovada" ? `<button class="btn btn-success btn-sm qt-approve-btn" data-id="${q.id}" type="button">✅ Aprovar → Pedido + Fila 3D</button>` : ""}
              <button class="btn btn-ghost btn-sm qt-del-btn" data-id="${q.id}" type="button">Excluir</button>
            </div>
          </article>
        `;
      })
      .join("");

    listEl.querySelectorAll(".qt-approve-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/quotes/${btn.dataset.id}/approve`, { method: "POST" });
        showToast("Cotação aprovada! Pedido de cliente e trabalho na Fila 3D criados.");
        await Promise.all([renderQuotesTab(), refreshSummary()]);
      });
    });

    listEl.querySelectorAll(".qt-print-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const q = erpState.quotes.find((x) => Number(x.id) === Number(btn.dataset.id));
        if (!q) return;
        const win = window.open("", "_blank", "width=620,height=720");
        if (!win) return;
        win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Orçamento ${escapeHtml(q.code)}</title>
          <style>body{font-family:Arial,sans-serif;padding:28px;color:#111}h1{margin:0;font-size:20px}table{width:100%;border-collapse:collapse;margin:18px 0}th,td{border:1px solid #cbd5e1;padding:10px;text-align:left}</style></head>
          <body><h1>Ita Arte 3D — Orçamento ${escapeHtml(q.code)}</h1>
          <p>Data: ${formatDateTimePtBr(q.created_at)} • Validade: 7 dias</p><hr>
          <p><strong>Cliente:</strong> ${escapeHtml(q.customer_name)} ${q.customer_whatsapp ? `• WhatsApp: ${escapeHtml(q.customer_whatsapp)}` : ""}</p>
          <table><thead><tr><th>Descrição do Projeto / Peça 3D</th><th>Qtd</th><th>Unitário</th><th>Subtotal</th></tr></thead>
          <tbody><tr><td>${escapeHtml(q.title)}<br><small>Material: ${escapeHtml(q.spool_label || "PLA/PETG")} • Peso est.: ${q.grams}g</small></td><td>${q.quantity}</td><td>${formatBrl(q.unit_price_brl)}</td><td><strong>${formatBrl(q.total_price_brl)}</strong></td></tr></tbody></table>
          <p><strong>Prazo de Produção:</strong> ${q.lead_days} dia(s) úteis após aprovação e sinal de 50%.</p>
          ${q.notes ? `<p><strong>Observações:</strong> ${escapeHtml(q.notes)}</p>` : ""}
          <script>window.print();</script></body></html>`);
        win.document.close();
      });
    });

    listEl.querySelectorAll(".qt-del-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiJson(`/api/quotes/${btn.dataset.id}`, { method: "DELETE" });
        showToast("Cotação excluída.");
        await Promise.all([renderQuotesTab(), refreshSummary()]);
      });
    });
  }

  // ---- TAB CRM: CLIENTES, FORNECEDORES & COMPRAS ---- //
  async function renderCrmTab() {
    await loadBaseRefs();
    const qCust = document.getElementById("cust-filter-q")?.value.trim() || "";
    const bMonth = document.getElementById("cust-filter-bday")?.checked ? String(new Date().getMonth() + 1) : "";
    const params = new URLSearchParams();
    if (qCust) params.set("q", qCust);
    if (bMonth) params.set("birthday_month", bMonth);

    const [custData, purData] = await Promise.all([
      apiJson(`/api/customers?${params.toString()}`),
      apiJson("/api/purchases"),
    ]);
    erpState.customers = custData.items || [];
    erpState.purchases = purData.items || [];

    const badgeCrm = document.getElementById("badge-crm");
    if (badgeCrm) badgeCrm.textContent = custData.total ?? erpState.customers.length;

    const custBody = document.getElementById("customers-tbody");
    if (custBody) {
      custBody.innerHTML = erpState.customers.length
        ? erpState.customers
            .map((c) => {
              const msg = `Olá ${c.name.split(" ")[0]}! Aqui é da Loja ItaDigital / Ita Arte 3D.`;
              return `
                <tr>
                  <td><strong>${escapeHtml(c.name)}</strong>${c.notes ? `<br><span style="color:var(--muted); font-size:11px;">${escapeHtml(c.notes)}</span>` : ""}</td>
                  <td class="tnum">${escapeHtml(c.whatsapp || "—")}</td>
                  <td>${escapeHtml(c.city || "—")}</td>
                  <td class="tnum">${escapeHtml(c.birthday || "—")}</td>
                  <td class="tnum">${c.orders_count} ped. • <strong>${formatBrl(c.total_spent_brl)}</strong></td>
                  <td>
                    <div class="card-actions">
                      <a class="btn btn-secondary btn-xs" href="${waLink(c.whatsapp, msg)}" target="_blank" rel="noopener noreferrer">WhatsApp</a>
                      <button class="btn btn-accent btn-xs cust-order-btn" data-id="${c.id}" type="button">+ Pedido</button>
                      <button class="btn btn-danger btn-xs cust-del-btn" data-id="${c.id}" type="button">Excluir</button>
                    </div>
                  </td>
                </tr>`;
            })
            .join("")
        : `<tr><td colspan="6" style="text-align:center; color:var(--muted);">Nenhum cliente encontrado.</td></tr>`;

      custBody.querySelectorAll(".cust-order-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const c = erpState.customers.find((x) => Number(x.id) === Number(btn.dataset.id));
          if (!c) return;
          document.getElementById("ord-customer-sel").value = c.id;
          document.getElementById("ord-customer-name").value = c.name;
          document.getElementById("ord-customer-wa").value = c.whatsapp || "";
          await switchTab("orders");
        });
      });
      custBody.querySelectorAll(".cust-del-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await apiJson(`/api/customers/${btn.dataset.id}`, { method: "DELETE" });
          showToast("Cliente removido.");
          await Promise.all([renderCrmTab(), refreshSummary()]);
        });
      });
    }

    const supGrid = document.getElementById("suppliers-grid");
    if (supGrid) {
      supGrid.innerHTML = erpState.suppliers
        .map((s) => {
          const msg = `Olá! Gostaria de solicitar cotação e disponibilidade de estoque/filamentos para reposição na Ita Arte 3D / Loja ItaDigital.`;
          return `
            <article class="card">
              <div class="card-body">
                <div class="card-category-row">
                  <span>${escapeHtml(s.type)}</span>
                  <span class="tnum">${escapeHtml(s.city_uf || "")}</span>
                </div>
                <h3 class="card-title">${escapeHtml(s.name)}</h3>
                <div class="specs-strip tnum">
                  <span class="spec-pill">Prazo: <strong>${s.lead_days}d</strong></span>
                  <span class="spec-pill">Mínimo: <strong>${formatBrl(s.min_order_brl)}</strong></span>
                  ${s.whatsapp ? `<span class="spec-pill">${escapeHtml(s.whatsapp)}</span>` : ""}
                </div>
                ${s.notes ? `<p class="rec-reason">${escapeHtml(s.notes)}</p>` : ""}
              </div>
              <div class="card-footer">
                <div class="card-actions">
                  <a class="btn btn-secondary btn-xs" href="${waLink(s.whatsapp, msg)}" target="_blank" rel="noopener noreferrer">Cotar WhatsApp</a>
                  ${s.site ? `<a class="btn btn-ghost btn-xs" href="${escapeHtml(s.site)}" target="_blank" rel="noopener noreferrer">Site ↗</a>` : ""}
                </div>
                <button class="btn btn-danger btn-xs sup-del-btn" data-id="${s.id}" type="button">Excluir</button>
              </div>
            </article>
          `;
        })
        .join("");

      supGrid.querySelectorAll(".sup-del-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await apiJson(`/api/suppliers/${btn.dataset.id}`, { method: "DELETE" });
          showToast("Fornecedor removido.");
          await Promise.all([renderCrmTab(), refreshSummary()]);
        });
      });
    }

    const purBody = document.getElementById("purchases-tbody");
    if (purBody) {
      purBody.innerHTML = erpState.purchases
        .map(
          (p) => `
          <tr>
            <td class="tnum">${formatDateTimePtBr(p.created_at)}</td>
            <td><strong>${escapeHtml(p.item_name)}</strong></td>
            <td>${escapeHtml(p.supplier_name)}</td>
            <td class="tnum">${p.quantity}</td>
            <td class="tnum">${formatBrl(p.final_unit_cost_brl)}</td>
            <td class="tnum"><strong>${formatBrl(p.total_brl)}</strong></td>
            <td><button class="btn btn-ghost btn-xs pur-del-btn" data-id="${p.id}" type="button">Excluir</button></td>
          </tr>
        `
        )
        .join("");
      purBody.querySelectorAll(".pur-del-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await apiJson(`/api/purchases/${btn.dataset.id}`, { method: "DELETE" });
          showToast("Registro de compra removido.");
          await renderCrmTab();
        });
      });
    }
  }

  // ---- KITS, NICHOS & ETIQUETAS NA ABA CATÁLOGO ---- //
  async function renderCatalogExtras() {
    await loadBaseRefs();
    const kitsGrid = document.getElementById("kits-grid");
    if (kitsGrid) {
      kitsGrid.innerHTML = erpState.kits.length
        ? erpState.kits
            .map(
              (k) => `
              <article class="card">
                <div class="card-body">
                  <div class="card-category-row">
                    <span>${escapeHtml(k.niche)}</span>
                    <span class="badge badge-purple">${escapeHtml(k.level)}</span>
                  </div>
                  <h3 class="card-title">${escapeHtml(k.name)}</h3>
                  <div class="specs-strip tnum">
                    <span class="spec-pill">Custo: <strong>${formatBrl(k.total_cost_brl)}</strong></span>
                    <span class="spec-pill">Venda: <strong style="color:var(--cyan);">${formatBrl(k.sale_price_brl)}</strong></span>
                  </div>
                  ${k.notes ? `<p class="rec-reason">${escapeHtml(k.notes)}</p>` : ""}
                </div>
                <div class="card-footer">
                  <button class="btn btn-accent btn-xs kit-sell-btn" data-id="${k.id}" type="button">Vender Kit</button>
                  <button class="btn btn-danger btn-xs kit-del-btn" data-id="${k.id}" type="button">Excluir</button>
                </div>
              </article>
            `
            )
            .join("")
        : `<p class="brand-sub">Nenhum kit cadastrado.</p>`;

      kitsGrid.querySelectorAll(".kit-sell-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const k = erpState.kits.find((x) => Number(x.id) === Number(btn.dataset.id));
          if (!k) return;
          document.getElementById("ord-kit-sel").value = k.id;
          document.getElementById("ord-product-sel").value = "";
          document.getElementById("ord-item-name").value = `Kit: ${k.name}`;
          document.getElementById("ord-unit-price").value = k.sale_price_brl;
          updateOrderLiveTotal();
          await switchTab("orders");
        });
      });
      kitsGrid.querySelectorAll(".kit-del-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await apiJson(`/api/kits/${btn.dataset.id}`, { method: "DELETE" });
          showToast("Kit removido.");
          await Promise.all([renderCatalogExtras(), refreshSummary()]);
        });
      });
    }

    const nichosWrap = document.getElementById("nichos-list");
    if (nichosWrap) {
      nichosWrap.innerHTML = erpState.nichos
        .map(
          (n) => `
          <span class="rubric-badge" style="padding:5px 10px;">
            <span class="rubric-dot" style="background:${escapeHtml(n.cor || "#38bdf8")};"></span>
            <strong>${escapeHtml(n.nome)}</strong>
          </span>`
        )
        .join("");
    }
  }

  function openQuoteWithModel(model) {
    loadBaseRefs().then(() => {
      document.getElementById("qt-title").value = model.title || "";
      document.getElementById("qt-grams").value = model.filament_grams || 60;
      document.getElementById("qt-time").value = model.print_time_min || 90;
      document.getElementById("qt-notes").value = model.dimensions_mm ? `Dimensões: ${model.dimensions_mm}` : "";
      updateQuoteLivePreview();
      switchTab("quotes");
    });
  }

  function bindErpEvents() {
    // Atalhos no dashboard
    document.querySelectorAll("[data-dash-go]").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.dashGo));
    });

    // Pedidos / PDV
    document.getElementById("ord-customer-sel")?.addEventListener("change", (e) => {
      const c = erpState.customers.find((x) => String(x.id) === String(e.target.value));
      document.getElementById("ord-customer-name").value = c ? c.name : "";
      document.getElementById("ord-customer-wa").value = c ? c.whatsapp || "" : "";
    });
    document.getElementById("ord-product-sel")?.addEventListener("change", (e) => {
      const p = erpState.catalog.find((x) => String(x.id) === String(e.target.value));
      if (p) {
        document.getElementById("ord-kit-sel").value = "";
        document.getElementById("ord-item-name").value = p.name;
        document.getElementById("ord-unit-price").value = p.sale_price_brl;
        updateOrderLiveTotal();
      }
    });
    document.getElementById("ord-kit-sel")?.addEventListener("change", (e) => {
      const k = erpState.kits.find((x) => String(x.id) === String(e.target.value));
      if (k) {
        document.getElementById("ord-product-sel").value = "";
        document.getElementById("ord-item-name").value = `Kit: ${k.name}`;
        document.getElementById("ord-unit-price").value = k.sale_price_brl;
        updateOrderLiveTotal();
      }
    });
    ["ord-qty", "ord-unit-price", "ord-discount", "ord-freight"].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", updateOrderLiveTotal);
    });
    document.getElementById("order-create-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = {
        customer_id: document.getElementById("ord-customer-sel").value || null,
        customer_name: document.getElementById("ord-customer-name").value.trim() || "Consumidor Final",
        customer_whatsapp: document.getElementById("ord-customer-wa").value.trim(),
        catalog_item_id: document.getElementById("ord-product-sel").value || null,
        kit_id: document.getElementById("ord-kit-sel").value || null,
        item_name: document.getElementById("ord-item-name").value.trim(),
        quantity: Number(document.getElementById("ord-qty").value || 1),
        unit_price_brl: Number(document.getElementById("ord-unit-price").value || 0),
        discount_brl: Number(document.getElementById("ord-discount").value || 0),
        freight_brl: Number(document.getElementById("ord-freight").value || 0),
        channel: document.getElementById("ord-channel").value,
        payment_method: document.getElementById("ord-pay-method").value,
        payment_status: document.getElementById("ord-pay-status").value,
        fulfillment_status: document.getElementById("ord-status").value || undefined,
        auto_queue_missing: document.getElementById("ord-auto-queue").checked,
        notes: document.getElementById("ord-notes").value.trim(),
      };
      const res = await apiJson("/api/sales", { method: "POST", body: JSON.stringify(body) });
      e.target.reset();
      updateOrderLiveTotal();
      showToast(res.queued_job ? "Pedido salvo e enviado automaticamente para a Fila 3D!" : "Pedido registrado com sucesso!");
      await Promise.all([renderOrdersTab(), refreshSummary()]);
    });
    ["ord-filter-status", "ord-filter-payment"].forEach((id) => {
      document.getElementById(id)?.addEventListener("change", renderOrdersTab);
    });
    document.getElementById("ord-filter-q")?.addEventListener("input", renderOrdersTab);

    // Cotações 3D
    document.getElementById("qt-customer-sel")?.addEventListener("change", (e) => {
      const c = erpState.customers.find((x) => String(x.id) === String(e.target.value));
      document.getElementById("qt-customer-name").value = c ? c.name : "";
      document.getElementById("qt-customer-wa").value = c ? c.whatsapp || "" : "";
    });
    document.getElementById("qt-catalog-ref")?.addEventListener("change", (e) => {
      const p = erpState.catalog.find((x) => String(x.id) === String(e.target.value));
      if (p) {
        document.getElementById("qt-title").value = p.name;
        document.getElementById("qt-grams").value = p.filament_grams || 50;
        updateQuoteLivePreview();
      }
    });
    document.getElementById("qt-printer")?.addEventListener("change", (e) => {
      const p = erpState.printers.find((x) => String(x.id) === String(e.target.value));
      const hourlyEl = document.getElementById("qt-hourly");
      if (p && hourlyEl && p.hourly_cost_brl != null) {
        hourlyEl.value = p.hourly_cost_brl;
      }
      updateQuoteLivePreview();
    });
    document.getElementById("qt-spool")?.addEventListener("change", (e) => {
      const s = erpState.spools.find((x) => String(x.id) === String(e.target.value));
      const costEl = document.getElementById("qt-cost-kg");
      if (s && costEl && s.cost_per_kg_brl != null) {
        costEl.value = s.cost_per_kg_brl;
      }
      updateQuoteLivePreview();
    });
    ["qt-qty", "qt-grams", "qt-time", "qt-hourly", "qt-cost-kg", "qt-energy", "qt-extras", "qt-mode", "qt-margin", "qt-rate-g", "qt-manual-price"].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", updateQuoteLivePreview);
      document.getElementById(id)?.addEventListener("change", updateQuoteLivePreview);
    });
    document.getElementById("quote-create-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const live = getQuoteLiveValues();
      const body = {
        customer_id: document.getElementById("qt-customer-sel").value || null,
        customer_name: document.getElementById("qt-customer-name").value.trim() || "Cliente",
        customer_whatsapp: document.getElementById("qt-customer-wa").value.trim(),
        catalog_item_id: document.getElementById("qt-catalog-ref").value || null,
        printer_id: document.getElementById("qt-printer").value || null,
        spool_id: document.getElementById("qt-spool").value || null,
        title: document.getElementById("qt-title").value.trim(),
        quantity: Number(document.getElementById("qt-qty").value || 1),
        grams: Number(document.getElementById("qt-grams").value || 0),
        time_min: Number(document.getElementById("qt-time").value || 0),
        spool_cost_per_kg_brl: live.costKg,
        printer_hourly_cost_brl: live.hourly,
        energy_wear_brl: Number(document.getElementById("qt-energy").value || 0),
        extras_brl: Number(document.getElementById("qt-extras").value || 0),
        pricing_mode: document.getElementById("qt-mode").value,
        margin_percent: Number(document.getElementById("qt-margin").value || 160),
        rate_per_gram_brl: Number(document.getElementById("qt-rate-g").value || 0.45),
        unit_price_brl: live.unitPrice,
        lead_days: Number(document.getElementById("qt-lead-days").value || 2),
        notes: document.getElementById("qt-notes").value.trim(),
      };
      await apiJson("/api/quotes", { method: "POST", body: JSON.stringify(body) });
      showToast("Cotação 3D salva!");
      await Promise.all([renderQuotesTab(), refreshSummary()]);
    });
    document.getElementById("qt-filter-status")?.addEventListener("change", renderQuotesTab);

    // Calculadora de Cotação com Fornecedor
    ["supcalc-currency", "supcalc-lot", "supcalc-usd", "supcalc-freight", "supcalc-tax", "supcalc-others", "supcalc-qty", "supcalc-margin", "supcalc-fee"].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", updateSupplierCalcLive);
      document.getElementById(id)?.addEventListener("change", updateSupplierCalcLive);
    });

    // CRM: Clientes, Fornecedores & Compras
    document.getElementById("cust-create-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      await apiJson("/api/customers", {
        method: "POST",
        body: JSON.stringify({
          name: document.getElementById("cust-name").value.trim(),
          whatsapp: document.getElementById("cust-wa").value.trim(),
          city: document.getElementById("cust-city").value.trim(),
          birthday: document.getElementById("cust-bday").value.trim(),
          notes: document.getElementById("cust-notes").value.trim(),
        }),
      });
      e.target.reset();
      showToast("Cliente cadastrado!");
      await Promise.all([renderCrmTab(), refreshSummary()]);
    });
    document.getElementById("cust-filter-q")?.addEventListener("input", renderCrmTab);
    document.getElementById("cust-filter-bday")?.addEventListener("change", renderCrmTab);

    document.getElementById("sup-create-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      await apiJson("/api/suppliers", {
        method: "POST",
        body: JSON.stringify({
          name: document.getElementById("sup-name").value.trim(),
          type: document.getElementById("sup-type").value.trim(),
          whatsapp: document.getElementById("sup-wa").value.trim(),
          site: document.getElementById("sup-site").value.trim(),
          city_uf: document.getElementById("sup-city").value.trim(),
          lead_days: Number(document.getElementById("sup-lead").value || 5),
          min_order_brl: Number(document.getElementById("sup-min").value || 0),
          notes: document.getElementById("sup-notes").value.trim(),
        }),
      });
      e.target.reset();
      showToast("Fornecedor cadastrado!");
      await Promise.all([renderCrmTab(), refreshSummary()]);
    });

    document.getElementById("pur-target-kind")?.addEventListener("change", syncErpSelects);
    document.getElementById("pur-create-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      await apiJson("/api/purchases", {
        method: "POST",
        body: JSON.stringify({
          supplier_id: document.getElementById("pur-supplier").value || null,
          target_kind: document.getElementById("pur-target-kind").value,
          target_id: document.getElementById("pur-target-id").value || null,
          item_name: document.getElementById("pur-item-name").value.trim(),
          quantity: Number(document.getElementById("pur-qty").value || 1),
          unit_cost_brl: Number(document.getElementById("pur-unit-cost").value || 0),
          freight_brl: Number(document.getElementById("pur-freight").value || 0),
          taxes_brl: Number(document.getElementById("pur-taxes").value || 0),
        }),
      });
      e.target.reset();
      showToast("Compra registrada e estoque atualizado!");
      await Promise.all([renderCrmTab(), refreshSummary()]);
    });

    // Kits & Etiquetas na aba Catálogo
    document.getElementById("kit-create-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const prodId = document.getElementById("kit-comp-prod").value;
      const prod = erpState.catalog.find((c) => String(c.id) === String(prodId));
      await apiJson("/api/kits", {
        method: "POST",
        body: JSON.stringify({
          name: document.getElementById("kit-name").value.trim(),
          level: document.getElementById("kit-level").value,
          niche: document.getElementById("kit-niche").value,
          items: prod ? [{ catalog_item_id: prod.id, name: prod.name, qty: 1, unit_cost_brl: prod.unit_cost_brl }] : [],
          total_cost_brl: prod ? prod.unit_cost_brl : 0,
          sale_price_brl: Number(document.getElementById("kit-price").value || 0),
          notes: document.getElementById("kit-notes").value.trim(),
        }),
      });
      e.target.reset();
      showToast("Kit / Combo salvo!");
      await Promise.all([renderCatalogExtras(), refreshSummary()]);
    });

    document.getElementById("lbl-print-btn")?.addEventListener("click", () => {
      const pid = document.getElementById("lbl-product").value;
      const qty = Math.max(1, Math.min(48, Number(document.getElementById("lbl-qty").value || 4)));
      const p = erpState.catalog.find((c) => String(c.id) === String(pid));
      if (!p) return;
      const svg = renderBarcodeSvg(p.code || `PROD-${p.id}`);
      const labels = Array.from({ length: qty })
        .map(
          () => `<div class="lbl"><div class="lbl-name">${escapeHtml(p.name)}</div>${svg}<div class="lbl-price">${formatBrl(p.sale_price_brl)}</div></div>`
        )
        .join("");
      const win = window.open("", "_blank", "width=760,height=720");
      if (!win) return;
      win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Etiquetas — ${escapeHtml(p.name)}</title>
        <style>body{font-family:Arial,sans-serif;margin:16px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.lbl{border:1px dashed #666;padding:10px;text-align:center;border-radius:6px;break-inside:avoid}.lbl-name{font-size:12px;font-weight:bold;margin-bottom:4px}.lbl-price{font-size:16px;font-weight:800;margin-top:4px}</style></head>
        <body><div class="grid">${labels}</div><script>window.print();</script></body></html>`);
      win.document.close();
    });

    // Exportar / Importar Backup JSON
    document.getElementById("btn-export-backup")?.addEventListener("click", async () => {
      const jsonStr = await exportFullHubBackupJson();
      const blob = new Blob([jsonStr], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `backup_loja_itaarte3d_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("Backup JSON completo baixado!");
    });

    document.getElementById("input-import-backup")?.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        await importFullHubBackupJson(JSON.parse(text));
        showToast("Backup restaurado com sucesso! Recarregando dados...");
        await Promise.all([refreshSummary(), renderDashboardTab()]);
      } catch (err) {
        showToast("Falha ao importar JSON: " + err.message);
      } finally {
        e.target.value = "";
      }
    });

    // Botão sincronizar bundle completo com Planilha Google
    document.getElementById("btn-sync-erp-sheets")?.addEventListener("click", async () => {
      const apiUrl = document.getElementById("apiUrlInput")?.value.trim();
      if (!apiUrl) {
        showToast("Informe a URL do Web App da Planilha Google primeiro.");
        return;
      }
      try {
        const full = await getFullErpState();
        const res = await fetch(apiUrl, {
          method: "POST",
          body: JSON.stringify({
            action: "sync_erp_bundle",
            customers: full.customers,
            quotes: full.quotes,
            sales: full.sales,
            jobs: full.jobs,
            suppliers: full.suppliers,
            catalog: full.catalog,
          }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "Erro na sincronização");
        showToast("Clientes, Cotações, Pedidos, Fila 3D e Produtos sincronizados na Planilha Google!");
      } catch (err) {
        showToast("Falha ao sincronizar com Planilha: " + err.message);
      }
    });

    document.getElementById("btn-pull-erp-sheets")?.addEventListener("click", async () => {
      const apiUrl = document.getElementById("apiUrlInput")?.value.trim();
      if (!apiUrl) {
        showToast("Informe a URL do Web App da Planilha Google primeiro.");
        return;
      }
      try {
        const sep = apiUrl.includes("?") ? "&" : "?";
        const res = await fetch(apiUrl + sep + "action=get_erp_bundle");
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || "Erro ao baixar dados");
        await mergeRemoteErpData(data);
        showToast("Dados baixados da Planilha Google para este dispositivo!");
        await Promise.all([refreshSummary(), renderDashboardTab()]);
      } catch (err) {
        showToast("Falha ao puxar da Planilha: " + err.message);
      }
    });
  }

  async function onTabSwitched(tabName) {
    if (tabName === "dashboard") await renderDashboardTab();
    else if (tabName === "orders") await renderOrdersTab();
    else if (tabName === "quotes") await renderQuotesTab();
    else if (tabName === "crm") await renderCrmTab();
    else if (tabName === "catalog") await renderCatalogExtras();
  }

  return {
    bindErpEvents,
    onTabSwitched,
    renderDashboardTab,
    openQuoteWithModel,
  };
}
