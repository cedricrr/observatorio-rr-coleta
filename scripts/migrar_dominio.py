"""Migração de domínio público nos artefatos já publicados (Ciclo 12).

Reescreve `https://<dominio-antigo>/` → `https://<dominio-novo>/` em:
- **r2**: HTMLs e sidecars JSON sob `jornal/` no bucket, preservando
  ContentType/CacheControl/Metadata originais (lidos via head_object —
  não inferidos por extensão);
- **jsons**: campo `url_r2` dos JSONs locais de `data/diarios/`, por
  text-replace puro (o diff do git fica restrito à linha da URL).

Idempotente: chaves/arquivos sem o domínio antigo são pulados ("já ok");
rodar duas vezes é no-op. Não usa a API Anthropic. O script NÃO commita —
o commit dos JSONs locais é manual, único, após conferência.

Uso (domínios sempre explícitos — sem default do .env, para poder rodar
APÓS a troca de R2_PUBLIC_DOMAIN sem ambiguidade):

    python -m scripts.migrar_dominio \
        --dominio-antigo pub-xxx.r2.dev \
        --dominio-novo observatoriorr.com.br \
        [--alvo r2|jsons|todos] [--dry-run] [--diarios-dir data/diarios]
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

from scripts.r2_client import R2Client

logger = logging.getLogger(__name__)

PREFIXO_JORNAL = "jornal/"
DIARIOS_DIR_DEFAULT = Path("data/diarios")
_EXTENSOES_TEXTUAIS = (".html", ".json", ".txt", ".xml")


def _migrar_chave(
    chave: str, antigo: str, novo: str, r2: R2Client, dry_run: bool,
) -> str:
    """Migra uma chave do R2. Retorna "migrado" ou "ja_ok"."""
    texto = r2.download_bytes(chave).decode("utf-8")
    marcador = f"https://{antigo}/"
    if marcador not in texto:
        return "ja_ok"
    if dry_run:
        logger.info(f"[dry-run] migraria {chave} ({texto.count(marcador)} URLs)")
        return "migrado"

    head = r2.client.head_object(Bucket=r2.bucket, Key=chave)
    novo_texto = texto.replace(marcador, f"https://{novo}/")
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(novo_texto)
        tmp_path = Path(tmp.name)
    try:
        r2.upload(
            tmp_path,
            chave,
            metadados=head.get("Metadata") or None,
            content_type=head["ContentType"],
            cache_control=head.get("CacheControl"),
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.info(f"Migrado: {chave}")
    return "migrado"


def migrar_r2(
    antigo: str, novo: str, r2: R2Client, dry_run: bool = False,
) -> dict[str, int]:
    """Migra HTMLs/sidecars sob jornal/ no R2. Erro em uma chave não derruba o resto."""
    resumo = {"migrados": 0, "ja_ok": 0, "erros": 0}
    chaves = [
        c for c in r2.listar(PREFIXO_JORNAL) if c.endswith(_EXTENSOES_TEXTUAIS)
    ]
    for chave in chaves:
        try:
            status = _migrar_chave(chave, antigo, novo, r2, dry_run)
        except Exception as e:
            logger.error(f"Erro ao migrar {chave}: {e}")
            resumo["erros"] += 1
            continue
        resumo["migrados" if status == "migrado" else "ja_ok"] += 1
    logger.info(
        f"R2: {resumo['migrados']} migrados / {resumo['ja_ok']} já ok / "
        f"{resumo['erros']} erros"
    )
    return resumo


def migrar_jsons(
    antigo: str,
    novo: str,
    diarios_dir: Path = DIARIOS_DIR_DEFAULT,
    dry_run: bool = False,
) -> dict[str, int]:
    """Migra o domínio nos JSONs locais de data/diarios/ (text-replace puro)."""
    resumo = {"migrados": 0, "ja_ok": 0}
    marcador = f"https://{antigo}/"
    for json_path in sorted(diarios_dir.glob("*/*.json")):
        texto = json_path.read_text(encoding="utf-8")
        if marcador not in texto:
            resumo["ja_ok"] += 1
            continue
        if not dry_run:
            json_path.write_text(
                texto.replace(marcador, f"https://{novo}/"), encoding="utf-8",
            )
        resumo["migrados"] += 1
    logger.info(
        f"JSONs locais: {resumo['migrados']} migrados / {resumo['ja_ok']} já ok"
        f"{' (dry-run, nada gravado)' if dry_run else ''}"
    )
    return resumo


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reescreve o domínio público nos artefatos já publicados",
    )
    parser.add_argument("--dominio-antigo", required=True)
    parser.add_argument("--dominio-novo", required=True)
    parser.add_argument(
        "--alvo", choices=("r2", "jsons", "todos"), default="todos",
        help="r2 = HTMLs/sidecars no bucket; jsons = data/diarios/ local.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--diarios-dir", type=Path, default=DIARIOS_DIR_DEFAULT,
        help=f"Diretório dos JSONs locais. Default: {DIARIOS_DIR_DEFAULT}.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv)
    if args.dominio_antigo == args.dominio_novo:
        logger.error("--dominio-antigo e --dominio-novo são iguais; nada a fazer.")
        return 1

    if args.alvo in ("r2", "todos"):
        resumo = migrar_r2(
            args.dominio_antigo, args.dominio_novo,
            R2Client.from_env(), dry_run=args.dry_run,
        )
        if resumo["erros"]:
            return 1
    if args.alvo in ("jsons", "todos"):
        migrar_jsons(
            args.dominio_antigo, args.dominio_novo,
            args.diarios_dir, dry_run=args.dry_run,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
