"""CLI para retro-popular sidecars JSON das edições já publicadas (Ciclo 11.6).

Lista jornal/AAAA-MM-DD.html no R2, baixa cada HTML, parseia via
parse_jornal_para_sidecar e sobe o JSON correspondente. `--skip-existentes`
(default true) evita sobrescrever sidecars já produzidos pelo pipeline diário.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import date

from scripts.publicar import PREFIXO_R2, publicar_sidecar
from scripts.r2_client import R2Client
from scripts.sidecar_backfill import parse_jornal_para_sidecar

logger = logging.getLogger(__name__)

_RE_CHAVE_JORNAL = re.compile(r"^jornal/(\d{4}-\d{2}-\d{2})\.html$")


def listar_edicoes_publicadas(r2: R2Client) -> list[date]:
    """Lista datas de jornal/AAAA-MM-DD.html no R2 (desc).

    Usa list_objects_v2 raw (boto3) — não precisa de método novo no wrapper.
    Filtra index.html e qualquer outro arquivo fora do padrão de data.
    """
    resposta = r2.client.list_objects_v2(
        Bucket=r2.bucket if hasattr(r2, "bucket") else None,
        Prefix=PREFIXO_R2,
    )
    datas: list[date] = []
    for obj in resposta.get("Contents", []):
        m = _RE_CHAVE_JORNAL.match(obj["Key"])
        if m:
            datas.append(date.fromisoformat(m.group(1)))
    return sorted(datas, reverse=True)


def _chave_sidecar(d: date) -> str:
    return f"{PREFIXO_R2}{d.isoformat()}.json"


def _chave_html(d: date) -> str:
    return f"{PREFIXO_R2}{d.isoformat()}.html"


def backfill_uma(
    data_edicao: date,
    r2: R2Client,
    *,
    dry_run: bool = False,
    skip_existentes: bool = True,
) -> str:
    """Processa uma edição: baixa HTML → parseia → sobe sidecar.

    Retorna status: "sucesso" | "ja_existe" | "dry_run" | "erro".
    """
    if skip_existentes and r2.existe(_chave_sidecar(data_edicao)):
        return "ja_existe"
    if dry_run:
        return "dry_run"
    try:
        html_bytes = r2.download_bytes(_chave_html(data_edicao))
        html = html_bytes.decode("utf-8")
        url_jornal = r2.url_publica(_chave_html(data_edicao))
        sidecar = parse_jornal_para_sidecar(html, data_edicao, url_jornal)
        publicar_sidecar(sidecar, r2, data_edicao)
        return "sucesso"
    except Exception as e:
        logger.error(f"Falha ao processar {data_edicao}: {e}")
        return "erro"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Retro-popula sidecars JSON das edições já publicadas. "
            "Pula edições cujo sidecar já existe (--no-skip-existentes p/ forçar)."
        ),
    )
    parser.add_argument(
        "--limite", type=int, default=None,
        help="Máximo de edições a processar (default: todas).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Não sobe nada; apenas relata o que faria.",
    )
    parser.add_argument(
        "--no-skip-existentes", action="store_true",
        help="Reprocessa mesmo quando o sidecar JSON já existe no R2.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    r2 = R2Client.from_env()
    datas = listar_edicoes_publicadas(r2)
    if args.limite is not None:
        datas = datas[: args.limite]

    skip_existentes = not args.no_skip_existentes
    contagem: dict[str, int] = {}
    for d in datas:
        status = backfill_uma(
            d, r2,
            dry_run=args.dry_run,
            skip_existentes=skip_existentes,
        )
        contagem[status] = contagem.get(status, 0) + 1
        logger.info(f"{d.isoformat()}: {status}")

    print("Backfill sidecars concluído:")
    print(f"  Total: {len(datas)}")
    for status, n in sorted(contagem.items()):
        print(f"  {status}: {n}")

    return 1 if contagem.get("erro", 0) > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
