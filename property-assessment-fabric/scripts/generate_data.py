from __future__ import annotations

import argparse
import csv
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
NEIGHBORHOODS = [
    ("NORTH", "North Ridge", "Urban"),
    ("LAKE", "Lake Junction", "Waterfront"),
    ("PINE", "Pine Crossing", "Suburban"),
    ("COPPER", "Copper Works", "Mixed Use"),
    ("VALLEY", "Valley East", "Rural"),
    ("CENTRAL", "Central Sudsberry", "Urban Core"),
]
STREETS = ["Aurora", "Boreal", "Copper", "Granite", "Juniper", "Northern Light", "Pinecone", "Silver Birch"]
CONDITIONS = ["fair", "good", "good", "average", "excellent"]
APPEAL_SCENARIOS = [
    ("COMPARABLE_SALES", "negative", "The fictional assessed value is higher than comparable synthetic sales. Review comparable selection and condition adjustments."),
    ("PROPERTY_CONDITION", "negative", "The fictional assessment does not reflect synthetic roof damage and unfinished repairs documented during inspection."),
    ("DATA_CORRECTION", "neutral", "The fictional profile lists finished space that is synthetic unfinished storage. Verify floor area and correct the record."),
    ("CLASSIFICATION", "neutral", "The fictional parcel class does not match the synthetic permitted use. Review the classification evidence."),
    ("RENOVATION_TIMING", "negative", "The fictional valuation includes synthetic renovation work incomplete on the valuation date."),
    ("INFORMATION_REQUEST", "positive", "The fictional online summary was helpful. Provide the synthetic comparable-sales worksheet for review.")
]


