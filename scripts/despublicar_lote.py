"""Despublicação em lote das matérias da auditoria histórica (Fase 4).

Incidente 2026-06-10, proteção a menores (ECA art. 143) — ver
docs/incidentes/2026-06-10-protecao-menores.md. Decisão editorial de
2026-06-11: marcação CONSERVADORA — todas as matérias que casaram na
auditoria saem do ar provisoriamente; a classificação fina virá com
consulta externa.

Reversível por construção: nada é deletado. Cada matéria despublicada
gera snapshot completo (estado anterior + relevante=False +
motivo/data de despublicação) em data/incidentes/snapshots/, e cada
edição tem o sidecar e o HTML originais snapshotados para rollback.

Nota de design: a matéria SAI do sidecar público em vez de ficar nele
com relevante=False — o sidecar só contém relevantes por contrato
(agregar_destaques_recentes não checa o campo) e o JSON é público, ou
seja, manter manchete/resumo ali seria manter a exposição. O registro
relevante=False vive no snapshot local (gitignored), nunca no R2.

Dois estágios (gate de confirmação manual entre eles):
    python -m scripts.despublicar_lote --preparar   # snapshots + staging, nada sobe
    python -m scripts.despublicar_lote --executar   # upload com rollback

A atomicidade possível em um object store: o estágio --preparar
renderiza TUDO localmente antes de qualquer upload (falha de render →
aborta sem tocar o R2); o --executar faz rollback (re-upload dos
originais) de tudo que já subiu se qualquer upload falhar.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.despublicar_emergencia import _dict_para_materia
from scripts.publicar import (
    CACHE_CONTROL_INDICE,
    CHAVE_INDICE,
    CONTENT_TYPE_HTML,
    CONTENT_TYPE_JSON,
    gerar_indice,
    publicar_paginas_diarios,
)
from scripts.r2_client import R2Client
from scripts.renderizar import renderizar_jornal
from scripts.validador_sensivel import casar_termo_sensivel

logger = logging.getLogger(__name__)

INCIDENTES_DIR = Path("data/incidentes")
SNAPSHOTS_DIR = INCIDENTES_DIR / "snapshots"
STAGING_DIR = INCIDENTES_DIR / "fase4-staging"
MANIFEST_PATH = STAGING_DIR / "manifest.json"
RELATORIO_EXECUCAO = INCIDENTES_DIR / "fase4-execucao-20260611.json"

RELATORIO_AUDITORIA_DEFAULT = (
    INCIDENTES_DIR / "auditoria-historico-20260611T031737Z.json"
)
MOTIVO = "fase4-conservadora-20260611"
TOTAL_ESPERADO = 52


def particionar_materias(sidecar: dict) -> tuple[list[dict], list[tuple]]:
    """Separa matérias do sidecar em (mantidas, despublicadas).

    `despublicadas` é lista de (indice_original, materia, termo_casado).
    Usa o MESMO validador da auditoria (casar_termo_sensivel) — re-deriva
    em vez de confiar só no relatório, e o chamador cruza os dois.
    """
    mantidas: list[dict] = []
    despublicadas: list[tuple] = []
    for idx, m in enumerate(sidecar.get("materias", [])):
        termo = casar_termo_sensivel(_dict_para_materia(m))
        if termo is None:
            mantidas.append(m)
        else:
            despublicadas.append((idx, m, termo))
    return mantidas, despublicadas


def montar_sidecar_sem_despublicadas(sidecar: dict, mantidas: list[dict]) -> dict:
    """Novo sidecar com o mesmo cabeçalho e só as matérias mantidas."""
    return {**sidecar, "total_relevantes": len(mantidas), "materias": mantidas}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preparar(relatorio_path: Path, r2: R2Client) -> int:
    """Estágio 1: snapshots + sidecars/HTMLs novos em staging. Não sobe nada."""
    inicio = time.monotonic()
    relatorio = json.loads(relatorio_path.read_text(encoding="utf-8"))
    achados = relatorio["achados"]
    if len(achados) != TOTAL_ESPERADO:
        logger.error(
            f"Relatório tem {len(achados)} achados, esperado {TOTAL_ESPERADO}. "
            "PARANDO — confirme o número antes de prosseguir."
        )
        return 1

    por_data: dict[str, list[dict]] = {}
    for a in achados:
        por_data.setdefault(a["data_edicao"], []).append(a)

    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    ts_operacao = datetime.now(timezone.utc).isoformat()

    edicoes: list[dict] = []
    ja_despublicadas: list[dict] = []
    total_despublicadas = 0

    for data in sorted(por_data):
        chave_json = f"jornal/{data}.json"
        chave_html = f"jornal/{data}.html"
        sidecar_bytes = r2.download_bytes(chave_json)
        html_bytes = r2.download_bytes(chave_html)
        sidecar = json.loads(sidecar_bytes.decode("utf-8"))

        # Snapshots de rollback da edição (estado público atual).
        orig_json = SNAPSHOTS_DIR / f"{data}-sidecar-original.json"
        orig_html = SNAPSHOTS_DIR / f"{data}-html-original.html"
        orig_json.write_bytes(sidecar_bytes)
        orig_html.write_bytes(html_bytes)

        mantidas, despublicadas = particionar_materias(sidecar)

        # Cruzamento com o relatório da auditoria: mesmas manchetes.
        manchetes_relatorio = {a["manchete"] for a in por_data[data]}
        manchetes_agora = {m["manchete"] for _, m, _ in despublicadas}
        faltantes = manchetes_relatorio - manchetes_agora
        extras = manchetes_agora - manchetes_relatorio
        if extras:
            logger.error(
                f"{data}: validador casou matérias fora do relatório: "
                f"{extras}. ABORTANDO preparação."
            )
            return 1
        for manchete in sorted(faltantes):
            # Não está mais no sidecar → já foi despublicada antes.
            ja_despublicadas.append({"data_edicao": data, "manchete": manchete})
            logger.warning(f"{data}: já estava despublicada: {manchete!r}")

        snapshots_materias = []
        for idx, m, termo in despublicadas:
            snap_path = SNAPSHOTS_DIR / f"{data}-{idx:02d}.json"
            snap_path.write_text(
                json.dumps(
                    {
                        **m,
                        "relevante": False,
                        "motivo_despublicacao": MOTIVO,
                        "data_despublicacao": ts_operacao,
                        "termo_casado": termo,
                        "chave_sidecar": chave_json,
                        "indice_no_sidecar": idx,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            snapshots_materias.append({
                "snapshot": str(snap_path),
                "sha256": _sha256(snap_path),
                "manchete": m.get("manchete"),
                "termo": termo,
            })
        total_despublicadas += len(despublicadas)

        # Sidecar novo + HTML re-renderizado do próprio sidecar (sem RLM).
        novo_sidecar = montar_sidecar_sem_despublicadas(sidecar, mantidas)
        stage_json = STAGING_DIR / f"{data}.json"
        stage_json.write_text(
            json.dumps(novo_sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        materias = [_dict_para_materia(m) for m in mantidas]
        html = renderizar_jornal(
            materias,
            datetime.strptime(data, "%Y-%m-%d").date(),
            url_canonica=sidecar.get("url_jornal"),
        )
        stage_html = STAGING_DIR / f"{data}.html"
        stage_html.write_text(html, encoding="utf-8")

        edicoes.append({
            "data_edicao": data,
            "chave_json": chave_json,
            "chave_html": chave_html,
            "sidecar_original": str(orig_json),
            "html_original": str(orig_html),
            "sidecar_novo": str(stage_json),
            "html_novo": str(stage_html),
            "materias_despublicadas": snapshots_materias,
            "restantes": len(mantidas),
        })
        logger.info(
            f"{data}: {len(despublicadas)} despublicada(s), "
            f"{len(mantidas)} restante(s)"
        )

    manifest = {
        "preparado_em_utc": ts_operacao,
        "motivo": MOTIVO,
        "relatorio_auditoria": str(relatorio_path),
        "total_achados_relatorio": len(achados),
        "total_despublicadas": total_despublicadas,
        "ja_despublicadas": ja_despublicadas,
        "edicoes": edicoes,
        "duracao_preparo_s": round(time.monotonic() - inicio, 1),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    n_arquivos = 2 * len(edicoes) + 3  # sidecars + HTMLs + index + 2 diarios
    print()
    print(f"Edições afetadas:        {len(edicoes)}")
    print(f"Matérias a despublicar:  {total_despublicadas}")
    print(f"Já estavam fora do ar:   {len(ja_despublicadas)}")
    print(f"Arquivos a subir no R2:  {n_arquivos} "
          f"({len(edicoes)} sidecars + {len(edicoes)} HTMLs + index + 2 diários)")
    print(f"Manifest: {MANIFEST_PATH}")
    return 0


def _upload_bytes(
    r2: R2Client, conteudo: bytes, chave: str, content_type: str,
    metadados: dict | None = None, cache_control: str | None = None,
) -> str:
    """put_object direto (sem arquivo temporário)."""
    kwargs: dict = {
        "Bucket": r2.bucket,
        "Key": chave,
        "Body": conteudo,
        "ContentType": content_type,
    }
    if metadados is not None:
        kwargs["Metadata"] = metadados
    if cache_control is not None:
        kwargs["CacheControl"] = cache_control
    r2.client.put_object(**kwargs)
    return r2.url_publica(chave)


def _rollback(r2: R2Client, subidos: list[dict]) -> None:
    """Restaura no R2 os originais de tudo que já tinha subido."""
    logger.error(f"ROLLBACK de {len(subidos)} chave(s)...")
    for item in reversed(subidos):
        try:
            _upload_bytes(
                r2,
                Path(item["original"]).read_bytes(),
                item["chave"],
                item["content_type"],
                metadados=item.get("metadados"),
            )
            logger.info(f"  restaurado: {item['chave']}")
        except Exception as e:  # melhor esforço: continua restaurando o resto
            logger.error(f"  FALHA ao restaurar {item['chave']}: {e}")


def executar(r2: R2Client) -> int:
    """Estágio 2: sobe staging pro R2 com rollback; regenera índice/diários."""
    inicio = time.monotonic()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    subidos: list[dict] = []
    publicados: list[str] = []
    erros: list[str] = []

    try:
        for ed in manifest["edicoes"]:
            data = ed["data_edicao"]
            meta = {"data-edicao": data}
            _upload_bytes(
                r2, Path(ed["sidecar_novo"]).read_bytes(), ed["chave_json"],
                CONTENT_TYPE_JSON, metadados=meta,
            )
            subidos.append({
                "chave": ed["chave_json"], "original": ed["sidecar_original"],
                "content_type": CONTENT_TYPE_JSON, "metadados": meta,
            })
            _upload_bytes(
                r2, Path(ed["html_novo"]).read_bytes(), ed["chave_html"],
                CONTENT_TYPE_HTML, metadados=meta,
            )
            subidos.append({
                "chave": ed["chave_html"], "original": ed["html_original"],
                "content_type": CONTENT_TYPE_HTML, "metadados": meta,
            })
            publicados.extend([ed["chave_json"], ed["chave_html"]])
            logger.info(f"publicado: {data} (sidecar + html)")

        # Índice re-agregado dos sidecars já atualizados no R2.
        html_indice = gerar_indice(public_domain=r2.public_domain, r2=r2)
        _upload_bytes(
            r2, html_indice.encode("utf-8"), CHAVE_INDICE,
            CONTENT_TYPE_HTML, cache_control=CACHE_CONTROL_INDICE,
        )
        publicados.append(CHAVE_INDICE)
        publicados.extend(
            u.split(r2.public_domain + "/")[-1]
            for u in publicar_paginas_diarios(r2, public_domain=r2.public_domain)
        )
    except Exception as e:
        erros.append(f"{type(e).__name__}: {e}")
        logger.error(f"Falha no upload: {e}")
        _rollback(r2, subidos)
        logger.error("Operação ABORTADA; estado público restaurado.")
        return 1

    relatorio = {
        "executado_em_utc": datetime.now(timezone.utc).isoformat(),
        "motivo": MOTIVO,
        "manifest": manifest,
        "arquivos_publicados": publicados,
        "erros": erros,
        "duracao_upload_s": round(time.monotonic() - inicio, 1),
    }
    RELATORIO_EXECUCAO.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print()
    print(f"{manifest['total_despublicadas']} matérias despublicadas em "
          f"{len(manifest['edicoes'])} edições; {len(publicados)} arquivos "
          f"publicados no R2.")
    print(f"Relatório de execução: {RELATORIO_EXECUCAO}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Despublicação em lote (Fase 4, proteção a menores)",
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--preparar", action="store_true")
    grupo.add_argument("--executar", action="store_true")
    parser.add_argument(
        "--relatorio", type=Path, default=RELATORIO_AUDITORIA_DEFAULT,
    )
    args = parser.parse_args(argv)

    r2 = R2Client.from_env()
    if args.preparar:
        return preparar(args.relatorio, r2)
    return executar(r2)


if __name__ == "__main__":
    sys.exit(main())
