const DEFAULT_API_URL = "https://script.google.com/macros/s/AKfycbzj7BsmnH8WLBWh1z6iW5yhjDx5WKXVzLnEDoemlVU_i1T1hRuExBz5hyq6BO5QwXWUVw/exec";
const STORAGE_KEY = "loja_itadigital_sheets_api_url";

function getApiUrl() {
  const params = new URLSearchParams(window.location.search);
  const paramApi = params.get("api");
  if (paramApi) {
    localStorage.setItem(STORAGE_KEY, paramApi.trim());
    return paramApi.trim();
  }
  return (localStorage.getItem(STORAGE_KEY) || DEFAULT_API_URL).trim();
}

function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.style.display = "block";
  setTimeout(() => { el.style.display = "none"; }, 3500);
}

function fmtBrl(v) {
  const num = Number(v || 0);
  return num.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function escapeHtml(txt) {
  return String(txt || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
  });
});

async function carregarTudo() {
  const apiUrl = getApiUrl();
  const pill = document.getElementById("connStatus");
  document.getElementById("apiUrlInput").value = apiUrl;

  if (!apiUrl) {
    pill.textContent = "Planilha Google não conectada (configure na aba ⚙️)";
    pill.className = "status-pill warn";
    renderIdeias([]);
    return;
  }

  try {
    const sep = apiUrl.includes("?") ? "&" : "?";
    const res = await fetch(apiUrl + sep + "action=dashboard");
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Erro desconhecido");

    pill.textContent = "Conectado à Planilha Google";
    pill.className = "status-pill ok";

    if (data.sheet_url) {
      document.getElementById("linkPlanilhaWrap").innerHTML =
        `Planilha ativa: <a href="${escapeHtml(data.sheet_url)}" target="_blank" style="color:#38bdf8">${escapeHtml(data.sheet_url)}</a>`;
    }

    renderIdeias(data.ideias || []);
    renderProdutos(data.produtos || []);
    renderVendas(data.vendas || []);
  } catch (err) {
    pill.textContent = "Erro ao conectar à Planilha";
    pill.className = "status-pill warn";
    showToast("Falha ao buscar dados: " + err.message);
  }
}

function renderIdeias(ideias) {
  document.getElementById("qtdIdeias").textContent = ideias.length;
  const wrap = document.getElementById("listaIdeias");
  if (!ideias.length) {
    wrap.innerHTML = `<p class="muted">Nenhuma ideia registrada ainda. Digite uma acima!</p>`;
    return;
  }

  const ordered = [...ideias].reverse();
  wrap.innerHTML = ordered.map(it => {
    let links = [];
    try { links = typeof it.links_json === "string" ? JSON.parse(it.links_json || "[]") : (it.links_json || []); } catch {}
    const isDone = String(it.status).toLowerCase() === "concluida";
    const linksHtml = links.map(lk =>
      `<li><b>${escapeHtml(lk.fonte)}:</b> <a href="${escapeHtml(lk.url)}" target="_blank">${escapeHtml(lk.titulo)}</a>${lk.preco_brl ? ` — <b>${fmtBrl(lk.preco_brl)}</b>` : ""}</li>`
    ).join("");

    return `
      <div class="idea-card">
        <div class="idea-top">
          <strong>#${escapeHtml(it.id)} — ${escapeHtml(it.termo_ideia)}</strong>
          <span class="badge ${isDone ? "done" : ""}">${escapeHtml(String(it.status || "pendente").toUpperCase())}</span>
        </div>
        ${it.observacoes ? `<div class="muted" style="margin:4px 0 0;">Obs.: ${escapeHtml(it.observacoes)}</div>` : ""}
        ${isDone ? `
          <div class="idea-meta">
            <div><b>Marketplaces (Médio):</b> ${it.preco_medio_brl > 0 ? fmtBrl(it.preco_medio_brl) : "Ver links"}<br><b>Sugerido Loja:</b> ${fmtBrl(it.preco_sugerido_brl)}</div>
            <div><b>Padrão Mercado:</b> ${escapeHtml(it.dimensao_mercado_mm)}<br><b>Fatiado:</b> ${escapeHtml(it.dimensao_fatiada_mm)} (${escapeHtml(it.gramas_estimadas)}g / ~${escapeHtml(it.tempo_estimado_min)} min)</div>
          </div>
          ${it.resumo_analise ? `<p class="muted" style="margin:8px 0 0;">${escapeHtml(it.resumo_analise)}</p>` : ""}
          <div class="idea-links">
            ${it.modelo_url ? `<div><b>Modelo 3D:</b> <a href="${escapeHtml(it.modelo_url)}" target="_blank">${escapeHtml(it.modelo_url)}</a></div>` : ""}
            ${linksHtml ? `<ul style="margin:4px 0 0 18px; padding:0;">${linksHtml}</ul>` : ""}
          </div>
        ` : `<div class="muted" style="margin:6px 0 0;">Aguardando processamento do robô local (06h).</div>`}
      </div>
    `;
  }).join("");
}

