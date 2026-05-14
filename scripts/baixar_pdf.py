"""Download de PDFs do R2 com validação básica."""

from __future__ import annotations

from scripts.r2_client import R2Client


def baixar_pdf_do_r2(chave: str, r2: R2Client) -> bytes:
    """Baixa um PDF do R2 pela chave e retorna seus bytes.

    Valida que a chave não é vazia/só-espaços e que os bytes
    retornados parecem ser um PDF válido (começam com %PDF).

    Levanta:
    - ValueError: chave vazia, bytes vazios, ou bytes não começam
      com magic number de PDF.
    - Qualquer exceção do R2Client é propagada (ClientError,
      NoSuchKey, RuntimeError, etc).
    """
    if not chave or not chave.strip():
        raise ValueError("chave vazia ou só espaços")

    pdf_bytes = r2.download_bytes(chave)

    if not pdf_bytes:
        raise ValueError("bytes vazios retornados pelo R2")
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("bytes não são PDF")

    return pdf_bytes
