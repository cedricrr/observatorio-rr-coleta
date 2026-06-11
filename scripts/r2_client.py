"""Cliente Cloudflare R2 (S3-compatible) usado pelo coletor."""

from __future__ import annotations

import os
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv


_VARS_NECESSARIAS = (
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
    "R2_PUBLIC_DOMAIN",
)


class R2Client:
    """Wrapper boto3 para operações no bucket do Observatório."""

    DEFAULT_CONNECT_TIMEOUT_SECONDS = 10
    DEFAULT_READ_TIMEOUT_SECONDS = 120
    DEFAULT_MAX_ATTEMPTS = 5

    def __init__(
        self,
        account_id: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        public_domain: str,
    ) -> None:
        self.account_id = account_id
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.public_domain = public_domain
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                connect_timeout=self.DEFAULT_CONNECT_TIMEOUT_SECONDS,
                read_timeout=self.DEFAULT_READ_TIMEOUT_SECONDS,
                retries={
                    "max_attempts": self.DEFAULT_MAX_ATTEMPTS,
                    "mode": "adaptive",
                },
            ),
        )

    @classmethod
    def from_env(cls) -> "R2Client":
        """Constrói um R2Client lendo credenciais do ambiente (carrega .env do cwd se existir)."""
        load_dotenv(Path.cwd() / ".env")
        faltando = [v for v in _VARS_NECESSARIAS if not os.environ.get(v)]
        if faltando:
            raise RuntimeError(
                f"Variáveis de ambiente faltando: {', '.join(faltando)}"
            )
        return cls(
            account_id=os.environ["R2_ACCOUNT_ID"],
            access_key=os.environ["R2_ACCESS_KEY_ID"],
            secret_key=os.environ["R2_SECRET_ACCESS_KEY"],
            bucket=os.environ["R2_BUCKET_NAME"],
            public_domain=os.environ["R2_PUBLIC_DOMAIN"],
        )

    def existe(self, chave: str) -> bool:
        """True se a chave existe no bucket; False em 404; propaga outros erros."""
        try:
            self.client.head_object(Bucket=self.bucket, Key=chave)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "404":
                return False
            raise

    def upload(
        self,
        caminho_local: Path,
        chave: str,
        metadados: dict[str, str] | None = None,
        content_type: str = "application/pdf",
        cache_control: str | None = None,
    ) -> str:
        """Sobe o arquivo com o ContentType informado (default PDF).

        Se cache_control for fornecido, vira o header Cache-Control do objeto
        (ex.: índice com max-age curto). Sem ele, o objeto não recebe o header
        e fica sujeito ao cache padrão do CDN — adequado a PDFs imutáveis.
        """
        kwargs: dict = {
            "Bucket": self.bucket,
            "Key": chave,
            "Body": caminho_local.read_bytes(),
            "ContentType": content_type,
        }
        if metadados is not None:
            kwargs["Metadata"] = metadados
        if cache_control is not None:
            kwargs["CacheControl"] = cache_control
        self.client.put_object(**kwargs)
        return self.url_publica(chave)

    def url_publica(self, chave: str) -> str:
        """URL pública do objeto via domínio CDN configurado."""
        return f"https://{self.public_domain}/{chave}"

    def listar(self, prefixo: str) -> list[str]:
        """Lista todas as chaves do bucket sob o prefixo, paginando."""
        paginator = self.client.get_paginator("list_objects_v2")
        chaves: list[str] = []
        for pagina in paginator.paginate(Bucket=self.bucket, Prefix=prefixo):
            chaves.extend(obj["Key"] for obj in pagina.get("Contents", []))
        return chaves

    def download_bytes(self, chave: str) -> bytes:
        """Baixa o objeto da chave informada e retorna os bytes.

        Levanta botocore.exceptions.ClientError se a chave não existe
        ou se houver erro de acesso ao R2.
        """
        resposta = self.client.get_object(Bucket=self.bucket, Key=chave)
        return resposta["Body"].read()
