#!/usr/bin/env bash
# dev.sh — arranca LicitaScan en local con auto-reload (desarrollo).
# Uso: ./dev.sh   (o: bash dev.sh). Ctrl+C para detenerlo.
#
# - Mata cualquier uvicorn previo (libera el puerto 8010).
# - WATCHFILES_FORCE_POLLING=1: necesario en WSL cuando se edita desde Windows
#   (inotify no avisa de esos cambios; el sondeo sí), para que --reload funcione.
cd "$(dirname "$0")"
pkill -f 'uvicorn web_app' 2>/dev/null || true
echo "Arrancando LicitaScan en http://localhost:8010 (auto-reload activo)..."
exec env WATCHFILES_FORCE_POLLING=1 .venv/bin/uvicorn web_app:app --port 8010 --reload
