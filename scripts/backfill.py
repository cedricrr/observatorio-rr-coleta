"""Backfill histórico — núcleo (gerar datas, checkpoint).

A orquestração (modos listing/daily, CLI) fica em ciclo separado.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


STATUS_VALIDOS = {"sucesso", "erro", "pulado_dedupe", "sem_diario"}


@dataclass
class Checkpoint:
    """Estado de uma execução de backfill, persistível em JSON."""

    escopo: str
    iniciado_em: str
    atualizado_em: str
    itens: list[dict]
    config: dict


def gerar_datas(de: date, ate: date, somente_uteis: bool = False) -> list[date]:
    """Lista datas entre `de` e `ate` (inclusivo). Se somente_uteis, pula sáb/dom."""
    if de > ate:
        raise ValueError(f"de ({de}) > ate ({ate})")
    datas: list[date] = []
    atual = de
    while atual <= ate:
        if not somente_uteis or atual.weekday() < 5:
            datas.append(atual)
        atual += timedelta(days=1)
    return datas


def carregar_checkpoint(caminho: Path) -> Checkpoint | None:
    """Carrega checkpoint do JSON; None se arquivo não existe."""
    if not caminho.exists():
        return None
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return Checkpoint(**dados)


def gravar_checkpoint(checkpoint: Checkpoint, caminho: Path) -> None:
    """Atualiza atualizado_em e grava em disco com indent=2, UTF-8 preservado."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.atualizado_em = datetime.now().isoformat()
    caminho.write_text(
        json.dumps(asdict(checkpoint), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def marcar_processado(
    checkpoint: Checkpoint,
    item_id: str,
    status: str,
    detalhes: str | None = None,
) -> None:
    """Adiciona item ao checkpoint com timestamp ISO atual. Não persiste."""
    if status not in STATUS_VALIDOS:
        raise ValueError(f"status inválido: {status!r}")
    checkpoint.itens.append({
        "id": item_id,
        "status": status,
        "detalhes": detalhes,
        "timestamp": datetime.now().isoformat(),
    })


def ja_processado(checkpoint: Checkpoint, item_id: str) -> bool:
    """True se já houver item com esse id no checkpoint."""
    return any(it["id"] == item_id for it in checkpoint.itens)
