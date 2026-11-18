/**
 * Backend Serverless em Planilha Google (Google Apps Script)
 * Sistema: Loja ItaDigital / Ita Arte 3D (GitHub Pages + Robô Local 06h)
 *
 * COMO IMPLANTAR:
 * 1. Execute a função `inicializarBancoPlanilha()` uma vez para criar a Planilha no Google Drive.
 * 2. Clique em "Implantar" > "Nova implantação" > Tipo: "App da Web".
 * 3. Executar como: "Eu (alysontrindadef@gmail.com)" | Quem pode acessar: "Qualquer pessoa".
 * 4. Copie a URL gerada (/exec) e cole no GitHub Pages e no sistema local (/ideias-3d).
 */

const PROP_SHEET_ID = "LOJA_ITADIGITAL_SHEET_ID";

function _getOrCreateSpreadsheet() {
  const props = PropertiesService.getScriptProperties();
  let ssId = props.getProperty(PROP_SHEET_ID);
  let ss = null;
  if (ssId) {
    try {
      ss = SpreadsheetApp.openById(ssId);
    } catch (err) {
      ss = null;
    }
  }
  if (!ss) {
    ss = SpreadsheetApp.create("Banco de Dados — Loja ItaDigital (GitHub Pages & Robô 3D)");
    props.setProperty(PROP_SHEET_ID, ss.getId());
  }
  _garantirAbas(ss);
  return ss;
}

function _garantirAbas(ss) {
  const esquemas = {
    Ideias_Impressao: [
      "id", "termo_ideia", "observacoes", "status",
      "preco_min_brl", "preco_medio_brl", "preco_max_brl", "preco_sugerido_brl",
      "dimensao_mercado_mm", "dimensao_fatiada_mm", "gramas_estimadas",
      "tempo_estimado_min", "modelo_url", "links_json", "resumo_analise",
      "criado_em", "processado_em"
    ],
    Produtos: [
      "id", "sku", "nome", "nicho", "custo_brl", "preco_brl", "estoque", "estoque_min", "atualizado_em"
    ],
    Vendas: [
      "id", "data", "cliente", "canal", "pagamento", "total_brl", "itens_resumo"
    ],
    Config: ["chave", "valor"]
  };

  Object.keys(esquemas).forEach(function(nomeAba) {
    let sh = ss.getSheetByName(nomeAba);
    if (!sh) {
      sh = ss.insertSheet(nomeAba);
    }
    if (sh.getLastRow() === 0) {
      sh.appendRow(esquemas[nomeAba]);
      sh.getRange(1, 1, 1, esquemas[nomeAba].length).setFontWeight("bold");
      sh.setFrozenRows(1);
    }
  });

  const padrao = ss.getSheetByName("Página1") || ss.getSheetByName("Sheet1");
  if (padrao && ss.getSheets().length > 1) {
    try { ss.deleteSheet(padrao); } catch (e) {}
  }
}

function inicializarBancoPlanilha() {
  const ss = _getOrCreateSpreadsheet();
  Logger.log("PLANILHA_URL: " + ss.getUrl());
  Logger.log("PLANILHA_ID: " + ss.getId());
  return ss.getUrl();
}

function _sheetToObjects(sh) {
  const rows = sh.getDataRange().getValues();
  if (rows.length <= 1) return [];
  const headers = rows[0];
  const out = [];
  for (let i = 1; i < rows.length; i++) {
    const obj = {};
    for (let j = 0; j < headers.length; j++) {
      obj[headers[j]] = rows[i][j];
    }
    out.push(obj);
  }
  return out;
}

