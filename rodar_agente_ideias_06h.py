"""Agente diário das 06:00 — Loja ItaDigital.

Sincroniza ideias da Planilha Google, verifica ideias pendentes, busca modelos no MakerWorld,
compara preços e tamanhos no Mercado Livre e Shopee, reescala/rotaciona (Face-Down 180°),
executa fatiamento e grava o relatório matinal.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.config import build_settings
from app.db import get_session, init_db
from app.services.ideia_3d_service import (
    listar_ideias,
    processar_pendentes,
    sincronizar_com_google_sheets,
)


def executar_rotina_matinal() -> dict:
    settings = build_settings()
    engine = init_db(settings)

    sync_inicial = {}
    processadas = []
    sync_final = {}

    with get_session(engine) as db:
        sync_inicial = sincronizar_com_google_sheets(db)
        db.commit()

        processadas = processar_pendentes(db, base_modelos_dir=PROJECT_DIR / "modelos_3d")
        db.commit()

        if processadas or sync_inicial.get("ok"):
            sync_final = sincronizar_com_google_sheets(db)
            db.commit()

        todas = listar_ideias(db)

    rel_dir = PROJECT_DIR / "relatorios_06h"
    rel_dir.mkdir(parents=True, exist_ok=True)
    hoje = datetime.now().strftime("%Y-%m-%d")
    rel_path = rel_dir / f"relatorio_{hoje}.md"

    linhas = [
        f"# Relatório Matinal 06h — Ideias de Impressão 3D ({hoje})",
        "",
        f"- **Sincronização inicial (Google Sheets):** `{json.dumps(sync_inicial, ensure_ascii=False)}`",
        f"- **Ideias pendentes processadas agora:** **{len(processadas)}**",
        f"- **Total de ideias no sistema:** **{len(todas)}**",
        "",
    ]
    if processadas:
        linhas.append("## Ideias Processadas Hoje")
        for p in processadas:
            preco_brl = p["preco_sugerido_centavos"] / 100.0
            linhas.append(
                f"- **#{p['id']} {p['termo_ideia']}** — {p['gramas']}g | Sugerido: R$ {preco_brl:.2f} | Arquivo: `{p['arquivo_fatiado']}`"
            )
    else:
        linhas.append("_Nenhuma ideia pendente encontrada nesta execução._")

    rel_path.write_text("\n".join(linhas), encoding="utf-8")

    return {
        "relatorio": str(rel_path),
        "processadas": len(processadas),
        "sync_inicial": sync_inicial,
        "sync_final": sync_final,
    }


if __name__ == "__main__":
    res = executar_rotina_matinal()
    print(json.dumps(res, ensure_ascii=False, indent=2))
