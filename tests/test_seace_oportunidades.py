from pathlib import Path

from seace_api import Opportunity
from seace_oportunidades import collect_opportunities, write_opportunity_exports


class FakeClient:
    def __init__(self):
        self.calls = []

    def search_opportunities(self, keyword, page=1, paginate_by=50):
        self.calls.append((keyword, page, paginate_by))
        return [
            Opportunity(
                keyword=keyword.upper(),
                ocid=f"ocds-{keyword}-{page}",
                tender_id=f"{keyword}-{page}",
                process_code=f"PROC-{keyword}-{page}",
                entity_name="ENTIDAD",
                entity_id="PE-1",
                description=f"Proyecto {keyword}",
                category="works",
                procurement_method="Licitación Pública",
                amount=100.0,
                currency="PEN",
                date="2026-06-05T00:00:00-05:00",
                tender_start_date="2026-06-01T00:00:00-05:00",
                tender_end_date="2026-06-10T00:00:00-05:00",
                source="SEACE V3",
                api_url=f"https://example.test/{keyword}/{page}",
            )
        ]


def test_collect_opportunities_queries_each_keyword_and_page():
    client = FakeClient()

    opportunities = collect_opportunities(client, ["puente", "carretera"], pages=2, paginate_by=10)

    assert [op.keyword for op in opportunities] == ["PUENTE", "PUENTE", "CARRETERA", "CARRETERA"]
    assert client.calls == [
        ("puente", 1, 10),
        ("puente", 2, 10),
        ("carretera", 1, 10),
        ("carretera", 2, 10),
    ]


class DuplicateClient:
    def search_opportunities(self, keyword, page=1, paginate_by=50):
        return [
            Opportunity(
                keyword=keyword.upper(),
                ocid="same-ocid",
                tender_id="123",
                process_code="PROC-123",
                entity_name="ENTIDAD",
                entity_id="PE-1",
                description="Proyecto puente carretera",
                category="works",
                procurement_method="Licitación Pública",
                amount=100.0,
                currency="PEN",
                date="2026-06-05T00:00:00-05:00",
                tender_start_date="2026-06-01T00:00:00-05:00",
                tender_end_date="2026-06-10T00:00:00-05:00",
                source="SEACE V3",
                api_url="https://example.test/record/same-ocid",
            )
        ]


def test_collect_opportunities_deduplicates_by_ocid_and_preserves_matched_keywords():
    opportunities = collect_opportunities(DuplicateClient(), ["puente", "carretera"], pages=1, paginate_by=10)

    assert len(opportunities) == 1
    assert opportunities[0].keyword == "PUENTE,CARRETERA"


def test_write_opportunity_exports_creates_csv_and_json(tmp_path: Path):
    opportunity = FakeClient().search_opportunities("puente")[0]

    csv_path, json_path = write_opportunity_exports([opportunity], tmp_path, stem="demo")

    assert csv_path.name == "demo.csv"
    assert json_path.name == "demo.json"
    assert "PROC-puente-1" in csv_path.read_text(encoding="utf-8")
    assert "PROC-puente-1" in json_path.read_text(encoding="utf-8")