def property_class(number: int) -> str:
    if number % 17 == 0:
        return "AGR"
    if number % 11 == 0:
        return "COM"
    if number % 7 == 0:
        return "MUR"
    return "RES"


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build(scale: int, seed: int) -> dict[str, list[dict]]:
    random.seed(seed)
    parcels: list[dict] = []
    buildings: list[dict] = []
    assessments: list[dict] = []
    sales: list[dict] = []
    profiles: list[dict] = []
    appeals: list[dict] = []

    for number in range(1, scale + 1):
        parcel_id = f"SUD-{number:05d}"
        neighborhood_id, neighborhood_name, market_area = NEIGHBORHOODS[number % len(NEIGHBORHOODS)]
        class_code = property_class(number)
        condition = CONDITIONS[number % len(CONDITIONS)]
        floor_area = (
            180 + number % 140 if class_code == "AGR"
            else 300 + number % 900 if class_code == "COM"
            else 260 + number % 500 if class_code == "MUR"
            else 85 + number % 190
        )
        lot_area = 12000 + number * 83 if class_code == "AGR" else 900 + number * 17 if class_code == "COM" else 420 + number * 9
        latitude = round(46.430000 + ((number % 20) * 0.003100), 6)
        longitude = round(-81.060000 + (((number - 1) // 20) * 0.004200), 6)
        address = f"{100 + number} {STREETS[number % len(STREETS)]} {['Road', 'Avenue', 'Lane', 'Drive'][number % 4]}"
        parcels.append({
            "parcelId": parcel_id, "parcelNumber": f"99-{((number - 1) // 20) + 1:04d}-{number:04d}",
            "neighborhoodId": neighborhood_id, "neighborhoodName": neighborhood_name, "marketArea": market_area,
            "propertyClassCode": class_code, "syntheticAddress": address, "latitude": latitude, "longitude": longitude,
            "lotAreaSquareMetres": lot_area, "zoningCode": {"AGR": "AG-1", "COM": "C-2", "MUR": "RM-2", "RES": "R-1"}[class_code],
            "isSynthetic": True
        })
        buildings.append({
            "buildingId": number, "parcelId": parcel_id,
            "buildingType": {"AGR": "farmResidence", "COM": "commercialBuilding", "MUR": "multiUnitResidence"}.get(class_code, ["detachedResidence", "semiDetachedResidence", "townhouse"][number % 3]),
            "yearBuilt": 1955 + number % 69, "floorAreaSquareMetres": floor_area,
            "storeys": 1 + number % (4 if class_code in {"COM", "MUR"} else 2), "conditionCode": condition,
            "isSynthetic": True
        })
        current_assessed = 0.0
        for tax_year, factor in ((2025, 1.0), (2026, 1.0475)):
            land = round(lot_area * {"AGR": 6, "COM": 145, "MUR": 118, "RES": 92}[class_code] * factor, 2)
            improvement = round(floor_area * {"AGR": 980, "COM": 1850, "MUR": 2100, "RES": 2450}[class_code] * {"fair": .78, "average": .90, "excellent": 1.12}.get(condition, 1.0) * factor, 2)
            assessed = round(land + improvement, 2)
            assessments.append({
                "assessmentId": f"ASM-{tax_year}-{number:05d}", "parcelId": parcel_id, "taxYear": tax_year,
                "valuationDate": f"{tax_year - 1}-12-31", "landValue": land, "improvementValue": improvement,
                "assessedValue": assessed, "confidenceScore": round(.76 + ((number * 37 + tax_year) % 2200) / 10000, 4),
                "assessmentStatus": "Certified", "currencyCode": "CAD", "isSynthetic": True
            })
            if tax_year == 2026:
                current_assessed = assessed
        if number % 3 == 0:
            sale_price = round(assessments[-2]["assessedValue"] * (.86 + ((number * 13) % 31) / 100), 2)
            sales.append({
                "saleId": f"SAL-{number:05d}", "parcelId": parcel_id,
                "saleDate": (date(2024, 1, 1) + timedelta(days=(number * 11) % 650)).isoformat(),
                "salePrice": sale_price, "saleType": "Open market", "isArmsLength": True,
                "currencyCode": "CAD", "isSynthetic": True
            })
        inspection_date = date(2026, 1, 5) + timedelta(days=(number * 7) % 210)
        profiles.append({
            "id": parcel_id, "parcelId": parcel_id, "documentType": "propertyProfile", "synthetic": True,
            "jurisdiction": {"name": "Sudsberry", "countryCode": "CA", "regionCode": "ON", "currencyCode": "CAD", "areaUnit": "squareMetres"},
            "neighborhoodId": neighborhood_id, "neighborhoodName": neighborhood_name,
            "location": {"type": "Point", "coordinates": [longitude, latitude]},
            "site": {"syntheticAddress": address, "propertyClassCode": class_code, "zoningCode": parcels[-1]["zoningCode"], "lotAreaSquareMetres": lot_area},
            "building": {"type": buildings[-1]["buildingType"], "yearBuilt": buildings[-1]["yearBuilt"], "floorAreaSquareMetres": floor_area, "storeys": buildings[-1]["storeys"], "condition": condition,
                         "attributes": {"energyRetrofitObserved": number % 9 == 0, "accessoryStructureObserved": number % 13 == 0, "renovationObserved": number % 8 == 0}},
            "currentAssessment": {"taxYear": 2026, "assessedValue": current_assessed, "confidenceScore": assessments[-1]["confidenceScore"], "status": "certified"},
            "inspections": [{"inspectionId": f"INS-{number:05d}-01", "inspectionDate": inspection_date.isoformat(), "inspectionType": "fieldReview" if number % 4 == 0 else "exteriorReview", "condition": condition, "followUpRequired": number % 8 == 0}]
        })

    appeal_count = scale + math.floor(scale / 4)
    for number in range(1, appeal_count + 1):
        reason, sentiment, narrative = APPEAL_SCENARIOS[number % len(APPEAL_SCENARIOS)]
        submitted = date(2026, 2, 1) + timedelta(days=(number * 3) % 180)
        status = ["submitted", "underReview", "resolved"][number % 3]
        appeals.append({
            "appealId": f"APL-{number:05d}", "parcelId": f"SUD-{((number * 7) % scale) + 1:05d}",
            "neighborhoodId": NEIGHBORHOODS[number % len(NEIGHBORHOODS)][0], "taxYear": 2026,
            "submittedDate": submitted.isoformat(), "reasonCode": reason, "narrative": narrative,
            "requestedAdjustmentPct": round(3.0 + ((number * 7) % 28) * .5, 2), "status": status,
            "outcome": ["confirmed", "adjusted", "partiallyAdjusted"][number % 3] if status == "resolved" else None,
            "resolvedDate": (submitted + timedelta(days=14 + number % 35)).isoformat() if status == "resolved" else None,
            "groundTruthSentiment": sentiment, "currencyCode": "CAD", "countryCode": "CA", "regionCode": "ON", "synthetic": True
        })
    return {"parcels": parcels, "buildings": buildings, "assessments": assessments, "sales": sales, "property_profiles": profiles, "appeals": appeals}


def sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "N'" + str(value).replace("'", "''") + "'"


def write_sql_seed(path: Path, data: dict[str, list[dict]]) -> None:
    tables = [
        ("dbo.Parcel", data["parcels"]),
        ("dbo.Building", data["buildings"]),
        ("dbo.Assessment", data["assessments"]),
        ("dbo.Sale", data["sales"])
    ]
    lines = ["SET NOCOUNT ON;", "SET XACT_ABORT ON;", "BEGIN TRANSACTION;"]
    for table, rows in reversed(tables):
        lines.append(f"DELETE FROM {table};")
    for table, rows in tables:
        columns = list(rows[0])
        for start in range(0, len(rows), 500):
            batch = rows[start:start + 500]
            lines.append(f"INSERT INTO {table} ({', '.join('[' + column + ']' for column in columns)}) VALUES")
            lines.append(",\n".join("(" + ", ".join(sql_literal(row[column]) for column in columns) + ")" for row in batch) + ";")
    lines.extend(["COMMIT TRANSACTION;", "SELECT COUNT(*) AS ParcelCount FROM dbo.Parcel;"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic fictional property-assessment data.")
    parser.add_argument("--scale", type=int, default=240)
    parser.add_argument("--seed", type=int, default=20261013)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "generated")
    args = parser.parse_args()
    if args.scale < 24:
        raise SystemExit("--scale must be at least 24 so every scenario is represented.")
    data = build(args.scale, args.seed)
    output = args.output
    sql_dir, cosmos_dir, adls_dir = output / "sql", output / "cosmos", output / "adls"
    for name in ("parcels", "buildings", "assessments", "sales"):
        write_csv(sql_dir / f"{name}.csv", data[name])
    cosmos_dir.mkdir(parents=True, exist_ok=True)
    (cosmos_dir / "property_profiles.json").write_text(json.dumps(data["property_profiles"], indent=2) + "\n", encoding="utf-8")
    (cosmos_dir / "property_profiles.jsonl").write_text("\n".join(json.dumps(row, separators=(",", ":")) for row in data["property_profiles"]) + "\n", encoding="utf-8")
    adls_dir.mkdir(parents=True, exist_ok=True)
    appeals_json = adls_dir / "assessment_appeals.json"
    appeals_json.write_text(json.dumps(data["appeals"], indent=2) + "\n", encoding="utf-8")
    with duckdb.connect() as connection:
        connection.execute("CREATE TABLE appeals AS SELECT * FROM read_json_auto(?, format='array')", [str(appeals_json).replace("\\", "/")])
        connection.execute(f"COPY appeals TO '{str(adls_dir / 'assessment_appeals.parquet').replace(chr(92), '/')}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    write_sql_seed(sql_dir / "seed.generated.sql", data)
    manifest = {
        "synthetic": True, "seed": args.seed, "scale": args.scale,
        "counts": {name: len(rows) for name, rows in data.items()},
        "warning": "All records are fictional and unsuitable for real valuation or taxation."
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

