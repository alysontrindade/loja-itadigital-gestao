# Plano de Implementação – Sistema de Gestão da Loja

## 1️⃣ Visão Geral
Desenvolver um **portal web** local (acessível via `http://localhost:8000`) que permita ao administrador gerenciar:
- Produtos (cadastro, imagens, tags de nicho, estoque, preço de compra/venda)
- Vendas (registro, detalhes do cliente, pagamento)
- Fornecedores (contato, condições, links)
- Bundles/upsell (combinações de produtos)
- Relatórios completos (vendas, margem, estoque, desempenho por nicho, etc.)
- Busca avançada com filtros por nicho, preço, estoque, fornecedor.
- Backup diário automático dos dados SQLite.
- Futuras integrações (Shopify, WooCommerce, APIs de pagamento, WhatsApp, etc.)

## 2️⃣ Ordem de Invocação de Skills (Projeto Kickoff)
| Fase | Skill(s) Selecionada(s) | Objetivo no Projeto |
|------|------------------------|----------------------|
| **Descoberta & Planejamento** | `using-superpowers` → `brainstorming` → `writing-plans` | Definir escopo, requisitos e arquitetura geral |
| **Arquitetura & Diagramas** | `archify` | Gerar diagramas de arquitetura (arquitetura de componentes, fluxo de dados) |
| **Design Visual & UI/UX** | `open-design` | Escolher sistema de design minimalista, temas claro/escuro, componentes UI |
| **Disciplina de Código** | `karpathy-guidelines` | Garantir simplicidade, mudanças cirúrgicas e boas práticas |
| **Infraestrutura & Dependências** | `managing-python-dependencies` | Configurar ambiente virtual, dependências (FastAPI/Flask, SQLModel, Jinja2, Bootstrap) |
| **Desenvolvimento & Testes** | `test-driven-development` → `executing-plans` → `subagent-driven-development` | Implementar rotinas, escrever testes unitários e de integração |
| **Segurança & Backup** | `accidental-data-loss-prevention` → `verification-before-completion` | Implementar hash de senha, backups automáticos, revisão final antes de entrega |
| **Entrega & Documentação** | `writing-skills` (para documentação) → `generative_ui` (para mockups) | Produzir documentação de uso e mockups interativos |

> **Ação:** Revise a tabela acima. Se estiver de acordo, confirmaremos e avançaremos para a fase de **Arquitetura**.

## 3️⃣ Arquitetura Proposta
- **Backend:** Python 3.11 + **FastAPI** (leve, async, fácil de servir).  
- **ORM:** **SQLModel** (camada sobre SQLite) – manipulação simples de modelos e migrações.
- **Banco de Dados:** **SQLite** (`loja.db`) armazenado em `H:/Meu Drive/ANTIGRAVITY/loja-itamarandiba-fornecedores/`.
- **Frontend:** HTML + Jinja2 templates + **Bootstrap 5** (tema claro/escuro toggle). 
- **Autenticação:** sessão com cookie seguro; senha armazenada em **bcrypt hash**.
- **Backup:** script `backup.py` que copia `loja.db` para `backup/loja_YYYYMMDD_HHMMSS.db` diariamente via `schedule` (cron interno).
- **Imagens:** arquivos enviados ficam em `static/images/` (paths armazenados no DB).
- **Filtros de Busca:** endpoint `/products` com query params (`nome`, `sku`, `nicho`, `preco_min`, `preco_max`, `estoque_min`).

## 4️⃣ Roadmap (30 dias)
| Semana | Atividade | Responsável |
|--------|-----------|-------------|
| 1 | Definir modelos de dados (Product, Sale, Supplier, Bundle, User) e gerar diagramas (`archify`). | Você / Agente |
| 2 | Configurar ambiente virtual, instalar dependências (`managing‑python‑dependencies`). | Você |
| 3 | Implementar rotas CRUD básicas e UI mínima (FastAPI + Jinja). | Você |
| 4 | Implementar autenticação, hash de senha e política de segurança (`karpathy‑guidelines`). | Você |
| 5 | Adicionar filtros de busca avançada e paginação. | Você |
| 6 | Criar rotinas de backup automático (`schedule` + `backup.py`). | Você |
| 7 | Desenvolver relatórios (SQL queries + templates): vendas por período, margem por nicho, estoque crítico, desempenho de bundles. | Você |
| 8 | Testes unitários e de integração (`test‑driven‑development`). | Você |
| 9 | Revisão final, verificação de segurança (`verification‑before‑completion`). | Você |
| 10 | Documentação de uso e mockups UI (`generative_ui`). | Você |

## 5️⃣ Próximos Passos
1. **Aprovar a ordem de skills e o roadmap** – confirme para que possamos iniciar a fase de arquitetura.
2. Caso queira ajustar algum ponto (ex.: escolher outro framework), informe agora.

---
*Este plano está salvo como artefato:* `H:/Meu Drive/ANTIGRAVITY/loja-itamarandiba-fornecedores/13-PLANO-IMPLEMENTACAO.md`
