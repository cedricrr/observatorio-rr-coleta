"""Conversão de PDFs em Markdown estruturado usando pymupdf4llm."""

from __future__ import annotations

import fitz
import pymupdf4llm


def pdf_para_markdown(pdf_bytes: bytes) -> str:
    """Converte um PDF (em bytes) para texto Markdown estruturado.

    Usa pymupdf4llm que detecta hierarquia (cabeçalhos via tamanho
    de fonte), preserva negrito, listas e estrutura geral. O output
    é texto puro em sintaxe Markdown padrão (#, ##, **, _, etc).

    Não inclui marcadores ===PAGE N=== (diferente de extrair_texto
    do Ciclo 8.1) — a entrada do pipeline editorial trabalha com
    Markdown puro.

    Levanta ValueError se bytes vazios. Levanta exceção do pymupdf
    (RuntimeError, FileDataError, etc) se bytes não formarem PDF
    válido.
    """
    if not pdf_bytes:
        raise ValueError("bytes vazios")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return pymupdf4llm.to_markdown(doc)
    finally:
        doc.close()
