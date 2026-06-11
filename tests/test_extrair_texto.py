"""Testes do scripts.extrair_texto."""

import fitz
import pytest

from scripts.extrair_texto import extrair_paginas, extrair_texto


def _pdf_com_texto(*paginas_texto: str) -> bytes:
    """Gera PDF de N páginas com o texto especificado em cada."""
    doc = fitz.open()
    for txt in paginas_texto:
        page = doc.new_page()
        page.insert_text((50, 100), txt)
    return doc.tobytes()


def test_pdf_uma_pagina_retorna_marcador_e_texto():
    pdf_bytes = _pdf_com_texto("conteudo simples")

    resultado = extrair_texto(pdf_bytes)

    assert "===PAGE 1===" in resultado
    assert "conteudo simples" in resultado
    assert "===PAGE 2===" not in resultado


def test_pdf_tres_paginas_marcadores_em_ordem():
    pdf_bytes = _pdf_com_texto("primeira", "segunda", "terceira")

    resultado = extrair_texto(pdf_bytes)

    pos1 = resultado.index("===PAGE 1===")
    pos2 = resultado.index("===PAGE 2===")
    pos3 = resultado.index("===PAGE 3===")
    assert pos1 < pos2 < pos3
    assert pos1 < resultado.index("primeira") < pos2
    assert pos2 < resultado.index("segunda") < pos3
    assert pos3 < resultado.index("terceira")


def test_pdf_pagina_em_branco_inclui_marcador_mas_texto_vazio():
    doc = fitz.open()
    doc.new_page()  # em branco
    page2 = doc.new_page()
    page2.insert_text((50, 100), "página dois")
    pdf_bytes = doc.tobytes()

    resultado = extrair_texto(pdf_bytes)

    assert "===PAGE 1===" in resultado
    assert "===PAGE 2===" in resultado
    assert "página dois" in resultado


def test_pdf_caracteres_unicode_preservados():
    pdf_bytes = _pdf_com_texto("Diário Eletrônico — São Luiz do Anauá")

    resultado = extrair_texto(pdf_bytes)

    assert "Diário" in resultado
    assert "Eletrônico" in resultado
    assert "Anauá" in resultado


def test_bytes_vazios_levanta_excecao():
    with pytest.raises(Exception):
        extrair_texto(b"")


def test_bytes_invalidos_nao_pdf_levantam_excecao():
    with pytest.raises(Exception):
        extrair_texto(b"isso nao eh um PDF, eh texto puro")


def test_marcadores_na_propria_linha():
    pdf_bytes = _pdf_com_texto("A", "B")

    resultado = extrair_texto(pdf_bytes)
    linhas = resultado.splitlines()

    assert "===PAGE 1===" in linhas
    assert "===PAGE 2===" in linhas


def test_pdf_grande_paginas_numeradas_corretamente():
    pdf_bytes = _pdf_com_texto(*[f"pagina {i}" for i in range(1, 11)])

    resultado = extrair_texto(pdf_bytes)

    assert "===PAGE 10===" in resultado
    assert "===PAGE 11===" not in resultado
    assert "===PAGE 0===" not in resultado


def test_extrair_paginas_retorna_lista_por_pagina():
    pdf_bytes = _pdf_com_texto("primeira", "segunda")

    paginas = extrair_paginas(pdf_bytes)

    assert len(paginas) == 2
    assert "primeira" in paginas[0]
    assert "segunda" in paginas[1]


def test_extrair_paginas_pagina_em_branco_vira_string_vazia():
    doc = fitz.open()
    doc.new_page()  # em branco
    page2 = doc.new_page()
    page2.insert_text((50, 100), "página dois")
    pdf_bytes = doc.tobytes()

    paginas = extrair_paginas(pdf_bytes)

    assert len(paginas) == 2
    assert paginas[0].strip() == ""
    assert "página dois" in paginas[1]


def test_extrair_paginas_preserva_unicode():
    pdf_bytes = _pdf_com_texto("Diário Eletrônico — São Luiz do Anauá")

    paginas = extrair_paginas(pdf_bytes)

    assert "Diário" in paginas[0]
    assert "Anauá" in paginas[0]


def test_extrair_paginas_bytes_invalidos_levanta_excecao():
    with pytest.raises(Exception):
        extrair_paginas(b"isso nao eh um PDF")


def test_extrair_texto_equivale_a_join_de_extrair_paginas():
    pdf_bytes = _pdf_com_texto("um", "dois", "três")

    paginas = extrair_paginas(pdf_bytes)
    esperado = "".join(
        f"===PAGE {n}===\n{texto}\n" for n, texto in enumerate(paginas, start=1)
    )

    assert extrair_texto(pdf_bytes) == esperado
