"""Extração de texto de PDFs no formato paginado do Observatório."""

from __future__ import annotations

import fitz


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
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        partes: list[str] = []
        for n, page in enumerate(doc, start=1):
            partes.append(f"===PAGE {n}===\n{page.get_text()}\n")
        return "".join(partes)
    finally:
        doc.close()
