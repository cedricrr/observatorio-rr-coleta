"""Testes da despublicação em lote (Fase 4 do incidente 2026-06-10)."""

from __future__ import annotations

from scripts.despublicar_lote import (
    montar_sidecar_sem_despublicadas,
    particionar_materias,
)


def _materia_dict(manchete: str, resumo: str) -> dict:
    return {
        "orgao": "MPRR",
        "tipo": "PORTARIA",
        "categoria": "Investigações e inquéritos",
        "manchete": manchete,
        "resumo": resumo,
        "valor_rs": None,
        "tags": [],
        "pdf_url": "https://example.com/x.pdf",
        "pagina": None,
    }


SENSIVEL = _materia_dict(
    "MP apura caso em Bonfim",
    "Apura estupro de vulnerável contra adolescente de 13 anos.",
)
NORMAL = _materia_dict(
    "MPRR contrata limpeza por R$ 200 mil",
    "Contrato de limpeza predial firmado pelo MPRR.",
)


def _sidecar(materias: list[dict]) -> dict:
    return {
        "versao": 1,
        "data_edicao": "2026-02-24",
        "data_formatada": "24 de fevereiro de 2026",
        "url_jornal": "https://example.com/jornal/2026-02-24.html",
        "total_relevantes": len(materias),
        "materias": materias,
    }


def test_particionar_separa_sensivel_de_normal():
    mantidas, despublicadas = particionar_materias(_sidecar([SENSIVEL, NORMAL]))

    assert [m["manchete"] for m in mantidas] == [NORMAL["manchete"]]
    assert len(despublicadas) == 1
    idx, materia, termo = despublicadas[0]
    assert idx == 0
    assert materia["manchete"] == SENSIVEL["manchete"]
    assert termo == "estupro"


def test_particionar_preserva_ordem_das_mantidas():
    outra = _materia_dict("TJRR reforma prédio", "Obra de reforma predial.")
    mantidas, despublicadas = particionar_materias(
        _sidecar([NORMAL, SENSIVEL, outra]),
    )
    assert [m["manchete"] for m in mantidas] == [
        NORMAL["manchete"], outra["manchete"],
    ]
    assert [d[0] for d in despublicadas] == [1]


def test_particionar_sem_sensiveis():
    mantidas, despublicadas = particionar_materias(_sidecar([NORMAL]))
    assert len(mantidas) == 1
    assert despublicadas == []


def test_montar_sidecar_atualiza_contagem_e_preserva_cabecalho():
    original = _sidecar([SENSIVEL, NORMAL])
    mantidas, _ = particionar_materias(original)

    novo = montar_sidecar_sem_despublicadas(original, mantidas)

    assert novo["total_relevantes"] == 1
    assert novo["materias"] == mantidas
    assert novo["versao"] == original["versao"]
    assert novo["data_edicao"] == original["data_edicao"]
    assert novo["url_jornal"] == original["url_jornal"]
    # original não é modificado (pureza)
    assert original["total_relevantes"] == 2
    assert len(original["materias"]) == 2
