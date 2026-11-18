# Etapa 2 – Design Visual do Sistema

> **Status:** Etapa 2 concluída (protótipo pronto para sua avaliação).
> **Protótipo navegável:** [prototipo.html](../prototipo/prototipo.html) (abre direto no navegador, sem precisar instalar nada).
> **Folha de estilos base:** [app.css](../prototipo/app.css) (será reutilizada no sistema final).

---

## 1. Escolha do estilo visual (Open Design)

- **Sistema escolhido:** **Minimalismo quente** (inspirado no design system *Notion*, do catálogo OpenDesign).
- **Por que combina com a loja:**
  - Pouco ruído visual: fundo neutro, bordas suaves, foco total nos produtos, preços e alertas.
  - **Um único destaque (`--accent`)**: azul para o botão principal de cada tela e foco de teclado; o restante usa tons neutros, verde (ok), laranja (atenção) e vermelho (crítico).
  - **Números alinhados (`tabular-nums`)**: colunas de preço, custo, margem e totais não "dançam" na leitura.
  - **Ícones simples de traço único** em SVG local (sem depender de internet e sem emojis decorativos).

## 2. Opções de tema e acessibilidade

- **3 temas selecionáveis** (salvos no navegador e acessíveis pela barra lateral ou em **Configurações**):
  1. **Claro quente (padrão):** fundo `#ffffff` com barra lateral `#f6f5f4`.
  2. **Escuro suave:** fundo `#191918` para ambientes com pouca luz.
  3. **Alto contraste:** bordas e textos reforçados para leitura rápida no balcão.
- **Contraste conferido (WCAG 2.2 AA):** todos os textos, rótulos secundários e badges passam do mínimo de 4,5:1 de contraste tanto no tema claro quanto no escuro.
- **Atalhos rápidos:** `F2` abre **Nova venda**; `F9` finaliza a venda no caixa; `Esc` fecha o menu em telas pequenas.

## 3. O que você pode testar no protótipo

| Tela | O que testar |
|---|---|
| **Início** | Resumo do dia/7 dias/mês, vendas por nicho, alertas de estoque baixo e aniversariantes |
| **Produtos** | Busca por nome/SKU/código de barras + filtros por nicho, fornecedor, faixa de preço, margem, chips de estoque e ordenação; clique em qualquer linha para abrir em modo edição |
| **Cadastro / Edição** | Cálculo de margem e lucro em tempo real, aviso de produto parecido, filtros dentro de nichos e fornecedores, upload de fotos com miniatura instantânea e validação ao sair do campo |
| **Nova venda (PDV)** | Busca com código de barras (`F2`), filtro rápido por nicho, controle de estoque no carrinho, campo de desconto, escolha de pagamento e finalização (`F9`) |
| **Configurações** | Escolha visual entre os temas Claro, Escuro e Alto contraste |

## 4. Próximo passo (Etapa 3)

Após sua aprovação do visual e dos filtros:
- Iniciar a **Etapa 3 – Base do sistema** (estrutura Flask + SQLAlchemy/SQLite no disco local + `INICIAR-LOJA.bat` + login com senha + backup automático no Google Drive + testes automáticos).
