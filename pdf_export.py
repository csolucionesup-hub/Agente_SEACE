"""Genera un PDF con buen formato (logo + colores) del expediente de una obra.

Renderiza un HTML con estilos a PDF usando Playwright (Chromium headless), que soporta
color, imágenes y CSS completo. Local-only: necesita el navegador (en datacenter falla).
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from html import escape as _h
from pathlib import Path
from typing import Any

BRAND = "#0b43a5"
BRAND_2 = "#0ea36a"

_CSS = """
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Arial, sans-serif; color: #111827; margin: 0; font-size: 12px; }
.header { background: """ + BRAND + """; color: #fff; padding: 22px 30px; display: flex; align-items: center; gap: 16px; }
.header img { height: 46px; background: #fff; border-radius: 10px; padding: 6px; }
.header .brand { font-size: 20px; font-weight: 700; line-height: 1.1; }
.header .sub { font-size: 12px; opacity: .85; }
.wrap { padding: 24px 30px; }
.eyebrow { color: """ + BRAND_2 + """; font-weight: 700; font-size: 11px; letter-spacing: .5px; text-transform: uppercase; }
h1 { font-size: 22px; margin: 4px 0 6px; }
.desc { color: #374151; margin: 0 0 12px; }
.badges { margin-bottom: 18px; }
.badge { display: inline-block; background: #eef2ff; color: """ + BRAND + """; border-radius: 999px; padding: 3px 11px; font-size: 11px; font-weight: 600; margin-right: 6px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 18px; }
.card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 12px 14px; }
.card .k { color: #6b7280; font-size: 11px; }
.card .v { font-weight: 700; font-size: 14px; margin-top: 2px; }
.section { margin-bottom: 18px; }
.section h2 { font-size: 14px; color: """ + BRAND + """; border-bottom: 2px solid #e5e7eb; padding-bottom: 6px; margin: 0 0 10px; }
.reco { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 12px; padding: 12px 14px; }
.reco .razon { color: #6b7280; font-size: 11px; margin-top: 4px; }
.timeline { list-style: none; margin: 0; padding: 0; }
.timeline li { position: relative; padding: 0 0 12px 22px; }
.timeline li::before { content: ''; position: absolute; left: 4px; top: 3px; width: 10px; height: 10px; border-radius: 50%; background: #cbd5e1; }
.timeline li.completed::before { background: """ + BRAND_2 + """; }
.timeline li.current::before { background: """ + BRAND + """; }
.timeline .t { font-weight: 700; }
.timeline .m { color: #6b7280; font-size: 11px; }
.footer { border-top: 1px solid #e5e7eb; margin: 8px 30px 0; padding: 12px 0; color: #9ca3af; font-size: 10px; display: flex; justify-content: space-between; }
.muted { color: #6b7280; }
"""


def _money(amount: Any, currency: str = "PEN") -> str:
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return "—"
    sym = "S/" if (currency or "PEN") in ("PEN", "") else str(currency)
    return f"{sym} {n:,.0f}"


def _date(value: Any) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except Exception:
        return str(value)[:10]


def logo_data_uri(static_dir: str | Path) -> str:
    for name in ("licitascan-logo-cropped.jpg", "licitascan-logo.jpg"):
        p = Path(static_dir) / name
        if p.exists():
            b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
    return ""


def build_expediente_html(opportunity: dict[str, Any], events: list[dict[str, Any]],
                          timeline: list[dict[str, Any]], logo_uri: str = "",
                          generated_at: str = "") -> str:
    """Arma el HTML del reporte. Función pura (testeable); no toca Playwright."""
    o = opportunity or {}
    proc = _h(str(o.get("process_code") or "—"))
    desc = _h(str(o.get("description") or ""))
    badges = "".join(
        f'<span class="badge">{_h(str(b))}</span>'
        for b in [o.get("stage"), o.get("outcome"), o.get("commercial_score") is not None and f"Score {o.get('commercial_score')}" or ""]
        if b
    )
    razones = " · ".join(_h(str(r)) for r in (o.get("commercial_reasons") or [])) or "Sin razones comerciales calculadas"
    reco = _h(str(o.get("recommended_action") or "Revisar el expediente y decidir seguimiento."))

    if o.get("winner_name"):
        intel = f"""<div class="grid">
          <div class="card"><div class="k">Ganador</div><div class="v">{_h(str(o.get('winner_name')))}</div></div>
          <div class="card"><div class="k">RUC</div><div class="v">{_h(str(o.get('winner_ruc') or '—'))}</div></div>
          <div class="card"><div class="k">Monto adjudicado</div><div class="v">{_money(o.get('awarded_amount'), o.get('currency'))}</div></div>
          <div class="card"><div class="k">Fecha buena pro</div><div class="v">{_date(o.get('award_date'))}</div></div>
        </div>"""
    else:
        intel = '<p class="muted">Aún no hay ganador. Mantener seguimiento hasta la buena pro.</p>'

    tl = "".join(
        f'<li class="{_h(str(t.get("status") or ""))}"><div class="t">{_h(str(t.get("title") or ""))}</div>'
        f'<div class="m">{_date(t.get("date"))} · {_h(str(t.get("description") or t.get("status") or ""))}</div></li>'
        for t in (timeline or [])
    )

    logo_html = f'<img src="{logo_uri}" alt="LicitaScan">' if logo_uri else ""
    gen = _h(generated_at or datetime.now().strftime("%d/%m/%Y %H:%M"))

    body = f"""
    <div class="header">{logo_html}
      <div><div class="brand">LicitaScan</div><div class="sub">Expediente SEACE / OECE</div></div>
    </div>
    <div class="wrap">
      <div class="eyebrow">Expediente</div>
      <h1>{proc}</h1>
      <p class="desc">{desc}</p>
      <div class="badges">{badges}</div>
      <div class="grid">
        <div class="card"><div class="k">Entidad</div><div class="v">{_h(str(o.get('entity_name') or '—'))}</div></div>
        <div class="card"><div class="k">Monto referencial</div><div class="v">{_money(o.get('amount'), o.get('currency'))}</div></div>
        <div class="card"><div class="k">OCID</div><div class="v">{_h(str(o.get('ocid') or '—'))}</div></div>
        <div class="card"><div class="k">Fecha crítica</div><div class="v">{_date(o.get('next_critical_date'))}</div></div>
      </div>
      <div class="section"><h2>Acción recomendada</h2>
        <div class="reco">{reco}<div class="razon">Razones: {razones}</div></div>
      </div>
      <div class="section"><h2>Inteligencia competitiva</h2>{intel}</div>
      <div class="section"><h2>Línea de tiempo del proceso</h2><ul class="timeline">{tl}</ul></div>
    </div>
    <div class="footer"><span>Generado por LicitaScan · {gen}</span><span>Fuente: SEACE/OECE OCDS (datos públicos)</span></div>
    """
    return f"<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'><style>{_CSS}</style></head><body>{body}</body></html>"


async def _render_pdf_async(html: str) -> bytes:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        try:
            await page.set_content(html, wait_until="networkidle")
            return await page.pdf(
                format="A4", print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
        finally:
            await browser.close()


def render_expediente_pdf(opportunity: dict[str, Any], events: list[dict[str, Any]],
                          timeline: list[dict[str, Any]], static_dir: str | Path = "web",
                          generated_at: str = "") -> bytes:
    """Construye el HTML y lo renderiza a PDF (bytes) con Playwright. Local-only."""
    html = build_expediente_html(opportunity, events, timeline, logo_data_uri(static_dir), generated_at)
    return asyncio.run(_render_pdf_async(html))
