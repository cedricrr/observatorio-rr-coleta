"""Testes do script de migração de domínio (Ciclo 12 — fase RED).

O script reescreve URLs `https://<antigo>/` → `https://<novo>/` em:
- HTMLs e sidecars JSON sob jornal/ no R2 (preservando os headers originais);
- campo url_r2 dos JSONs locais de data/diarios/ (text-replace, sem re-dump).
Idempotente: rodar duas vezes é no-op. Sem custo de API Anthropic.
"""

import json
from pathlib import Path

ANTIGO = "pub-xxx.r2.dev"
NOVO = "observatoriorr.com.br"


class _FakeBoto:
    """head_object mínimo lendo do dicionário de objetos do FakeR2."""

    def __init__(self, objetos: dict):
        self._objetos = objetos

    def head_object(self, Bucket: str, Key: str) -> dict:
        obj = self._objetos[Key]
        resposta = {
            "ContentType": obj["content_type"],
            "Metadata": obj.get("metadata") or {},
        }
        if obj.get("cache_control"):
            resposta["CacheControl"] = obj["cache_control"]
        return resposta


class FakeR2:
    """R2 em memória com a mesma interface usada pela migração.

    objetos: {chave: {"body": bytes, "content_type": str,
                      "cache_control": str|None, "metadata": dict|None}}
    """

    def __init__(self, objetos: dict):
        self.bucket = "observatorio-diarios"
        self.objetos = objetos
        self.client = _FakeBoto(objetos)
        self.uploads: list[str] = []

    def listar(self, prefixo: str) -> list[str]:
        return sorted(k for k in self.objetos if k.startswith(prefixo))

    def download_bytes(self, chave: str) -> bytes:
        return self.objetos[chave]["body"]

    def upload(self, caminho_local: Path, chave: str, metadados=None,
               content_type="application/pdf", cache_control=None) -> str:
        self.objetos[chave] = {
            "body": caminho_local.read_bytes(),
            "content_type": content_type,
            "cache_control": cache_control,
            "metadata": metadados,
        }
        self.uploads.append(chave)
        return f"https://{NOVO}/{chave}"


def _fake_r2_padrao() -> FakeR2:
    return FakeR2({
        "jornal/2026-06-01.html": {
            "body": f'<a href="https://{ANTIGO}/mprr/x.pdf">PDF</a>'.encode(),
            "content_type": "text/html; charset=utf-8",
            "cache_control": None,
            "metadata": {"data-edicao": "2026-06-01"},
        },
        "jornal/2026-06-01.json": {
            "body": json.dumps(
                {"url_jornal": f"https://{ANTIGO}/jornal/2026-06-01.html"}
            ).encode(),
            "content_type": "application/json",
            "cache_control": None,
            "metadata": None,
        },
        "jornal/index.html": {
            "body": f'<a href="https://{ANTIGO}/jornal/2026-06-01.html">e</a>'.encode(),
            "content_type": "text/html; charset=utf-8",
            "cache_control": "public, max-age=300",
            "metadata": None,
        },
        # PDF fora de jornal/ — nunca tocado (binário, sem URLs embutidas)
        "mprr/2026/06/2026-06-01-970.pdf": {
            "body": b"%PDF-1.4 binario",
            "content_type": "application/pdf",
            "cache_control": None,
            "metadata": None,
        },
    })


# =============================================================
# migrar_r2
# =============================================================


def test_migrar_r2_substitui_dominio_nos_htmls_e_sidecars():
    from scripts.migrar_dominio import migrar_r2
    r2 = _fake_r2_padrao()

    resumo = migrar_r2(ANTIGO, NOVO, r2)

    assert resumo["migrados"] == 3
    assert resumo["erros"] == 0
    assert (
        f'href="https://{NOVO}/mprr/x.pdf"'
        in r2.objetos["jornal/2026-06-01.html"]["body"].decode()
    )
    sidecar = json.loads(r2.objetos["jornal/2026-06-01.json"]["body"])
    assert sidecar["url_jornal"] == f"https://{NOVO}/jornal/2026-06-01.html"


def test_migrar_r2_preserva_content_type_cache_control_e_metadata():
    from scripts.migrar_dominio import migrar_r2
    r2 = _fake_r2_padrao()

    migrar_r2(ANTIGO, NOVO, r2)

    indice = r2.objetos["jornal/index.html"]
    assert indice["content_type"] == "text/html; charset=utf-8"
    assert indice["cache_control"] == "public, max-age=300"
    edicao = r2.objetos["jornal/2026-06-01.html"]
    assert edicao["cache_control"] is None
    assert edicao["metadata"] == {"data-edicao": "2026-06-01"}
    assert r2.objetos["jornal/2026-06-01.json"]["content_type"] == "application/json"


def test_migrar_r2_nao_toca_pdfs_fora_de_jornal():
    from scripts.migrar_dominio import migrar_r2
    r2 = _fake_r2_padrao()

    migrar_r2(ANTIGO, NOVO, r2)

    assert r2.objetos["mprr/2026/06/2026-06-01-970.pdf"]["body"] == b"%PDF-1.4 binario"
    assert "mprr/2026/06/2026-06-01-970.pdf" not in r2.uploads