function renderProdutos(produtos) {
  document.getElementById("qtdProdutos").textContent = produtos.length;
  document.getElementById("tbodyProdutos").innerHTML = produtos.map(p => `
    <tr>
      <td>${escapeHtml(p.sku)}</td>
      <td><b>${escapeHtml(p.nome)}</b></td>
      <td>${escapeHtml(p.nicho)}</td>
      <td>${fmtBrl(p.custo_brl)}</td>
      <td><b>${fmtBrl(p.preco_brl)}</b></td>
      <td>${escapeHtml(p.estoque)}</td>
    </tr>
  `).join("");
}

function renderVendas(vendas) {
  document.getElementById("tbodyVendas").innerHTML = [...vendas].reverse().map(v => `
    <tr>
      <td>${escapeHtml(String(v.data || "").slice(0, 10))}</td>
      <td>${escapeHtml(v.cliente)}</td>
      <td>${escapeHtml(v.itens_resumo)}</td>
      <td>${escapeHtml(v.pagamento)}</td>
      <td>${escapeHtml(v.canal)}</td>
      <td><b>${fmtBrl(v.total_brl)}</b></td>
    </tr>
  `).join("");
}

async function postAction(payload) {
  const apiUrl = getApiUrl();
  if (!apiUrl) {
    showToast("Configure a URL da Planilha Google na aba ⚙️ primeiro.");
    return null;
  }
  const res = await fetch(apiUrl, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return res.json();
}

document.getElementById("formIdeia").addEventListener("submit", async (e) => {
  e.preventDefault();
  const termo = document.getElementById("termoIdeia").value.trim();
  const obs = document.getElementById("obsIdeia").value.trim();
  if (!termo) return;
  const r = await postAction({ action: "add_ideia", termo_ideia: termo, observacoes: obs });
  if (r && r.ok) {
    document.getElementById("termoIdeia").value = "";
    document.getElementById("obsIdeia").value = "";
    showToast("Ideia salva na Planilha Google!");
    carregarTudo();
  }
});

document.getElementById("formProduto").addEventListener("submit", async (e) => {
  e.preventDefault();
  const r = await postAction({
    action: "add_produto",
    nome: document.getElementById("prodNome").value,
    sku: document.getElementById("prodSku").value,
    nicho: document.getElementById("prodNicho").value || "Geral",
    custo_brl: document.getElementById("prodCusto").value || 0,
    preco_brl: document.getElementById("prodPreco").value || 0,
    estoque: document.getElementById("prodEstoque").value || 0,
  });
  if (r && r.ok) {
    e.target.reset();
    showToast("Produto salvo na Planilha!");
    carregarTudo();
  }
});

document.getElementById("formVenda").addEventListener("submit", async (e) => {
  e.preventDefault();
  const r = await postAction({
    action: "add_venda",
    cliente: document.getElementById("vendaCliente").value,
    itens_resumo: document.getElementById("vendaItens").value,
    pagamento: document.getElementById("vendaPagamento").value,
    canal: document.getElementById("vendaCanal").value,
    total_brl: document.getElementById("vendaTotal").value,
  });
  if (r && r.ok) {
    e.target.reset();
    showToast("Venda registrada na Planilha!");
    carregarTudo();
  }
});

document.getElementById("formConfig").addEventListener("submit", (e) => {
  e.preventDefault();
  const val = document.getElementById("apiUrlInput").value.trim();
  localStorage.setItem(STORAGE_KEY, val);
  showToast("URL da Planilha salva!");
  carregarTudo();
});

document.getElementById("btnRecarregar").addEventListener("click", carregarTudo);
carregarTudo();
