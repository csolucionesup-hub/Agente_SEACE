"""CLI for generating sales-ready SEACE opportunity datasets from the official API."""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Protocol

from seace_api import Opportunity, SeaceApiClient, export_opportunities_csv, export_opportunities_json
from seace_config import DEFAULT_KEYWORDS


class OpportunitySearchClient(Protocol):
    def search_opportunities(self, keyword: str, page: int = 1, paginate_by: int = 50) -> list[Opportunity]:
        ...


def collect_opportunities(
    client: OpportunitySearchClient,
    keywords: Iterable[str],
    pages: int = 1,
    paginate_by: int = 50,
) -> list[Opportunity]:
    opportunities_by_ocid: dict[str, Opportunity] = {}
    matched_keywords_by_ocid: dict[str, list[str]] = {}

    for keyword in keywords:
        clean_keyword = keyword.strip()
        if not clean_keyword:
            continue
        for page in range(1, pages + 1):
            for opportunity in client.search_opportunities(clean_keyword, page=page, paginate_by=paginate_by):
                dedupe_key = opportunity.ocid or f"{opportunity.process_code}|{opportunity.entity_id}|{opportunity.date}"
                if dedupe_key not in opportunities_by_ocid:
                    opportunities_by_ocid[dedupe_key] = opportunity
                    matched_keywords_by_ocid[dedupe_key] = []

                for matched_keyword in opportunity.keyword.split(","):
                    normalized_keyword = matched_keyword.strip().upper()
                    if normalized_keyword and normalized_keyword not in matched_keywords_by_ocid[dedupe_key]:
                        matched_keywords_by_ocid[dedupe_key].append(normalized_keyword)

    return [
        replace(opportunity, keyword=",".join(matched_keywords_by_ocid[dedupe_key]))
        for dedupe_key, opportunity in opportunities_by_ocid.items()
    ]


def write_opportunity_exports(opportunities: list[Opportunity], output_dir: str | Path, stem: str | None = None) -> tuple[Path, Path]:
    output = Path(output_dir)
    if stem is None:
        stem = f"oportunidades-seace-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    csv_path = export_opportunities_csv(opportunities, output / f"{stem}.csv")
    json_path = export_opportunities_json(opportunities, output / f"{stem}.json")
    return csv_path, json_path


def _parse_keywords(value: str | None) -> list[str]:
    if not value:
        return DEFAULT_KEYWORDS.copy()
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Buscar oportunidades SEACE vía API oficial OCDS.")
    parser.add_argument("--keywords", default=None, help="Lista separada por comas. Ej: PUENTE,CARRETERA,PILOTE")
    parser.add_argument("--pages", type=int, default=1, help="Páginas API por keyword")
    parser.add_argument("--paginate-by", type=int, default=25, help="Resultados por página API")
    parser.add_argument("--output-dir", default="reportes", help="Carpeta de salida CSV/JSON")
    parser.add_argument("--stem", default=None, help="Nombre base de los archivos exportados")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    client = SeaceApiClient()
    keywords = _parse_keywords(args.keywords)
    opportunities = collect_opportunities(client, keywords, pages=args.pages, paginate_by=args.paginate_by)
    csv_path, json_path = write_opportunity_exports(opportunities, args.output_dir, stem=args.stem)
    print(f"Oportunidades encontradas: {len(opportunities)}")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
