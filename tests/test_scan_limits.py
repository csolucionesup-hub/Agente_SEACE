import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from seace_config import RuntimeConfig
from agente_seace import scanear_resultados


class FakeLocator:
    def __init__(self, *, text="", visible=True, count=1, attrs=None):
        self.text = text
        self.visible = visible
        self._count = count
        self.attrs = attrs or {}

    async def is_visible(self):
        return self.visible

    async def count(self):
        return self._count

    def nth(self, index):
        return self

    @property
    def last(self):
        return self

    @property
    def first(self):
        return self

    def locator(self, selector):
        return self

    def filter(self, **kwargs):
        return self

    async def inner_text(self):
        return self.text

    async def scroll_into_view_if_needed(self):
        return None

    async def click(self, **kwargs):
        return None

    async def wait_for(self, **kwargs):
        return None

    async def get_attribute(self, name):
        return self.attrs.get(name)


class FakePage:
    def __init__(self):
        self.row = FakeLocator(text="1\tENTIDAD\tOBRA DE PUENTE\tACCIONES")
        self.empty = FakeLocator(visible=False)
        self.rows = FakeLocator(count=1)
        self.keyboard = SimpleNamespace()

    def locator(self, selector):
        if "empty-message" in selector:
            return self.empty
        if "tr.ui-widget-content" in selector:
            return self.row
        if "tbody" in selector:
            return self.row
        return FakeLocator(text="Regresar")

    async def wait_for_timeout(self, ms):
        return None

    async def wait_for_selector(self, *args, **kwargs):
        return None


def test_scanear_resultados_respects_max_captures(monkeypatch, tmp_path):
    cfg = RuntimeConfig(
        seace_url="https://example.test",
        headless=True,
        keywords=["PUENTE"],
        year_start=2025,
        year_end=2025,
        max_pages=1,
        max_captures=1,
        output_dir=tmp_path,
    )
    calls = []

    async def fake_capture(*args, **kwargs):
        calls.append(args)
        return True

    monkeypatch.setattr("agente_seace.capturar_ficha_seace", fake_capture)

    captured = asyncio.run(scanear_resultados(FakePage(), "PUENTE", 2025, None, None, cfg, captures_taken=0))

    assert captured == 1
    assert len(calls) == 1
