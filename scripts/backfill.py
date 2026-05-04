"""Backfill histórico — núcleo + orquestração e CLI."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from scripts.coletar import processar_descoberta, processar_fonte
from scripts.config import FONTES, Fonte, get_fonte
from scripts.r2_client import R2Client


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


def backfill_listing(
    fonte: Fonte,
    anos: list[int],
    r2: R2Client | None,
    checkpoint: Checkpoint,
    pausa: float,
    dry_run: bool = False,
) -> Checkpoint:
    """Modo listing: usa list_year da fonte e processa todas as edições por ano."""
    for ano in anos:
        mod = importlib.import_module(f"fontes.{fonte.discovery_module}")
        for descoberta in mod.list_year(ano):
            item_id = (
                f"{fonte.codigo}-{descoberta['data_edicao']}-"
                f"{descoberta.get('numero', '')}"
            )
            if ja_processado(checkpoint, item_id):
                continue
            if dry_run:
                marcar_processado(checkpoint, item_id, "pulado_dedupe")
                continue
            try:
                processar_descoberta(fonte, descoberta, r2)
                marcar_processado(checkpoint, item_id, "sucesso")
            except (requests.RequestException, RuntimeError) as e:
                marcar_processado(checkpoint, item_id, "erro", str(e))
            if pausa > 0:
                time.sleep(pausa)
    return checkpoint


def backfill_daily(
    fonte: Fonte,
    de: date,
    ate: date,
    somente_uteis: bool,
    r2: R2Client | None,
    checkpoint: Checkpoint,
    pausa: float,
    dry_run: bool = False,
) -> Checkpoint:
    """Modo daily: itera datas no intervalo e tenta descoberta+download em cada."""
    for data in gerar_datas(de, ate, somente_uteis):
        item_id = f"{fonte.codigo}-{data.isoformat()}"
        if ja_processado(checkpoint, item_id):
            continue
        if dry_run:
            marcar_processado(checkpoint, item_id, "pulado_dedupe")
            continue
        try:
            resultado = processar_fonte(fonte, data, r2)
            if resultado is None:
                marcar_processado(checkpoint, item_id, "sem_diario")
            else:
                marcar_processado(checkpoint, item_id, "sucesso")
        except Exception as e:
            marcar_processado(checkpoint, item_id, "erro", str(e))
        if pausa > 0:
            time.sleep(pausa)
    return checkpoint


def gerar_relatorio(checkpoint: Checkpoint) -> str:
    """Resumo legível do estado do checkpoint: contagens por status + tempo."""
    total = len(checkpoint.itens)
    n_sucesso = sum(1 for i in checkpoint.itens if i["status"] == "sucesso")
    n_erro = sum(1 for i in checkpoint.itens if i["status"] == "erro")
    n_sd = sum(1 for i in checkpoint.itens if i["status"] == "sem_diario")
    n_pd = sum(1 for i in checkpoint.itens if i["status"] == "pulado_dedupe")
    iniciado = datetime.fromisoformat(checkpoint.iniciado_em)
    atualizado = datetime.fromisoformat(checkpoint.atualizado_em)
    decorrido = atualizado - iniciado
    return (
        f"Backfill: {checkpoint.escopo}\n"
        f"Total: {total}\n"
        f"  sucesso: {n_sucesso}\n"
        f"  erro: {n_erro}\n"
        f"  sem_diario: {n_sd}\n"
        f"  pulado_dedupe: {n_pd}\n"
        f"Tempo: {decorrido}\n"
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point CLI do backfill histórico."""
    parser = argparse.ArgumentParser(
        description="Backfill histórico do Observatório Roraima",
    )
    parser.add_argument("--fonte", required=True, choices=[f.codigo for f in FONTES])
    parser.add_argument("--anos", help="Lista de anos separados por vírgula (modo listing)")
    parser.add_argument("--de", help="Data inicial YYYY-MM-DD (modo daily)")
    parser.add_argument("--ate", help="Data final YYYY-MM-DD (modo daily)")
    parser.add_argument("--somente-dias-uteis", action="store_true")
    parser.add_argument("--pausa", type=float, default=3.0)
    parser.add_argument("--retomar", action="store_true")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)

    if args.anos and (args.de or args.ate):
        parser.error("--anos não pode ser usado junto com --de/--ate")
    if args.de and not args.ate:
        parser.error("--de requer --ate")
    if args.ate and not args.de:
        parser.error("--ate requer --de")
    if not args.anos and not args.de:
        parser.error("forneça --anos OU --de e --ate")

    fonte = get_fonte(args.fonte)
    modo = "listing" if args.anos else "daily"

    anos: list[int] = []
    if args.anos:
        try:
            anos = [int(a.strip()) for a in args.anos.split(",")]
        except ValueError:
            parser.error(f"--anos contém valor inválido: {args.anos!r}")

    if modo == "listing":
        escopo = f"{fonte.codigo}-{'-'.join(str(a) for a in anos)}"
    else:
        escopo = f"{fonte.codigo}-{args.de}-a-{args.ate}"

    caminho_ckpt = Path("data/backfill") / f"{escopo}.json"

    checkpoint = None
    if args.retomar:
        checkpoint = carregar_checkpoint(caminho_ckpt)

    if checkpoint is None:
        agora = datetime.now().isoformat()
        checkpoint = Checkpoint(
            escopo=escopo,
            iniciado_em=agora,
            atualizado_em=agora,
            itens=[],
            config={
                "fonte": args.fonte,
                "modo": modo,
                "pausa": args.pausa,
                "dry_run": args.dry_run,
            },
        )

    r2 = None if args.dry_run else R2Client.from_env()

    if modo == "listing":
        checkpoint = backfill_listing(
            fonte, anos, r2, checkpoint, args.pausa, dry_run=args.dry_run,
        )
    else:
        de = date.fromisoformat(args.de)
        ate = date.fromisoformat(args.ate)
        checkpoint = backfill_daily(
            fonte, de, ate, args.somente_dias_uteis,
            r2, checkpoint, args.pausa, dry_run=args.dry_run,
        )

    gravar_checkpoint(checkpoint, caminho_ckpt)
    print(gerar_relatorio(checkpoint))

    houve_erro = any(item["status"] == "erro" for item in checkpoint.itens)
    return 1 if houve_erro else 0


if __name__ == "__main__":
    sys.exit(main())
