"""Testes do R2Client (fase RED — implementação ainda não existe)."""

import pytest
from botocore.exceptions import ClientError

from scripts.r2_client import R2Client


def _make_client(mocker):
    """Constrói R2Client com boto3.client mockado; devolve (r2, fake_s3)."""
    fake_s3 = mocker.MagicMock()
    mocker.patch("boto3.client", return_value=fake_s3)
    r2 = R2Client(
        account_id="acct-fake",
        access_key="AKIA-fake",
        secret_key="secret-fake",
        bucket="observatorio-diarios",
        public_domain="pub-xxx.r2.dev",
    )
    return r2, fake_s3


def test_from_env_le_5_variaveis_e_constroi_cliente(monkeypatch, mocker, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "AKIA-key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "super-secret")
    monkeypatch.setenv("R2_BUCKET_NAME", "observatorio-diarios")
    monkeypatch.setenv("R2_PUBLIC_DOMAIN", "pub-xxx.r2.dev")

    boto_client = mocker.patch("boto3.client", return_value=mocker.MagicMock())

    R2Client.from_env()

    boto_client.assert_called_once()
    kwargs = boto_client.call_args.kwargs
    assert "acct-123" in kwargs["endpoint_url"]
    assert kwargs["region_name"] == "auto"
    assert kwargs["aws_access_key_id"] == "AKIA-key"


_TODAS_VARS = {
    "R2_ACCOUNT_ID": "acct-123",
    "R2_ACCESS_KEY_ID": "AKIA-key",
    "R2_SECRET_ACCESS_KEY": "super-secret",
    "R2_BUCKET_NAME": "observatorio-diarios",
    "R2_PUBLIC_DOMAIN": "pub-xxx.r2.dev",
}


@pytest.mark.parametrize("ausente", list(_TODAS_VARS.keys()))
def test_from_env_levanta_runtime_error_se_falta_variavel(monkeypatch, tmp_path, ausente):
    monkeypatch.chdir(tmp_path)
    for var, valor in _TODAS_VARS.items():
        if var == ausente:
            monkeypatch.delenv(var, raising=False)
        else:
            monkeypatch.setenv(var, valor)

    with pytest.raises(RuntimeError) as exc_info:
        R2Client.from_env()

    assert ausente in str(exc_info.value)


def test_existe_retorna_true_quando_head_object_sucede(mocker):
    r2, fake_s3 = _make_client(mocker)
    fake_s3.head_object.return_value = {}

    assert r2.existe("alguma/chave.pdf") is True
    fake_s3.head_object.assert_called_once_with(
        Bucket="observatorio-diarios", Key="alguma/chave.pdf"
    )


def test_existe_retorna_false_em_404(mocker):
    r2, fake_s3 = _make_client(mocker)
    fake_s3.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
    )

    assert r2.existe("nao/existe.pdf") is False


def test_existe_propaga_erros_que_nao_sao_404(mocker):
    r2, fake_s3 = _make_client(mocker)
    fake_s3.head_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "HeadObject"
    )

    with pytest.raises(ClientError):
        r2.existe("forbidden.pdf")


def test_upload_chama_put_object_com_content_type_pdf(mocker, tmp_path):
    r2, fake_s3 = _make_client(mocker)
    arquivo = tmp_path / "teste.pdf"
    arquivo.write_bytes(b"PDF-content")

    r2.upload(arquivo, "k/x.pdf")

    fake_s3.put_object.assert_called_once()
    kwargs = fake_s3.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "observatorio-diarios"
    assert kwargs["Key"] == "k/x.pdf"
    assert kwargs["ContentType"] == "application/pdf"
    assert kwargs["Body"] == b"PDF-content"
    assert "Metadata" not in kwargs or kwargs["Metadata"] == {}


def test_upload_aceita_metadados_customizados(mocker, tmp_path):
    r2, fake_s3 = _make_client(mocker)
    arquivo = tmp_path / "teste.pdf"
    arquivo.write_bytes(b"PDF-content")

    r2.upload(
        arquivo,
        "k.pdf",
        metadados={"sha256": "abc", "data": "2026-04-30"},
    )

    kwargs = fake_s3.put_object.call_args.kwargs
    assert kwargs["Metadata"] == {"sha256": "abc", "data": "2026-04-30"}


def test_upload_retorna_url_publica(mocker, tmp_path):
    r2, _ = _make_client(mocker)
    arquivo = tmp_path / "teste.pdf"
    arquivo.write_bytes(b"PDF-content")

    url = r2.upload(arquivo, "edicoes/2026/x.pdf")

    assert url == "https://pub-xxx.r2.dev/edicoes/2026/x.pdf"


