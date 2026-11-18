(function () {
  const sidebar = document.getElementById("sidebar");
  const menuBtn = document.getElementById("menu-btn");
  const scrim = document.getElementById("sidebar-scrim");

  function setDrawer(open) {
    if (!sidebar) return;
    sidebar.classList.toggle("open", open);
    if (scrim) scrim.classList.toggle("open", open);
    if (menuBtn) menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  if (menuBtn) {
    menuBtn.addEventListener("click", function () {
      setDrawer(!sidebar.classList.contains("open"));
    });
  }
  if (scrim) {
    scrim.addEventListener("click", function () {
      setDrawer(false);
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setDrawer(false);
  });

  // Preview imediato do tema nas opções de Configurações
  document.querySelectorAll('input[name="tema"][type="radio"]').forEach(function (radio) {
    radio.addEventListener("change", function () {
      document.documentElement.setAttribute("data-tema", radio.value);
    });
  });

  // Envia CSRF token em chamadas HTMX automaticamente
  document.body.addEventListener("htmx:configRequest", function (event) {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) {
      event.detail.headers["X-CSRF-Token"] = meta.getAttribute("content");
    }
  });

  // Auto-esconde toasts após 5s
  document.querySelectorAll(".toasts .toast").forEach(function (toast) {
    setTimeout(function () {
      toast.remove();
    }, 5000);
  });

  // Cálculo de margem ao vivo no cadastro/edição de produto
  function parseBRL(str) {
    if (!str) return 0;
    const limpo = String(str).replace(/R\$/g, "").replace(/\s+/g, "").replace(/\./g, "").replace(",", ".");
    const num = parseFloat(limpo);
    return Number.isFinite(num) ? num : 0;
  }

  function formatBRL(val) {
    return val.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  const custoInput = document.getElementById("custo");
  const precoInput = document.getElementById("preco");
  const margemBox = document.getElementById("margin-live-box");
  if (custoInput && precoInput && margemBox) {
    const lucroEl = document.getElementById("lucro-vivo");
    const pctEl = document.getElementById("margem-viva");
    const badgeEl = document.getElementById("margem-status-badge");
    const alvo = parseFloat(margemBox.dataset.margemAlvo || "45");

    function atualizarMargem() {
      const custo = parseBRL(custoInput.value);
      const preco = parseBRL(precoInput.value);
      const lucro = preco - custo;
      const margem = preco > 0 ? (lucro / preco) * 100 : 0;
      if (lucroEl) lucroEl.textContent = formatBRL(lucro);
      if (pctEl) pctEl.textContent = margem.toFixed(1).replace(".", ",") + "%";
      if (badgeEl) {
        badgeEl.className = "badge " + (margem >= alvo ? "badge-ok" : margem > 0 ? "badge-warn" : "badge-danger");
        badgeEl.textContent = margem >= alvo
          ? "Acima da meta (" + alvo + "%)"
          : margem > 0
            ? "Abaixo da meta (" + alvo + "%)"
            : "Sem lucro";
      }
    }
    custoInput.addEventListener("input", atualizarMargem);
    precoInput.addEventListener("input", atualizarMargem);
    atualizarMargem();
  }

  // Mini-filtro rápido de nichos dentro do formulário de produto
  const filtroNichosForm = document.getElementById("filtro-nichos-form");
  if (filtroNichosForm) {
    filtroNichosForm.addEventListener("input", function () {
      const q = filtroNichosForm.value.trim().toLowerCase();
      document.querySelectorAll("[data-nicho-label]").forEach(function (el) {
        const txt = (el.dataset.nichoLabel || "").toLowerCase();
        el.style.display = !q || txt.includes(q) ? "" : "none";
      });
    });
  }

  // Mini-filtro rápido de fornecedores dentro do formulário de produto
  const filtroFornForm = document.getElementById("filtro-forn-form");
  const selectForn = document.getElementById("fornecedor_id");
  if (filtroFornForm && selectForn) {
    filtroFornForm.addEventListener("input", function () {
      const q = filtroFornForm.value.trim().toLowerCase();
      Array.from(selectForn.options).forEach(function (opt) {
        if (!opt.value) {
          opt.hidden = false;
          return;
        }
        opt.hidden = Boolean(q) && !opt.textContent.toLowerCase().includes(q);
      });
    });
  }

  // Mostra contagem de fotos selecionadas no dropzone antes do envio
  const inputImagens = document.getElementById("imagens");
  const infoImagens = document.getElementById("imagens-selecionadas");
  if (inputImagens && infoImagens) {
    inputImagens.addEventListener("change", function () {
      const qtd = inputImagens.files ? inputImagens.files.length : 0;
      infoImagens.textContent = qtd > 0
        ? qtd + " arquivo(s) selecionado(s) pronto(s) para envio."
        : "Formatos aceitos: JPG, PNG ou WEBP (até 10 MB cada).";
    });
  }

  // Atalhos globais de teclado: F2 abre ou foca o PDV; F9 finaliza venda no PDV
  document.addEventListener("keydown", function (e) {
    if (e.key === "F2") {
      e.preventDefault();
      const pdvBusca = document.getElementById("pdv-busca");
      if (pdvBusca) {
        pdvBusca.focus();
        pdvBusca.select();
      } else {
        window.location.href = "/pdv";
      }
    } else if (e.key === "F9") {
      const pdvForm = document.getElementById("pdv-form");
      if (pdvForm) {
        e.preventDefault();
        pdvForm.requestSubmit();
      }
    }
  });

  // Linhas dinâmicas e simulação de margem para Kits
  const kitContainer = document.getElementById("kit-itens-container");
  const kitTpl = document.getElementById("tpl-kit-row");
  const btnAddKit = document.getElementById("btn-add-kit-item");
  if (kitContainer && kitTpl && btnAddKit) {
    function recalcularKit() {
      let custoCentavos = 0;
      let somaAvulsaCentavos = 0;
      kitContainer.querySelectorAll(".dyn-row").forEach(function (row) {
        const sel = row.querySelector(".js-kit-prod");
        const qtdEl = row.querySelector(".js-kit-qtd");
        if (!sel || !qtdEl) return;
        const opt = sel.options[sel.selectedIndex];
        const custoU = parseInt((opt && opt.dataset.custo) || "0", 10) || 0;
        const precoU = parseInt((opt && opt.dataset.preco) || "0", 10) || 0;
        const qtd = Math.max(0, parseInt(qtdEl.value || "0", 10) || 0);
        custoCentavos += custoU * qtd;
        somaAvulsaCentavos += precoU * qtd;
      });
      const precoKitCentavos = Math.round(parseBRL((document.getElementById("kit-preco") || {}).value) * 100);
      const lucroCentavos = precoKitCentavos - custoCentavos;
      const margem = precoKitCentavos > 0 ? (lucroCentavos / precoKitCentavos) * 100 : 0;

      const elCusto = document.getElementById("kit-custo-total");
      const elAvulsa = document.getElementById("kit-soma-avulsa");
      const elLucro = document.getElementById("kit-lucro");
      const elMargem = document.getElementById("kit-margem");
      if (elCusto) elCusto.textContent = formatBRL(custoCentavos / 100);
      if (elAvulsa) elAvulsa.textContent = formatBRL(somaAvulsaCentavos / 100);
      if (elLucro) elLucro.textContent = formatBRL(lucroCentavos / 100);
      if (elMargem) elMargem.textContent = margem.toFixed(1).replace(".", ",") + "%";
    }

    btnAddKit.addEventListener("click", function () {
      kitContainer.appendChild(kitTpl.content.cloneNode(true));
      recalcularKit();
    });
    kitContainer.addEventListener("click", function (e) {
      if (e.target.classList.contains("js-remove-row") && kitContainer.querySelectorAll(".dyn-row").length > 1) {
        e.target.closest(".dyn-row").remove();
        recalcularKit();
      }
    });
    kitContainer.addEventListener("change", recalcularKit);
    kitContainer.addEventListener("input", recalcularKit);
    const precoKitEl = document.getElementById("kit-preco");
    if (precoKitEl) precoKitEl.addEventListener("input", recalcularKit);
    recalcularKit();
  }

  // Linhas dinâmicas e soma de custos para Compras
  const compraContainer = document.getElementById("compra-itens-container");
  const compraTpl = document.getElementById("tpl-compra-row");
  const btnAddCompra = document.getElementById("btn-add-compra-item");
  if (compraContainer && compraTpl && btnAddCompra) {
    function recalcularCompra() {
      let bruto = 0;
      compraContainer.querySelectorAll(".dyn-row").forEach(function (row) {
        const qtd = Math.max(0, parseInt((row.querySelector(".js-compra-qtd") || {}).value || "0", 10) || 0);
        const custo = parseBRL((row.querySelector(".js-compra-custo") || {}).value || "0");
        bruto += qtd * custo;
      });
      const frete = parseBRL((document.getElementById("compra-frete") || {}).value);
      const impostos = parseBRL((document.getElementById("compra-impostos") || {}).value);
      const outros = parseBRL((document.getElementById("compra-outros") || {}).value);
      const extras = frete + impostos + outros;

      const elBruto = document.getElementById("compra-bruto");
      const elExtras = document.getElementById("compra-extras");
      const elTotal = document.getElementById("compra-total");
      if (elBruto) elBruto.textContent = formatBRL(bruto);
      if (elExtras) elExtras.textContent = formatBRL(extras);
      if (elTotal) elTotal.textContent = formatBRL(bruto + extras);
    }

    btnAddCompra.addEventListener("click", function () {
      compraContainer.appendChild(compraTpl.content.cloneNode(true));
      recalcularCompra();
    });
    compraContainer.addEventListener("click", function (e) {
      if (e.target.classList.contains("js-remove-row") && compraContainer.querySelectorAll(".dyn-row").length > 1) {
        e.target.closest(".dyn-row").remove();
        recalcularCompra();
      }
    });
    compraContainer.addEventListener("change", function (e) {
      if (e.target.classList.contains("js-compra-prod")) {
        const row = e.target.closest(".dyn-row");
        const custoInput = row && row.querySelector(".js-compra-custo");
        const opt = e.target.options[e.target.selectedIndex];
        if (custoInput && opt && (!custoInput.value || custoInput.value === "0,00")) {
          custoInput.value = opt.dataset.custo || "0,00";
        }
      }
      recalcularCompra();
    });
    document.querySelectorAll(".js-compra-calc").forEach(function (el) {
      el.addEventListener("input", recalcularCompra);
    });
    compraContainer.addEventListener("input", recalcularCompra);
    recalcularCompra();
  }

  // PDV / Frente de Caixa (carrinho, código de barras com Enter, pagamento e troco)
  const pdvForm = document.getElementById("pdv-form");
  if (pdvForm) {
    const cart = [];
    const cartItemsEl = document.getElementById("pdv-cart-items");
    const itensJsonEl = document.getElementById("pdv-itens-json");
    const subtotalEl = document.getElementById("pdv-subtotal");
    const totalEl = document.getElementById("pdv-total");
    const descontoEl = document.getElementById("pdv-desconto");
    const formaEl = document.getElementById("pdv-forma");
    const trocoBox = document.getElementById("pdv-troco-box");
    const recebidoEl = document.getElementById("pdv-recebido");
    const trocoValorEl = document.getElementById("pdv-troco-valor");
    const pdvBuscaEl = document.getElementById("pdv-busca");
    const pdvNichoEl = document.getElementById("pdv-nicho-id");

    function atualizarTroco(totalCentavos) {
      if (!trocoBox || !recebidoEl || !trocoValorEl) return;
      const recebidoCentavos = Math.round(parseBRL(recebidoEl.value) * 100);
      const troco = Math.max(0, recebidoCentavos - totalCentavos);
      trocoValorEl.textContent = "Troco: " + formatBRL(troco / 100);
    }

    function renderizarCarrinho() {
      if (!cart.length) {
        cartItemsEl.innerHTML = '<div class="empty" style="padding:20px 10px;"><p style="margin:0; font-size:13px;">Nenhum item adicionado ainda.</p></div>';
      } else {
        const esc = function (txt) {
          return String(txt || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
        };
        cartItemsEl.innerHTML = cart.map(function (item, idx) {
          const lineTotal = (item.preco_centavos * item.quantidade) / 100;
          const nomeSeguro = esc(item.nome);
          return (
            '<div class="cart-item">' +
              '<div class="cart-item-info">' +
                '<div class="cart-item-nome" title="' + nomeSeguro + '">' + nomeSeguro + '</div>' +
                '<div class="cart-item-sub">' + formatBRL(item.preco_centavos / 100) + ' × ' + item.quantidade + ' = <strong>' + formatBRL(lineTotal) + '</strong></div>' +
              '</div>' +
              '<div class="qty">' +
                '<button class="btn btn-ghost btn-xs js-cart-dec" data-idx="' + idx + '" type="button" aria-label="Diminuir">-</button>' +
                '<span class="num">' + item.quantidade + '</span>' +
                '<button class="btn btn-ghost btn-xs js-cart-inc" data-idx="' + idx + '" type="button" aria-label="Aumentar">+</button>' +
                '<button class="btn btn-ghost btn-xs js-cart-del" data-idx="' + idx + '" type="button" aria-label="Remover">×</button>' +
              '</div>' +
            '</div>'
          );
        }).join("");
      }

      const subtotalCentavos = cart.reduce(function (acc, it) {
        return acc + it.preco_centavos * it.quantidade;
      }, 0);
      const descontoCentavos = Math.max(0, Math.round(parseBRL(descontoEl.value) * 100));
      const totalCentavos = Math.max(0, subtotalCentavos - descontoCentavos);

      subtotalEl.textContent = formatBRL(subtotalCentavos / 100);
      totalEl.textContent = formatBRL(totalCentavos / 100);
      itensJsonEl.value = JSON.stringify(
        cart.map(function (it) {
          return { tipo: it.tipo, id: it.id, quantidade: it.quantidade };
        })
      );
      atualizarTroco(totalCentavos);
    }

    function adicionarAoCarrinho(item) {
      if (!item || item.estoque_disponivel <= 0) return;
      const existente = cart.find(function (c) {
        return c.tipo === item.tipo && c.id === item.id;
      });
      if (existente) {
        if (existente.quantidade < item.estoque_disponivel) {
          existente.quantidade += 1;
        }
      } else {
        cart.push({
          tipo: item.tipo,
          id: item.id,
          nome: item.nome,
          preco_centavos: item.preco_centavos,
          estoque_disponivel: item.estoque_disponivel,
          quantidade: 1,
        });
      }
      renderizarCarrinho();
    }

    document.addEventListener("click", function (e) {
      const btnAdd = e.target.closest(".js-pdv-add");
      if (btnAdd && !btnAdd.disabled) {
        adicionarAoCarrinho({
          tipo: btnAdd.dataset.tipo,
          id: parseInt(btnAdd.dataset.id, 10),
          nome: btnAdd.dataset.nome,
          preco_centavos: parseInt(btnAdd.dataset.preco, 10) || 0,
          estoque_disponivel: parseInt(btnAdd.dataset.estoque, 10) || 0,
        });
        return;
      }

      const nichoChip = e.target.closest(".js-pdv-nicho");
      if (nichoChip) {
        document.querySelectorAll(".js-pdv-nicho").forEach(function (el) {
          el.classList.remove("active");
        });
        nichoChip.classList.add("active");
        if (pdvNichoEl) pdvNichoEl.value = nichoChip.dataset.nichoId || "";
        return;
      }

      const payBtn = e.target.closest(".js-pdv-pay");
      if (payBtn) {
        document.querySelectorAll(".js-pdv-pay").forEach(function (el) {
          el.classList.remove("active");
        });
        payBtn.classList.add("active");
        const forma = payBtn.dataset.forma || "pix";
        formaEl.value = forma;
        if (trocoBox) trocoBox.style.display = forma === "dinheiro" ? "" : "none";
        return;
      }

      const inc = e.target.closest(".js-cart-inc");
      if (inc) {
        const it = cart[parseInt(inc.dataset.idx, 10)];
        if (it && it.quantidade < it.estoque_disponivel) {
          it.quantidade += 1;
          renderizarCarrinho();
        }
        return;
      }
      const dec = e.target.closest(".js-cart-dec");
      if (dec) {
        const idx = parseInt(dec.dataset.idx, 10);
        const it = cart[idx];
        if (it) {
          it.quantidade -= 1;
          if (it.quantidade <= 0) cart.splice(idx, 1);
          renderizarCarrinho();
        }
        return;
      }
      const del = e.target.closest(".js-cart-del");
      if (del) {
        cart.splice(parseInt(del.dataset.idx, 10), 1);
        renderizarCarrinho();
      }
    });

    if (pdvBuscaEl) {
      pdvBuscaEl.addEventListener("keydown", function (e) {
        if (e.key !== "Enter") return;
        e.preventDefault();
        const termo = pdvBuscaEl.value.trim();
        if (!termo) return;
        fetch("/pdv/buscar?busca=" + encodeURIComponent(termo) + "&formato=json")
          .then(function (resp) { return resp.json(); })
          .then(function (data) {
            const prods = data.produtos || [];
            const kits = data.kits || [];
            const exato = prods.find(function (p) { return p.match_exato_barras; });
            const unico = prods.length + kits.length === 1 ? (prods[0] || kits[0]) : null;
            const alvo = exato || unico;
            if (alvo && alvo.estoque_disponivel > 0) {
              adicionarAoCarrinho(alvo);
              pdvBuscaEl.value = "";
              pdvBuscaEl.dispatchEvent(new Event("input", { bubbles: true }));
            }
          });
      });
    }

    const btnLimpar = document.getElementById("pdv-limpar");
    if (btnLimpar) {
      btnLimpar.addEventListener("click", function () {
        cart.length = 0;
        renderizarCarrinho();
      });
    }
    if (descontoEl) descontoEl.addEventListener("input", renderizarCarrinho);
    if (recebidoEl) recebidoEl.addEventListener("input", renderizarCarrinho);

    pdvForm.addEventListener("submit", function (e) {
      if (!cart.length) {
        e.preventDefault();
        alert("Adicione pelo menos um produto ou kit ao carrinho antes de finalizar.");
      }
    });
  }
})();
