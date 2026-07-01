#!/usr/bin/env bash
# tunnel.sh — expone LicitaScan en internet con una URL FIJA, para usarla desde
# otra laptop (o el celular). Levanta la app local Y el túnel ngrok de una sola vez.
#
# Uso:   ./tunnel.sh
#   - Deja esta ventana abierta mientras la uses desde afuera.
#   - Ctrl+C baja la app y el túnel juntos.
#   - Esta PC debe quedar prendida (el tráfico sale por acá, IP de Perú → OECE ok).
#
# La app local NO pide login (tu .env no tiene SUPABASE), así que cualquiera con la
# URL entra. La URL es difícil de adivinar, pero es pública: no la compartas de más.
cd "$(dirname "$0")"

DOM="${LICITASCAN_TUNNEL_DOMAIN:-quintuple-blooper-freckles.ngrok-free.dev}"

# Evita choques con instancias previas (ngrok free = 1 sola sesión a la vez).
pkill -f 'uvicorn web_app' 2>/dev/null || true
pkill -f 'ngrok http'      2>/dev/null || true

echo "1/2 · Arrancando la app en localhost:8010 ..."
env WATCHFILES_FORCE_POLLING=1 .venv/bin/uvicorn web_app:app --port 8010 --reload \
    > /tmp/licitascan_uvicorn.log 2>&1 &
UVPID=$!

# Espera a que la app responda antes de abrir el túnel.
for _ in $(seq 1 40); do
  curl -s -o /dev/null http://localhost:8010/api/health && break
  sleep 0.5
done

trap 'kill "$UVPID" 2>/dev/null; pkill -f "ngrok http" 2>/dev/null; echo; echo "App y túnel detenidos."; exit 0' INT TERM

echo "2/2 · Abriendo el túnel público ..."
echo ""
echo "   ┌───────────────────────────────────────────────────────────────┐"
echo "   │  Abre esto en la otra laptop:                                 │"
echo "   │                                                               │"
echo "   │     https://$DOM"
echo "   │                                                               │"
echo "   │  Deja esta ventana abierta. Ctrl+C baja todo.                 │"
echo "   └───────────────────────────────────────────────────────────────┘"
echo ""

~/ngrok http 8010 --url="https://$DOM"

# Si ngrok termina (Ctrl+C), baja también la app.
kill "$UVPID" 2>/dev/null || true
echo "App y túnel detenidos."
