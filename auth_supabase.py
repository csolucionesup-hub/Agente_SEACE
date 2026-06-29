"""Verificación de tokens de Supabase Auth (login con Google).

El frontend hace el login con Google a través de Supabase; el navegador recibe un
``access_token`` (JWT). El backend lo valida preguntándole a Supabase quién es el
usuario (``GET {SUPABASE_URL}/auth/v1/user``), así no tenemos que manejar
algoritmos de firma ni rotación de llaves. El resultado se cachea en memoria unos
minutos para no llamar a Supabase en cada request.

Diseño desacoplado y testeable: ``verify`` es inyectable (token -> dict de usuario
o ``None``), de modo que los tests no tocan la red. Sin ``SUPABASE_URL`` +
``SUPABASE_ANON_KEY`` configurados, ``enabled`` es ``False`` y la app se comporta
como antes (útil en local/dev y para no romper los tests existentes).
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

DEFAULT_CACHE_TTL = 300.0

VerifyFn = Callable[[str], "dict[str, Any] | None"]


class SupabaseAuth:
    def __init__(
        self,
        url: str | None = None,
        anon_key: str | None = None,
        *,
        verify: VerifyFn | None = None,
        cache_ttl: float = DEFAULT_CACHE_TTL,
    ) -> None:
        self.url = (url if url is not None else os.getenv("SUPABASE_URL", "") or "").rstrip("/")
        self.anon_key = anon_key if anon_key is not None else os.getenv("SUPABASE_ANON_KEY", "") or ""
        self._verify = verify
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.anon_key)

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Devuelve ``{id, email}`` si el token es válido, si no ``None`` (con caché)."""
        token = (token or "").strip()
        if not token or not self.enabled:
            return None
        now = time.monotonic()
        cached = self._cache.get(token)
        if cached is not None and cached[0] > now:
            return cached[1]
        user = (self._verify or self._verify_remote)(token)
        if user:
            self._cache[token] = (now + self._cache_ttl, user)
        return user

    def _verify_remote(self, token: str) -> dict[str, Any] | None:
        import httpx

        try:
            response = httpx.get(
                f"{self.url}/auth/v1/user",
                headers={"Authorization": f"Bearer {token}", "apikey": self.anon_key},
                timeout=10.0,
            )
        except Exception:
            return None
        if response.status_code != 200:
            return None
        try:
            data = response.json()
        except Exception:
            return None
        user_id = str(data.get("id") or "")
        if not user_id:
            return None
        return {
            "id": user_id,
            "email": str(data.get("email") or ""),
            "name": str((data.get("user_metadata") or {}).get("full_name") or ""),
        }


def bearer_token(request: Any) -> str:
    """Extrae el token de la cabecera ``Authorization: Bearer <token>``."""
    header = request.headers.get("Authorization", "") if request is not None else ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""
