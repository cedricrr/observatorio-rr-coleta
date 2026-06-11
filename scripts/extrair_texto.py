"""Extração de texto de PDFs no formato paginado do Observatório."""

from __future__ import annotations

import fitz


def extrair_paginas(pdf_bytes: bytes) -> list[str]:
    """Extrai o texto de um PDF, uma string por página (índice 0 = página 1).

    Páginas em branco viram strings vazias. Acentuação e caracteres
    unicode são preservados.

    Levanta exceção se os bytes não formarem um PDF válido.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return [page.get_text() for page in doc]
    finally:
        doc.close()


def extrair_texto(pdf_bytes: bytes) -> str:
    """Extrai texto de um PDF e retorna paginado.

    Recebe bytes de um PDF e devolve string no formato:

        ===PAGE 1===
        (texto da página 1)
        ===PAGE 2===
        (texto da página 2)

    Cada marcador aparece em linha própria, com N começando em 1.
    Páginas em branco mantêm o marcador (sem texto).
    Acentuação e caracteres unicode são preservados.

    Levanta exceção se os bytes não formarem um PDF válido.
    """
    return "".join(
        f"===PAGE {n}===\n{texto}\n"
        for n, texto in enumerate(extrair_paginas(pdf_bytes), start=1)
    )
