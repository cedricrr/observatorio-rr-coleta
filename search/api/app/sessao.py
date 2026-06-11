"""Token de sessão freemium.

Não é autenticação de verdade: é o gate de lead capture. Um token
assinado (itsdangerous) emitido após o cadastro libera a lista completa
de resultados por ~180 dias. Vai em localStorage + header X-Sessao —
sem cookies, sem problemas de SameSite/CORS-credentials.
"""

from __future__ import annotations

from itsdangerous import BadSignature, URLSafeTimedSerializer

VALIDADE_SEGUNDOS = 180 * 24 * 60 * 60

_SALT = "sessao-busca-v1"


def _serializer(segredo: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(segredo, salt=_SALT)


def emitir_token(segredo: str) -> str:
    """Emite um token de sessão assinado (payload mínimo, sem PII)."""
    return _serializer(segredo).dumps({"v": 1})


def verificar_token(token: str, segredo: str) -> bool:
    """True se o token é íntegro, do mesmo segredo e dentro da validade."""
    if not token:
        return False
    try:
        _serializer(segredo).loads(token, max_age=VALIDADE_SEGUNDOS)
        return True
    except BadSignature:
        return False
