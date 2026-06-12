"""Testes da auditoria histórica de matérias publicadas (Fase 4 do
incidente 2026-06-10 — proteção a menores, ECA art. 143)."""

from __future__ import annotations

from scripts.auditar_historico import auditar_sidecar


def _sidecar(materias: list[dict]) -> dict:
    return {
        "versao": 1,
        "data_edicao": "2026-02-24",
        "data_formatada": "24 de fevereiro de 2026",
        "url_jornal": "https://example.com/jornal/2026-02-24.html",
        "total_relevantes": len(materias),
        "materias": materias,
    }


def _materia_dict(manchete: str, resumo: str, tags: list[str] | None = None) -> dict:
    return {
        "orgao": "MPRR",
        "tipo": "PORTARIA",
        "categoria": "Investigações e inquéritos",
        "manchete": manchete,
        "resumo": resumo,
        "valor_rs": None,
        "tags": tags or [],
        "pdf_url": "https://example.com/x.pdf",
        "pagina": None,
    }


def test_auditar_sidecar_acha_materia_sensivel():
    sidecar = _sidecar([
        _materia_dict(
            "MP apura caso em Bonfim",
            "Procedimento apura estupro de vulnerável contra adolescente.",
        ),
        _materia_dict(
            "MPRR contrata limpeza por R$ 200 mil",
            "Contrato de limpeza predial firmado pelo MPRR.",
        ),
    ])

    achados = auditar_sidecar(sidecar)

    assert len(achados) == 1
    assert achados[0]["data_edicao"] == "2026-02-24"
    assert achados[0]["manchete"] == "MP apura caso em Bonfim"
    assert achados[0]["termo"] == "estupro"
    assert achados[0]["orgao"] == "MPRR"


def test_auditar_sidecar_sem_sensiveis_retorna_vazio():
    sidecar = _sidecar([
        _materia_dict(
            "TJRR contrata frota por R$ 1,15 milhão",
            "Contrato de gestão de frota por 60 meses.",
        ),
    ])
    assert auditar_sidecar(sidecar) == []


def test_auditar_sidecar_vazio_retorna_vazio():
    assert auditar_sidecar(_sidecar([])) == []


def test_auditar_sidecar_casa_por_tags():
    sidecar = _sidecar([
        _materia_dict(
            "MP instaura procedimento em comarca do interior",
            "Procedimento administrativo instaurado.",
            tags=["estupro de vulnerável", "MPRR"],
        ),
    ])
    achados = auditar_sidecar(sidecar)
    assert len(achados) == 1


def test_auditar_sidecar_nao_modifica_entrada():
    materias = [
        _materia_dict(
            "MP apura caso",
            "Apura estupro de vulnerável.",
        ),
    ]
    sidecar = _sidecar(list(materias))
    antes = [dict(m) for m in sidecar["materias"]]

    auditar_sidecar(sidecar)

    assert sidecar["materias"] == antes
