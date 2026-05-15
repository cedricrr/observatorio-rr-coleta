"""Testes do scripts.pdf_para_markdown (fase RED — implementação ainda não existe)."""

import fitz
import pytest

from scripts.pdf_para_markdown import pdf_para_markdown


def _pdf_com_texto(*paginas_texto: str) -> bytes:
    """Gera PDF de N páginas com o texto especificado em cada."""
    doc = fitz.open()
    for txt in paginas_texto:
        page = doc.new_page()
        page.insert_text((50, 100), txt)
    return doc.tobytes()


def _pdf_com_titulo_e_corpo() -> bytes:
    """Gera PDF com cabeçalho em fonte grande e corpo em fonte normal.

    pymupdf4llm detecta hierarquia via tamanho de fonte e gera
    marcadores ## ou ### no Markdown.
    """
    doc = fitz.open()
    page = doc.new_page()
    # Cabeçalho em fonte 24pt
    page.insert_text((50, 80), "PORTARIA TJRR N. 100", fontsize=24)
    # Corpo em fonte 11pt
    page.insert_text((50, 130), "O presidente do tribunal resolve...", fontsize=11)
    return doc.tobytes()


def test_pdf_uma_pagina_retorna_string_markdown():
    pdf_bytes = _pdf_com_texto("conteudo simples de teste")

    resultado = pdf_para_markdown(pdf_bytes)

    assert isinstance(resultado, str)
    assert len(resultado) > 0
    assert "conteudo simples de teste" in resultado


def test_pdf_multiplas_paginas_inclui_todo_conteudo():
    pdf_bytes = _pdf_com_texto(
        "primeira pagina texto",
        "segunda pagina texto",
        "terceira pagina texto",
    )

    resultado = pdf_para_markdown(pdf_bytes)

    assert "primeira pagina texto" in resultado
    assert "segunda pagina texto" in resultado
    assert "terceira pagina texto" in resultado


def test_unicode_preservado():
    pdf_bytes = _pdf_com_texto("Diário Eletrônico — São Luiz do Anauá")

    resultado = pdf_para_markdown(pdf_bytes)

    assert "Diário" in resultado
    assert "Eletrônico" in resultado
    assert "Anauá" in resultado


def test_bytes_vazios_levanta_valueerror():
    with pytest.raises(ValueError, match="vazi"):
        pdf_para_markdown(b"")


def test_bytes_invalidos_levantam_excecao():
    with pytest.raises(Exception):
        pdf_para_markdown(b"isso nao eh um PDF")


def test_hierarquia_preservada_via_markdown():
    pdf_bytes = _pdf_com_titulo_e_corpo()

    resultado = pdf_para_markdown(pdf_bytes)

    assert "PORTARIA TJRR N. 100" in resultado
    assert any(linha.startswith("#") for linha in resultado.splitlines())


def test_retorno_e_string_nao_bytes():
    pdf_bytes = _pdf_com_texto("teste")

    resultado = pdf_para_markdown(pdf_bytes)

    assert isinstance(resultado, str)
    assert not isinstance(resultado, bytes)