function _jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  const ss = _getOrCreateSpreadsheet();
  const action = (e && e.parameter && e.parameter.action) || "dashboard";

  if (action === "list_ideias") {
    const ideias = _sheetToObjects(ss.getSheetByName("Ideias_Impressao"));
    return _jsonResponse({ ok: true, sheet_url: ss.getUrl(), ideias: ideias });
  }
  if (action === "list_produtos") {
    const produtos = _sheetToObjects(ss.getSheetByName("Produtos"));
    return _jsonResponse({ ok: true, produtos: produtos });
  }
  if (action === "list_vendas") {
    const vendas = _sheetToObjects(ss.getSheetByName("Vendas"));
    return _jsonResponse({ ok: true, vendas: vendas });
  }

  return _jsonResponse({
    ok: true,
    sheet_url: ss.getUrl(),
    ideias: _sheetToObjects(ss.getSheetByName("Ideias_Impressao")),
    produtos: _sheetToObjects(ss.getSheetByName("Produtos")),
    vendas: _sheetToObjects(ss.getSheetByName("Vendas"))
  });
}

function doPost(e) {
  const ss = _getOrCreateSpreadsheet();
  let body = {};
  try {
    body = JSON.parse((e && e.postData && e.postData.contents) || "{}");
  } catch (err) {
    return _jsonResponse({ ok: false, error: "JSON inválido: " + err });
  }

  const action = body.action || "";

  if (action === "add_ideia") {
    const termo = String(body.termo_ideia || "").trim();
    if (!termo) return _jsonResponse({ ok: false, error: "Informe termo_ideia" });
    const sh = ss.getSheetByName("Ideias_Impressao");
    const nextId = Math.max(1, sh.getLastRow());
    const agora = new Date().toISOString();
    sh.appendRow([
      nextId, termo, String(body.observacoes || ""), "pendente",
      0, 0, 0, 0, "", "", 0, 0, "", "[]", "", agora, ""
    ]);
    return _jsonResponse({ ok: true, id: nextId, termo_ideia: termo });
  }

  if (action === "sync_ideias") {
    const lista = Array.isArray(body.ideias) ? body.ideias : [];
    const sh = ss.getSheetByName("Ideias_Impressao");
    const headers = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
    if (sh.getLastRow() > 1) {
      sh.getRange(2, 1, sh.getLastRow() - 1, headers.length).clearContent();
    }
    const rows = lista.map(function(it) {
      return [
        it.id || "",
        it.termo_ideia || "",
        it.observacoes || "",
        it.status || "pendente",
        Number(it.preco_min_centavos || 0) / 100,
        Number(it.preco_medio_centavos || 0) / 100,
        Number(it.preco_max_centavos || 0) / 100,
        Number(it.preco_sugerido_centavos || 0) / 100,
        it.dimensao_mercado_mm || "",
        it.dimensao_fatiada_mm || "",
        Number(it.gramas_estimadas || 0),
        Number(it.tempo_estimado_min || 0),
        it.modelo_url || "",
        JSON.stringify(it.links || []),
        it.resumo_analise || "",
        it.criado_em || "",
        it.processado_em || ""
      ];
    });
    if (rows.length > 0) {
      sh.getRange(2, 1, rows.length, headers.length).setValues(rows);
    }
    return _jsonResponse({ ok: true, sincronizadas: rows.length });
  }

  if (action === "add_produto") {
    const sh = ss.getSheetByName("Produtos");
    const nextId = Math.max(1, sh.getLastRow());
    sh.appendRow([
      nextId,
      String(body.sku || ("SKU-" + nextId)),
      String(body.nome || ""),
      String(body.nicho || "Geral"),
      Number(body.custo_brl || 0),
      Number(body.preco_brl || 0),
      Number(body.estoque || 0),
      Number(body.estoque_min || 2),
      new Date().toISOString()
    ]);
    return _jsonResponse({ ok: true, id: nextId });
  }

  if (action === "add_venda") {
    const sh = ss.getSheetByName("Vendas");
    const nextId = Math.max(1, sh.getLastRow());
    sh.appendRow([
      nextId,
      new Date().toISOString(),
      String(body.cliente || "Consumidor Final"),
      String(body.canal || "loja"),
      String(body.pagamento || "pix"),
      Number(body.total_brl || 0),
      String(body.itens_resumo || "")
    ]);
    return _jsonResponse({ ok: true, id: nextId });
  }

  return _jsonResponse({ ok: false, error: "Ação não suportada: " + action });
}