def test_url_publica_formato_correto(mocker):
    r2, _ = _make_client(mocker)

    assert r2.url_publica("a/b/c.pdf") == "https://pub-xxx.r2.dev/a/b/c.pdf"


def test_upload_aceita_content_type_customizado(mocker, tmp_path):
    """upload() deve aceitar content_type kwarg para arquivos não-PDF (HTML, etc).

    Necessário para Ciclo 9.4 (publicação online do jornal em HTML).
    Default continua sendo application/pdf — coberto pelo teste
    test_upload_chama_put_object_com_content_type_pdf acima.
    """
    r2, fake_s3 = _make_client(mocker)
    arquivo = tmp_path / "jornal.html"
    arquivo.write_text("<html></html>")

    r2.upload(arquivo, "jornal/2026-05-15.html", content_type="text/html; charset=utf-8")

    kwargs = fake_s3.put_object.call_args.kwargs
    assert kwargs["ContentType"] == "text/html; charset=utf-8"
    assert kwargs["Key"] == "jornal/2026-05-15.html"


def test_upload_aceita_cache_control(mocker, tmp_path):
    """upload() deve aceitar cache_control kwarg, mapeado para CacheControl no put_object.

    Necessário para Ciclo 10.2 — índice com max-age curto contra stale CDN.
    """
    r2, fake_s3 = _make_client(mocker)
    arquivo = tmp_path / "index.html"
    arquivo.write_text("<html></html>")

    r2.upload(
        arquivo,
        "jornal/index.html",
        content_type="text/html; charset=utf-8",
        cache_control="public, max-age=300",
    )

    kwargs = fake_s3.put_object.call_args.kwargs
    assert kwargs["CacheControl"] == "public, max-age=300"


def test_upload_sem_cache_control_nao_inclui_header(mocker, tmp_path):
    """Sem cache_control, put_object não recebe CacheControl (default imutável p/ PDFs)."""
    r2, fake_s3 = _make_client(mocker)
    arquivo = tmp_path / "x.pdf"
    arquivo.write_bytes(b"PDF")

    r2.upload(arquivo, "k/x.pdf")

    kwargs = fake_s3.put_object.call_args.kwargs
    assert "CacheControl" not in kwargs


# ---------------------------------------------------------------------------
# Timeouts e retries (Ciclo 10.7b)
# ---------------------------------------------------------------------------
# Lote 2025 sofreu hangs também após uploads ao R2 (boto3/botocore), mesma
# assinatura dos hangs no Anthropic SDK (Ciclo 10.7a). Defaults de botocore
# (connect_timeout=60s, read_timeout=60s, max_attempts=3) deixam pendurar.
# Ajuste paralelo ao 10.7a: connect curto + read médio + retries generosos.


def test_default_timeout_constants_expostas():
    assert R2Client.DEFAULT_CONNECT_TIMEOUT_SECONDS == 10
    assert R2Client.DEFAULT_READ_TIMEOUT_SECONDS == 120
    assert R2Client.DEFAULT_MAX_ATTEMPTS == 5


def test_boto3_client_recebe_config_com_timeouts_defaults(mocker):
    boto_client = mocker.patch("boto3.client", return_value=mocker.MagicMock())
    R2Client(
        account_id="a", access_key="k", secret_key="s",
        bucket="b", public_domain="p",
    )
    config = boto_client.call_args.kwargs["config"]
    assert config.connect_timeout == 10
    assert config.read_timeout == 120


def test_boto3_client_recebe_config_com_max_attempts(mocker):
    boto_client = mocker.patch("boto3.client", return_value=mocker.MagicMock())
    R2Client(
        account_id="a", access_key="k", secret_key="s",
        bucket="b", public_domain="p",
    )
    config = boto_client.call_args.kwargs["config"]
    assert config.retries["max_attempts"] == 5


def test_boto3_client_preserva_signature_version_s3v4(mocker):
    # Regressão: o Config existente já fixava signature_version; o novo
    # não pode descartá-lo (R2 exige S3v4).
    boto_client = mocker.patch("boto3.client", return_value=mocker.MagicMock())
    R2Client(
        account_id="a", access_key="k", secret_key="s",
        bucket="b", public_domain="p",
    )
    config = boto_client.call_args.kwargs["config"]
    assert config.signature_version == "s3v4"
