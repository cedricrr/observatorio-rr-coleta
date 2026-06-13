"""Testes de scripts/medir_supressao.py (Sessão 12 — bloqueador da supressão).

Medição SOMENTE LEITURA: varre texto/ no R2, aplica as regras do filtro
sensível (fonte única em search/api/app/filtro_sensivel.py, carregada
por caminho de arquivo) e grava relatório local em data/incidentes/
(gitignored). Nada sobe ao R2 nem ao Solr.
"""

import json
from datetime import datetime, timezone

from scripts.medir_supressao import (
    carregar_filtro,
    executar_medicao,
    gravar_relatorio,
    medir_documento,
)

AGORA = datetime(2026, 6, 12, 22, 0, 0, tzinfo=timezone.utc)


def _doc(orgao="mprr", data="2026-05-29", paginas=None):
    chave_pdf = f"{orgao}/2026/05/{data}.pdf"
    return {
        "versao": 1,
        "orgao": orgao,
        "data_edicao": data,
        "numero": None,
        "chave_pdf": chave_pdf,
        "sha256_pdf": "abc",
        "total_paginas": len(paginas or []),
        "paginas_vazias": 0,
        "paginas": paginas or [],
    }


# ---------------------------------------------------------------------------
# Fonte única das regras
# ---------------------------------------------------------------------------


def test_carregar_filtro_usa_o_modulo_da_api():
    # a medição mede EXATAMENTE o que o /indexar vai filtrar
    pagina_sensivel = carregar_filtro()
    assert pagina_sensivel(
        "estupro de vulnerável contra criança"
    ) == "crime_sexual_menor"
    assert pagina_sensivel("ata de registro de preços") is None


# ---------------------------------------------------------------------------
# Medição por documento
# ---------------------------------------------------------------------------


def test_medir_documento_aponta_paginas_sensiveis():
    pagina_sensivel = carregar_filtro()
    doc = _doc(paginas=[
        {"n": 1, "texto": "portaria de nomeação de servidor"},
        {"n": 2, "texto": "apurar estupro de vulnerável contra adolescente"},
        {"n": 3, "texto": "extrato de contrato administrativo"},
    ])

    achados = medir_documento(doc, pagina_sensivel)

    assert len(achados) == 1
    a = achados[0]
    assert a["chave_pdf"] == doc["chave_pdf"]
    assert a["pagina"] == 2
    assert a["regra"] == "crime_sexual_menor"
    assert "estupro" in a["trecho"]
    assert len(a["trecho"]) <= 200  # amostra curta no relatório local


def test_medir_documento_sem_match_retorna_vazio():
    pagina_sensivel = carregar_filtro()
    doc = _doc(paginas=[{"n": 1, "texto": "designação de plantão forense"}])
    assert medir_documento(doc, pagina_sensivel) == []


# ---------------------------------------------------------------------------
# Varredura no R2 (somente leitura)
# ---------------------------------------------------------------------------


def _mock_r2(mocker, docs):
    r2 = mocker.MagicMock()
    chaves = []
    blobs = {}
    for doc in docs:
        chave = "texto/" + doc["chave_pdf"][: -len(".pdf")] + ".json"
        chaves.append(chave)
        blobs[chave] = json.dumps(doc).encode("utf-8")
    r2.listar.side_effect = lambda prefixo: [c for c in chaves if c.startswith(prefixo)]
    r2.download_bytes.side_effect = lambda chave: blobs[chave]
    return r2


def test_executar_medicao_agrega_por_orgao_e_ano(mocker):
    docs = [
        _doc(orgao="mprr", data="2026-05-29", paginas=[
            {"n": 1, "texto": "abuso sexual de criança"},
            {"n": 2, "texto": "extrato de contrato"},
        ]),
        _doc(orgao="tjrr", data="2025-03-10", paginas=[
            {"n": 1, "texto": "pauta de julgamento cível"},
        ]),
    ]
    r2 = _mock_r2(mocker, docs)

    relatorio = executar_medicao(r2, agora=AGORA)

    r2.listar.assert_called_once_with("texto/")
    assert relatorio["total_documentos"] == 2
    assert relatorio["total_paginas"] == 3
    assert relatorio["total_paginas_suprimidas"] == 1
    assert relatorio["por_orgao_ano"]["mprr"]["2026"]["paginas"] == 2
    assert relatorio["por_orgao_ano"]["mprr"]["2026"]["suprimidas"] == 1
    assert relatorio["por_orgao_ano"]["tjrr"]["2025"]["suprimidas"] == 0
    assert relatorio["por_regra"] == {"crime_sexual_menor": 1}
    assert len(relatorio["achados"]) == 1
    assert relatorio["executado_em_utc"] == AGORA.isoformat()


def test_executar_medicao_filtra_por_orgao(mocker):
    docs = [
        _doc(orgao="mprr", paginas=[{"n": 1, "texto": "x"}]),
        _doc(orgao="tjrr", paginas=[{"n": 1, "texto": "x"}]),
    ]
    r2 = _mock_r2(mocker, docs)

    relatorio = executar_medicao(r2, orgao="tjrr", agora=AGORA)

    r2.listar.assert_called_once_with("texto/tjrr/")
    assert relatorio["total_documentos"] == 1


def test_executar_medicao_respeita_limite(mocker):
    docs = [_doc(data=f"2026-05-{d:02d}", paginas=[{"n": 1, "texto": "x"}])
            for d in range(1, 6)]
    r2 = _mock_r2(mocker, docs)

    relatorio = executar_medicao(r2, limite=2, agora=AGORA)

    assert relatorio["total_documentos"] == 2
    assert r2.download_bytes.call_count == 2


def test_executar_medicao_documento_corrompido_nao_quebra(mocker):
    docs = [_doc(paginas=[{"n": 1, "texto": "abuso sexual de criança"}])]
    r2 = _mock_r2(mocker, docs)
    chaves = ["texto/quebrado.json"] + r2.listar("texto/")
    r2.listar.side_effect = lambda prefixo: chaves
    blobs_ok = r2.download_bytes.side_effect
    r2.download_bytes.side_effect = (
        lambda chave: b"{nao-e-json" if chave == "texto/quebrado.json" else blobs_ok(chave)
    )

    relatorio = executar_medicao(r2, agora=AGORA)

    assert relatorio["total_documentos"] == 1
    assert relatorio["documentos_com_erro"] == ["texto/quebrado.json"]


# ---------------------------------------------------------------------------
# Relatório local (gitignored)
# ---------------------------------------------------------------------------


def test_gravar_relatorio_em_data_incidentes(tmp_path):
    relatorio = {"executado_em_utc": AGORA.isoformat(), "achados": []}

    caminho = gravar_relatorio(relatorio, dir_destino=tmp_path, agora=AGORA)

    assert caminho.parent == tmp_path
    assert caminho.name == "medicao-supressao-20260612T220000Z.json"
    gravado = json.loads(caminho.read_text(encoding="utf-8"))
    assert gravado == relatorio
