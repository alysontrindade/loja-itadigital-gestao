/**
 * Backend Serverless em Planilha Google (Google Apps Script)
 * Sistema Unificado: Loja ItaDigital & Ita Arte 3D (GitHub Pages + Robô Local 06h)
 *
 * COMO IMPLANTAR:
 * 1. Execute a função `inicializarBancoPlanilha()` uma vez para criar/atualizar a Planilha no Google Drive.
 * 2. Clique em "Implantar" > "Gerenciar implantações" (ou "Nova implantação") > Tipo: "App da Web".
 * 3. Executar como: "Eu (alysontrindadef@gmail.com)" | Quem pode acessar: "Qualquer pessoa".
 * 4. Copie a URL gerada (/exec) e cole na aba "Ideias 06h & Sincronização" do GitHub Pages.
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
    ss = SpreadsheetApp.create("Banco de Dados — Loja ItaDigital & Hub 3D (GitHub Pages)");
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
    Clientes: [
      "id", "name", "whatsapp", "email", "city", "birthday", "notes", "created_at", "updated_at"
    ],
    Cotacoes_3D: [
      "id", "code", "customer_name", "customer_whatsapp", "title", "quantity",
      "grams", "time_min", "unit_cost_brl", "unit_price_brl", "total_price_brl",
      "estimated_profit_brl", "lead_days", "status", "notes", "created_at"
    ],
    Pedidos_Vendas: [
      "id", "item_name", "customer_name", "customer_whatsapp", "channel",
      "quantity", "unit_price_brl", "discount_brl", "freight_brl", "total_price_brl",
      "payment_status", "fulfillment_status", "notes", "created_at"
    ],
    Fila_3D: [
      "id", "title", "status", "priority", "target_type", "customer_name",
      "printer_name", "spool_label", "rubric_name", "quantity",
      "estimated_grams", "estimated_time_min", "slicing_notes", "notes", "updated_at"
    ],
    Fornecedores: [
      "id", "name", "type", "contact", "whatsapp", "site", "city_uf",
      "lead_days", "min_order_brl", "notes"
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
  if (!sh) return [];
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

function _replaceSheetRows(ss, sheetName, list, rowMapper) {
  const sh = ss.getSheetByName(sheetName);
  if (!sh) return 0;
  const cols = sh.getLastColumn();
  if (sh.getLastRow() > 1) {
    sh.getRange(2, 1, sh.getLastRow() - 1, cols).clearContent();
  }
  const rows = (Array.isArray(list) ? list : []).map(rowMapper);
  if (rows.length > 0) {
    sh.getRange(2, 1, rows.length, rows[0].length).setValues(rows);
  }
  return rows.length;
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
    return _jsonResponse({ ok: true, sheet_url: ss.getUrl(), ideias: _sheetToObjects(ss.getSheetByName("Ideias_Impressao")) });
  }
  if (action === "list_produtos") {
    return _jsonResponse({ ok: true, produtos: _sheetToObjects(ss.getSheetByName("Produtos")) });
  }
  if (action === "list_vendas") {
    return _jsonResponse({ ok: true, vendas: _sheetToObjects(ss.getSheetByName("Vendas")) });
  }
  if (action === "get_erp_bundle") {
    return _jsonResponse({
      ok: true,
      sheet_url: ss.getUrl(),
      customers: _sheetToObjects(ss.getSheetByName("Clientes")),
      quotes: _sheetToObjects(ss.getSheetByName("Cotacoes_3D")),
      sales: _sheetToObjects(ss.getSheetByName("Pedidos_Vendas")),
      jobs: _sheetToObjects(ss.getSheetByName("Fila_3D")),
      suppliers: _sheetToObjects(ss.getSheetByName("Fornecedores")),
      ideias: _sheetToObjects(ss.getSheetByName("Ideias_Impressao")),
      produtos: _sheetToObjects(ss.getSheetByName("Produtos"))
    });
  }

  return _jsonResponse({
    ok: true,
    sheet_url: ss.getUrl(),
    ideias: _sheetToObjects(ss.getSheetByName("Ideias_Impressao")),
    produtos: _sheetToObjects(ss.getSheetByName("Produtos")),
    vendas: _sheetToObjects(ss.getSheetByName("Vendas")),
    customers: _sheetToObjects(ss.getSheetByName("Clientes")),
    quotes: _sheetToObjects(ss.getSheetByName("Cotacoes_3D")),
    sales: _sheetToObjects(ss.getSheetByName("Pedidos_Vendas")),
    jobs: _sheetToObjects(ss.getSheetByName("Fila_3D")),
    suppliers: _sheetToObjects(ss.getSheetByName("Fornecedores"))
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
    const cnt = _replaceSheetRows(ss, "Ideias_Impressao", lista, function(it) {
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
    return _jsonResponse({ ok: true, sincronizadas: cnt });
  }

  if (action === "sync_erp_bundle") {
    const resumo = {};
    if (Array.isArray(body.customers)) {
      resumo.customers = _replaceSheetRows(ss, "Clientes", body.customers, function(c) {
        return [c.id || "", c.name || "", c.whatsapp || "", c.email || "", c.city || "", c.birthday || "", c.notes || "", c.created_at || "", c.updated_at || ""];
      });
    }
    if (Array.isArray(body.quotes)) {
      resumo.quotes = _replaceSheetRows(ss, "Cotacoes_3D", body.quotes, function(q) {
        return [q.id || "", q.code || "", q.customer_name || "", q.customer_whatsapp || "", q.title || "", Number(q.quantity || 1), Number(q.grams || 0), Number(q.time_min || 0), Number(q.unit_cost_brl || 0), Number(q.unit_price_brl || 0), Number(q.total_price_brl || 0), Number(q.estimated_profit_brl || 0), Number(q.lead_days || 1), q.status || "", q.notes || "", q.created_at || ""];
      });
    }
    if (Array.isArray(body.sales)) {
      resumo.sales = _replaceSheetRows(ss, "Pedidos_Vendas", body.sales, function(s) {
        return [s.id || "", s.item_name || "", s.customer_name || "", s.customer_whatsapp || "", s.channel || "", Number(s.quantity || 1), Number(s.unit_price_brl || 0), Number(s.discount_brl || 0), Number(s.freight_brl || 0), Number(s.total_price_brl || 0), s.payment_status || "", s.fulfillment_status || "", s.notes || "", s.created_at || ""];
      });
    }
    if (Array.isArray(body.jobs)) {
      resumo.jobs = _replaceSheetRows(ss, "Fila_3D", body.jobs, function(j) {
        return [j.id || "", j.title || "", j.status || "", j.priority || "", j.target_type || "", j.customer_name || "", j.printer_name || "", j.spool_label || "", j.rubric_name || "", Number(j.quantity || 1), Number(j.estimated_grams || 0), Number(j.estimated_time_min || 0), j.slicing_notes || "", j.notes || "", j.updated_at || ""];
      });
    }
    if (Array.isArray(body.suppliers)) {
      resumo.suppliers = _replaceSheetRows(ss, "Fornecedores", body.suppliers, function(f) {
        return [f.id || "", f.name || "", f.type || "", f.contact || "", f.whatsapp || "", f.site || "", f.city_uf || "", Number(f.lead_days || 0), Number(f.min_order_brl || 0), f.notes || ""];
      });
    }
    if (Array.isArray(body.catalog)) {
      resumo.catalog = _replaceSheetRows(ss, "Produtos", body.catalog, function(p) {
        return [p.id || "", p.code || "", p.name || "", p.category || "", Number(p.unit_cost_brl || 0), Number(p.sale_price_brl || 0), Number(p.stock_qty || 0), Number(p.min_stock_alert || 1), p.updated_at || ""];
      });
    }
    return _jsonResponse({ ok: true, sheet_url: ss.getUrl(), synced: resumo });
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
