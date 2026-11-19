import { escapeHtml, formatBrl, showToast } from "./utils.js";

const DEFAULT_API_URL =
  "https://script.google.com/macros/s/AKfycbzj7BsmnH8WLBWh1z6iW5yhjDx5WKXVzLnEDoemlVU_i1T1hRuExBz5hyq6BO5QwXWUVw/exec";
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

function renderIdeias(ideias) {
  const qtdEl = document.getElementById("qtdIdeias");
  const wrap = document.getElementById("listaIdeias");
  if (!qtdEl || !wrap) return;
  qtdEl.textContent = String(ideias.length);
  if (!ideias.length) {
    wrap.innerHTML = `<p class="brand-sub">Nenhuma ideia registrada ainda na Planilha Google.</p>`;
    return;
  }

  const ordered = [...ideias].reverse();
  wrap.innerHTML = ordered
    .map((it) => {
      let links = [];
      try {
        links = typeof it.links_json === "string" ? JSON.parse(it.links_json || "[]") : it.links_json || [];
      } catch {
        links = [];
      }
      const isDone = String(it.status).toLowerCase() === "concluida";
      const linksHtml = links
        .map(
          (lk) =>
            `<li><b>${escapeHtml(lk.fonte)}:</b> <a href="${escapeHtml(lk.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(
              lk.titulo
            )}</a>${lk.preco_brl ? ` — <b>${formatBrl(lk.preco_brl)}</b>` : ""}</li>`
        )
        .join("");

      return `
      <div class="idea-card">
        <div class="idea-top">
          <strong>#${escapeHtml(it.id)} — ${escapeHtml(it.termo_ideia)}</strong>
          <span class="badge ${isDone ? "badge-success" : "badge-info"}">${escapeHtml(
        String(it.status || "pendente").toUpperCase()
      )}</span>
        </div>
        ${it.observacoes ? `<div class="brand-sub" style="margin:4px 0 0;">Obs.: ${escapeHtml(it.observacoes)}</div>` : ""}
        ${
          isDone
            ? `
          <div class="idea-meta">
            <div><b>Marketplaces (Médio):</b> ${
              it.preco_medio_brl > 0 ? formatBrl(it.preco_medio_brl) : "Ver links"
            }<br><b>Sugerido Loja:</b> ${formatBrl(it.preco_sugerido_brl)}</div>
            <div><b>Padrão Mercado:</b> ${escapeHtml(it.dimensao_mercado_mm)}<br><b>Fatiado:</b> ${escapeHtml(
                it.dimensao_fatiada_mm
              )} (${escapeHtml(it.gramas_estimadas)}g / ~${escapeHtml(it.tempo_estimado_min)} min)</div>
          </div>
          ${it.resumo_analise ? `<p class="brand-sub" style="margin:8px 0 0;">${escapeHtml(it.resumo_analise)}</p>` : ""}
          <div class="idea-links">
            ${
              it.modelo_url
                ? `<div><b>Modelo 3D:</b> <a href="${escapeHtml(it.modelo_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(
                    it.modelo_url
                  )}</a></div>`
                : ""
            }
            ${linksHtml ? `<ul style="margin:4px 0 0 18px; padding:0;">${linksHtml}</ul>` : ""}
          </div>
        `
            : `<div class="brand-sub" style="margin:6px 0 0;">Aguardando processamento do robô local (06h).</div>`
        }
      </div>
    `;
    })
    .join("");
}

async function carregarPlanilha() {
  const apiUrl = getApiUrl();
  const pill = document.getElementById("connStatus");
  const input = document.getElementById("apiUrlInput");
  if (input) input.value = apiUrl;
  if (!pill) return;

  if (!apiUrl) {
    pill.textContent = "Planilha Google não configurada";
    pill.className = "sheets-status-pill warn";
    renderIdeias([]);
    return;
  }

  try {
    const sep = apiUrl.includes("?") ? "&" : "?";
    const res = await fetch(apiUrl + sep + "action=dashboard");
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Erro desconhecido");

    pill.textContent = "Planilha Google Conectada";
    pill.className = "sheets-status-pill ok";

    const linkWrap = document.getElementById("linkPlanilhaWrap");
    if (data.sheet_url && linkWrap) {
      linkWrap.innerHTML = `Planilha ativa: <a href="${escapeHtml(
        data.sheet_url
      )}" target="_blank" rel="noopener noreferrer" style="color:var(--cyan)">${escapeHtml(data.sheet_url)}</a>`;
    }
    renderIdeias(data.ideias || []);
  } catch (err) {
    pill.textContent = "Planilha offline";
    pill.className = "sheets-status-pill warn";
  }
}

async function postSheetAction(payload) {
  const apiUrl = getApiUrl();
  if (!apiUrl) {
    showToast("Configure a URL da Planilha Google primeiro.");
    return null;
  }
  const res = await fetch(apiUrl, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return res.json();
}

function bindSheetsBridge() {
  document.getElementById("formIdeia")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const termo = document.getElementById("termoIdeia").value.trim();
    const obs = document.getElementById("obsIdeia").value.trim();
    if (!termo) return;
    try {
      const r = await postSheetAction({ action: "add_ideia", termo_ideia: termo, observacoes: obs });
      if (r && r.ok) {
        document.getElementById("termoIdeia").value = "";
        document.getElementById("obsIdeia").value = "";
        showToast("Ideia salva na Planilha Google!");
        await carregarPlanilha();
      }
    } catch (err) {
      showToast("Falha ao enviar para Planilha Google: " + err.message);
    }
  });

  document.getElementById("formConfigSheets")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const val = document.getElementById("apiUrlInput").value.trim();
    localStorage.setItem(STORAGE_KEY, val);
    showToast("URL da Planilha salva!");
    carregarPlanilha();
  });

  document.getElementById("btnRecarregarSheets")?.addEventListener("click", carregarPlanilha);
  carregarPlanilha();
}

bindSheetsBridge();
