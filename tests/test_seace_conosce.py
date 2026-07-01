from seace_conosce import summarize_rows


def _rows():
    # Filas con los nombres de columna REALES del XLSX de CONOSCE (2024).
    return [
        {"ENTIDAD": "MUNI PUENTE PIEDRA", "OBJETOCONTRACTUAL": "Obra", "MONTOREFERENCIAL": "1000000",
         "DESCRIPCION_PROCESO": "Reparacion de puente X", "PROCESO": "LP-1-2024-MPP"},
        {"ENTIDAD": "MUNI PUENTE PIEDRA", "OBJETOCONTRACTUAL": "Obra", "MONTOREFERENCIAL": "500000",
         "DESCRIPCION_PROCESO": "Construccion de puente Y", "PROCESO": "AS-2-2024-MPP"},
        {"ENTIDAD": "PROVIAS", "OBJETOCONTRACTUAL": "Consultoría de Obra", "MONTOREFERENCIAL": "2000000",
         "DESCRIPCION_PROCESO": "Estudio de puente Z", "PROCESO": "CP-3-2024-MTC"},
        {"ENTIDAD": "OTRA ENTIDAD", "OBJETOCONTRACTUAL": "Bien", "MONTOREFERENCIAL": "300000",
         "DESCRIPCION_PROCESO": "Compra de fierros", "PROCESO": "AS-4-2024"},
    ]


def test_summarize_lee_las_columnas_reales_de_conosce():
    r = summarize_rows(_rows(), keyword="puente")
    # "puente" filtra las 3 primeras (la de fierros no menciona puente).
    assert r["total_records"] == 3
    assert r["total_amount"] == 3500000.0  # 1M + 0.5M + 2M (columna MONTOREFERENCIAL, sin guion)
    cats = {c["name"]: c["count"] for c in r["top_categories"]}
    assert cats.get("Obra") == 2
    assert cats.get("Consultoría de Obra") == 1
    ents = {e["name"]: e["count"] for e in r["top_entities"]}
    assert ents.get("MUNI PUENTE PIEDRA") == 2
    sample = r["sample_records"][0]
    assert sample["amount"] > 0
    assert sample["description"]
    assert sample["process_code"]


def test_summarize_sin_keyword_cuenta_todas():
    r = summarize_rows(_rows())
    assert r["total_records"] == 4
    assert r["total_amount"] == 3800000.0
