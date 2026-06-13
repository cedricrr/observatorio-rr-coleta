"""Backfill de publicação (Ciclo 10.6).

Gera e publica jornais editoriais retroativos a partir das chaves R2 já
coletadas em data/diarios/, SEM re-discover nos portais (que falharia para
datas antigas e geraria jornal vazio mesmo com o PDF no R2). Idempotente:
pula datas cujo jornal já existe no R2.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from scripts.backfill import (
    Checkpoint,
    carregar_checkpoint,
    gerar_relatorio,
    gravar_checkpoint,
    ja_processado,
    marcar_processado,
)
from scripts.cliente_anthropic import ClienteAnthropic
from scripts.jornal_diario import ganchos_busca, processar_chave
from scripts.publicar import (
    PREFIXO_R2,
    gerar_indice,
    publicar_indice,
    publicar_jornal,
)
from scripts.r2_client import R2Client
from scripts.renderizar import renderizar_jornal
from scripts.segmentar import Materia

# Diretório de origem → código de fonte aceito por processar_chave/segmentar.
_FONTE_POR_DIR = {"mprr": "MPRR", "tjrr": "TJRR"}
_RE_DATA_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def chave_jornal(data: date) -> str:
    """Chave R2 do jornal de uma data: jornal/AAAA-MM-DD.html."""
    return f"{PREFIXO_R2}{data.isoformat()}.html"


def mapear_chaves(diarios_dir: Path) -> dict[date, dict[str, str]]:
    """Varre data/diarios/{fonte}/*.json e devolve {data: {FONTE: chave_r2}}.

    A chave R2 do PDF é extraída de `url_r2` (mesma lógica do coletar_dia).
    JSON sem `url_r2` ou com nome fora do padrão de data é ignorado.
    """
    mapa: dict[date, dict[str, str]] = {}
    if not diarios_dir.exists():
        return mapa

    for fonte_dir in sorted(diarios_dir.iterdir()):
        if not fonte_dir.is_dir():
            continue
        fonte = _FONTE_POR_DIR.get(fonte_dir.name)
        if fonte is None:
            continue
        for json_path in fonte_dir.glob("*.json"):
            m = _RE_DATA_ISO.match(json_path.stem)
            if not m:
                continue
            try:
                dados = json.loads(json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            url_r2 = dados.get("url_r2")
            if not url_r2:
                continue
            chave = urlparse(url_r2).path.lstrip("/")
            data_edicao = date.fromisoformat(m.group(1))
            mapa.setdefault(data_edicao, {})[fonte] = chave
    return mapa


def processar_data(
    data: date,
    chaves_por_fonte: dict[str, str],
    r2: R2Client,
    cliente: ClienteAnthropic,
    output_dir: Path,
) -> tuple[str, int]:
    """Gera e publica o jornal de uma data a partir de chaves conhecidas.

    Pula (sem reprocessar) se o jornal já existe no R2. Retorna
    (status, n_materias): status ∈ {"pulado_dedupe", "sucesso"}. Exceções
    de geração/publicação propagam para o orquestrador marcar "erro".
    """
    if r2.existe(chave_jornal(data)):
        return ("pulado_dedupe", 0)

    materias: list[Materia] = []
    for fonte, chave in sorted(chaves_por_fonte.items()):
        materias.extend(processar_chave(chave, fonte, r2, cliente))

    url_busca, ocorrencias = ganchos_busca(materias)
    html = renderizar_jornal(
        materias, data, url_canonica=r2.url_publica(chave_jornal(data)),
        url_busca=url_busca, ocorrencias_acervo=ocorrencias,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{data.isoformat()}.html"
    output_path.write_text(html, encoding="utf-8")
    publicar_jornal(output_path, r2, data)

    return ("sucesso", len(materias))


def executar_backfill(
    diarios_dir: Path,
    r2: R2Client,
    cliente: ClienteAnthropic,
    output_dir: Path,
    checkpoint: Checkpoint,
    *,
    de: date | None = None,
    ate: date | None = None,
    dry_run: bool = False,
    limite: int | None = None,
    caminho_checkpoint: Path | None = None,
) -> Checkpoint:
    """Itera as datas publicáveis (recente→antigo) gerando/publicando o jornal.

    Reusa o checkpoint de `backfill.py`: persiste após cada data e em
    try/finally (interrupções/crashes preservam progresso para `--retomar`).
    `dry_run` apenas marca `pulado_dedupe` sem gerar nada. O índice é
    regenerado UMA vez no fim (não a cada data) — exceto em dry_run.
    `de`/`ate` filtram inclusivos; `limite` corta após o filtro.
    """
    mapa = mapear_chaves(diarios_dir)
    datas = sorted(
        (d for d in mapa.keys() if (de is None or d >= de) and (ate is None or d <= ate)),
        reverse=True,
    )
    if limite is not None:
        datas = datas[:limite]

    try:
        for data in datas:
            item_id = data.isoformat()
            if ja_processado(checkpoint, item_id):
                continue
            if dry_run:
                marcar_processado(checkpoint, item_id, "pulado_dedupe")
            else:
                try:
                    status, n = processar_data(
                        data, mapa[data], r2, cliente, output_dir,
                    )
                    marcar_processado(
                        checkpoint, item_id, status, detalhes=f"{n} materias",
                    )
                except Exception as e:
                    marcar_processado(checkpoint, item_id, "erro", str(e))
            if caminho_checkpoint is not None:
                gravar_checkpoint(checkpoint, caminho_checkpoint)
    finally:
        if caminho_checkpoint is not None:
            gravar_checkpoint(checkpoint, caminho_checkpoint)

    if not dry_run:
        html_indice = gerar_indice(diarios_dir, public_domain=r2.public_domain)
        publicar_indice(html_indice, r2)

    return checkpoint


_OUTPUT_DIR_DEFAULT = Path("/tmp/observatorio-roraima")
_DIARIOS_DIR_DEFAULT = Path("data/diarios")


def main(argv: list[str] | None = None) -> int:
    """Entry point CLI do backfill de publicação."""
    parser = argparse.ArgumentParser(
        description="Backfill de publicação editorial do Observatório Roraima",
    )
    parser.add_argument("--de", help="Data inicial inclusiva YYYY-MM-DD")
    parser.add_argument("--ate", help="Data final inclusiva YYYY-MM-DD")
    parser.add_argument(
        "--limite", type=int, help="Máximo de datas a processar (calibração)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retomar", action="store_true")
    parser.add_argument(
        "--diarios-dir", type=Path, default=_DIARIOS_DIR_DEFAULT,
        help=f"Diretório de origem dos JSONs. Default: {_DIARIOS_DIR_DEFAULT}",
    )
    parser.add_argument(
        "--output", type=Path, default=_OUTPUT_DIR_DEFAULT,
        help=f"Diretório de HTMLs gerados. Default: {_OUTPUT_DIR_DEFAULT}",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    de = date.fromisoformat(args.de) if args.de else None
    ate = date.fromisoformat(args.ate) if args.ate else None
    if de and ate and de > ate:
        parser.error(f"--de ({de}) > --ate ({ate})")

    sufixo = ""
    if de or ate:
        sufixo = f"-{de or '...'}-a-{ate or '...'}"
    escopo = f"publicacao{sufixo}"
    caminho_ckpt = Path("data/backfill") / f"{escopo}.json"

    checkpoint: Checkpoint | None = None
    if args.retomar:
        checkpoint = carregar_checkpoint(caminho_ckpt)
    if checkpoint is None:
        agora = datetime.now().isoformat()
        checkpoint = Checkpoint(
            escopo=escopo, iniciado_em=agora, atualizado_em=agora,
            itens=[],
            config={
                "modo": "publicacao",
                "de": args.de, "ate": args.ate,
                "limite": args.limite,
                "dry_run": args.dry_run,
            },
        )

    r2 = R2Client.from_env()
    cliente = ClienteAnthropic(
        model="claude-haiku-4-5-20251001", extended_thinking=False
    )

    checkpoint = executar_backfill(
        args.diarios_dir, r2, cliente, args.output, checkpoint,
        de=de, ate=ate, dry_run=args.dry_run, limite=args.limite,
        caminho_checkpoint=caminho_ckpt,
    )

    print(gerar_relatorio(checkpoint))

    houve_erro = any(it["status"] == "erro" for it in checkpoint.itens)
    return 1 if houve_erro else 0


if __name__ == "__main__":
    sys.exit(main())