def test_migrar_r2_e_idempotente():
    from scripts.migrar_dominio import migrar_r2
    r2 = _fake_r2_padrao()

    migrar_r2(ANTIGO, NOVO, r2)
    r2.uploads.clear()
    resumo = migrar_r2(ANTIGO, NOVO, r2)

    assert resumo["migrados"] == 0
    assert resumo["ja_ok"] == 3
    assert r2.uploads == []


def test_migrar_r2_dry_run_nao_escreve():
    from scripts.migrar_dominio import migrar_r2
    r2 = _fake_r2_padrao()

    resumo = migrar_r2(ANTIGO, NOVO, r2, dry_run=True)

    assert resumo["migrados"] == 3
    assert r2.uploads == []
    assert ANTIGO in r2.objetos["jornal/index.html"]["body"].decode()


def test_migrar_r2_erro_em_uma_chave_nao_derruba_as_demais():
    from scripts.migrar_dominio import migrar_r2
    r2 = _fake_r2_padrao()
    original_download = r2.download_bytes

    def _download(chave):
        if chave == "jornal/2026-06-01.html":
            raise RuntimeError("boom")
        return original_download(chave)

    r2.download_bytes = _download
    resumo = migrar_r2(ANTIGO, NOVO, r2)

    assert resumo["erros"] == 1
    assert resumo["migrados"] == 2


# =============================================================
# migrar_jsons (data/diarios/ local)
# =============================================================


def _criar_json_local(tmp_path: Path, fonte: str, nome: str, url_r2: str) -> Path:
    d = tmp_path / fonte
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{nome}.json"
    p.write_text(
        json.dumps({
            "orgao": fonte,
            "data_edicao": nome[:10],
            "url_r2": url_r2,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


def test_migrar_jsons_substitui_url_r2(tmp_path):
    from scripts.migrar_dominio import migrar_jsons
    p = _criar_json_local(
        tmp_path, "mprr", "2026-06-01-970",
        f"https://{ANTIGO}/mprr/2026/06/2026-06-01-970.pdf",
    )

    resumo = migrar_jsons(ANTIGO, NOVO, tmp_path)

    assert resumo["migrados"] == 1
    meta = json.loads(p.read_text(encoding="utf-8"))
    assert meta["url_r2"] == f"https://{NOVO}/mprr/2026/06/2026-06-01-970.pdf"


def test_migrar_jsons_preserva_formatacao_das_demais_linhas(tmp_path):
    """Text-replace puro: o diff do git deve ficar restrito à linha da URL."""
    from scripts.migrar_dominio import migrar_jsons
    p = _criar_json_local(
        tmp_path, "tjrr", "2026-06-01", f"https://{ANTIGO}/tjrr/x.pdf",
    )
    antes = p.read_text(encoding="utf-8")

    migrar_jsons(ANTIGO, NOVO, tmp_path)

    depois = p.read_text(encoding="utf-8")
    esperado = antes.replace(f"https://{ANTIGO}/", f"https://{NOVO}/")
    assert depois == esperado


def test_migrar_jsons_e_idempotente(tmp_path):
    from scripts.migrar_dominio import migrar_jsons
    _criar_json_local(tmp_path, "mprr", "2026-06-01-970", f"https://{ANTIGO}/x.pdf")

    migrar_jsons(ANTIGO, NOVO, tmp_path)
    resumo = migrar_jsons(ANTIGO, NOVO, tmp_path)

    assert resumo["migrados"] == 0
    assert resumo["ja_ok"] == 1


def test_migrar_jsons_dry_run_nao_escreve(tmp_path):
    from scripts.migrar_dominio import migrar_jsons
    p = _criar_json_local(tmp_path, "mprr", "2026-06-01-970", f"https://{ANTIGO}/x.pdf")
    antes = p.read_text(encoding="utf-8")

    resumo = migrar_jsons(ANTIGO, NOVO, tmp_path, dry_run=True)

    assert resumo["migrados"] == 1
    assert p.read_text(encoding="utf-8") == antes


# =============================================================
# CLI
# =============================================================


def test_main_alvo_jsons_nao_exige_credenciais_r2(tmp_path, monkeypatch):
    """--alvo jsons roda offline: não pode instanciar R2Client.from_env()."""
    from scripts.migrar_dominio import main
    for var in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                "R2_BUCKET_NAME", "R2_PUBLIC_DOMAIN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    _criar_json_local(tmp_path, "mprr", "2026-06-01-970", f"https://{ANTIGO}/x.pdf")

    rc = main([
        "--dominio-antigo", ANTIGO,
        "--dominio-novo", NOVO,
        "--alvo", "jsons",
        "--diarios-dir", str(tmp_path),
    ])

    assert rc == 0


def test_main_exige_dominios_diferentes():
    from scripts.migrar_dominio import main
    rc = main([
        "--dominio-antigo", ANTIGO,
        "--dominio-novo", ANTIGO,
        "--alvo", "jsons",
    ])
    assert rc != 0
