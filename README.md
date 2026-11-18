# Loja Itamarandiba — Sistema de Gestão Local

Sistema web local em Português para gestão completa da loja de presentes, variedades e kits em Itamarandiba/MG.

## Como iniciar no Windows

1. Dê um duplo clique em `INICIAR-LOJA.bat`.
2. Se for a primeira execução em um novo computador, o script cria `.venv` e instala `requirements.txt` automaticamente.
3. O sistema abre no navegador em `http://127.0.0.1:8000`.
4. No primeiro acesso, defina seu nome, usuário e senha de administrador.

## Onde os dados ficam salvos

- **Banco SQLite ativo (`loja.db`) e fotos:** `C:\Users\<seu-usuario>\AppData\Local\LojaItamarandiba\` (fora da pasta sincronizada em nuvem para evitar travamento e corrupção do SQLite em modo WAL).
- **Backups diários automáticos e manuais (`.zip`):** `H:\Meu Drive\ANTIGRAVITY\loja-itamarandiba-gestao\backups\` (contendo cópia consistente via API nativa do SQLite + verificação `PRAGMA integrity_check` + fotos, com retenção de 30 diários e 12 mensais).

## Recursos disponíveis (Etapa 3 — Base do sistema)

- Banco SQLite em modo WAL com chaves estrangeiras ativadas e 16 tabelas estruturadas (`migrations/v001_inicial.py`).
- Seed automático e idempotente dos 10 nichos aprovados (`seeds/nichos.py`).
- Autenticação local com hash `scrypt`, bloqueio temporário de 15 minutos após 5 tentativas inválidas, expiração automática por inatividade e proteção CSRF em todas as ações POST.
- Log de auditoria para acessos, alterações de configurações e backups.
- Seleção de 3 temas visuais (`Claro`, `Escuro`, `Alto contraste`) em **Configurações** ou troca rápida no rodapé do menu.
- Backup automático diário + backup manual com 1 clique e restauração segura (gera cópia `pre_restore_*.zip` antes de substituir os dados).

## Recursos disponíveis (Etapa 4 — Cadastros)

- **Produtos (`/produtos`):** cadastro e edição com cálculo de margem ao vivo, mini-filtros para nichos e fornecedores no formulário, alerta de SKU/código de barras/nome semelhante, upload seguro de fotos (JPG/PNG/WEBP validadas via Pillow e convertidas para WebP + miniatura), múltiplos filtros combinados com memória na sessão e inativação segura.
- **Nichos (`/nichos`):** gestão dos 10 nichos (cor, descrição, status ativo/inativo e contagem de produtos).
- **Fornecedores (`/fornecedores`):** distribuidores locais, atacado, China e marketplaces com filtros por tipo/cidade e link pronto de WhatsApp e site.
- **Clientes (`/clientes`):** cadastro com filtro por nome, cidade e aniversariantes do mês, além de link pronto de WhatsApp.

## Recursos disponíveis (Etapa 5 — Operação)

- **PDV / Frente de Caixa (`/pdv` · atalho `F2` / finalizar `F9`):** busca rápida por nome, SKU ou leitor de código de barras (Enter adiciona automaticamente), filtros por nicho, carrinho em tempo real para produtos e kits, desconto geral, formas de pagamento (Pix, Dinheiro com troco ao vivo, Débito e Crédito) e emissão de comprovante imprimível (`/vendas/<id>`).
- **Vendas Realizadas (`/vendas`):** histórico filtrado por cliente, canal, pagamento, status e período com apuração de faturamento e lucro bruto, além de cancelamento/estorno com devolução automática de todos os componentes ao estoque.
- **Kits & Combos (`/kits`):** montagem de combos nas faixas Básico, Presente e Premium com simulação de custo/economia/margem em tempo real e cálculo automático da capacidade disponível conforme o estoque dos componentes.
- **Compras & Entradas (`/compras`):** registro de pedidos por fornecedor com rateio proporcional de frete, impostos e outros custos sem perda de centavos, atualização de custo médio/real dos itens e recebimento com proteção contra entrada duplicada.
- **Estoque (`/estoque` e `/estoque/movimentos`):** posição valorizada a custo e potencial de venda, contador contínuo de itens em alerta no menu lateral e painel inicial, histórico completo de movimentações e registro de ajustes manuais ou perdas com motivo obrigatório.

## Recursos disponíveis (Etapa 6 — Relatórios)

- **Painel Gerencial (`/relatorios`):** faturamento, CMV, lucro bruto real, margem média e ticket médio com filtros por período, canal, forma de pagamento, nicho e mês de aniversário (salvos na sessão).
- **Visões analíticas:** vendas por canal e pagamento, evolução diária, Curva ABC (classes A, B e C), desempenho por nicho, alertas de reposição, itens sem giro no período, compras recebidas por fornecedor, top clientes e aniversariantes com link de WhatsApp.
- **Exportação:** download completo em Excel multi-abas (`.xlsx` via OpenPyXL) e `.csv` (UTF-8 BOM com `;` para Excel Brasil), além de versão otimizada para impressão/PDF.

## Recursos disponíveis (Etapa 7 — Extras)

- **Etiquetas de Preço e Barras (`/extras/etiquetas`):** folha imprimível com nome da loja, produto, preço, SKU e código de barras SVG local.
- **Central WhatsApp (`/extras/whatsapp`):** geração de links prontos (`wa.me`) com mensagens editáveis para aniversariantes e cotação de reposição com fornecedores.
- **Calculadora de Importação (`/extras/importacao`):** simulação de câmbio USD/BRL, imposto, frete e taxas de marketplace com preço sugerido para atingir a margem alvo.
- **Importação em Lote (`/extras/importar`):** download de planilha modelo `.xlsx` e carga em massa de produtos via `.xlsx` ou `.csv` com proteção anti-duplicidade.

## Executar testes automatizados

```powershell
& '.\.venv\Scripts\pytest.exe' -v
```
