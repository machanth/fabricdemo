from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "data" / "generated"


def fail(message: str) -> None:
    raise AssertionError(message)


def load_csv(name: str) -> list[dict]:
    with (GENERATED / "sql" / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_data() -> None:
    manifest = json.loads((GENERATED / "manifest.json").read_text(encoding="utf-8"))
    contract = json.loads((ROOT / "contracts" / "dataset-contract.json").read_text(encoding="utf-8"))
    parcels = load_csv("parcels")
    assessments = load_csv("assessments")
    sales = load_csv("sales")
    profiles = json.loads((GENERATED / "cosmos" / "property_profiles.json").read_text(encoding="utf-8"))
    appeals = json.loads((GENERATED / "adls" / "assessment_appeals.json").read_text(encoding="utf-8"))
    parcel_ids = {row["parcelId"] for row in parcels}
    expected = {
        "parcels": manifest["scale"],
        "buildings": manifest["scale"],
        "assessments": manifest["scale"] * 2,
        "sales": manifest["scale"] // 3,
        "property_profiles": manifest["scale"],
        "appeals": manifest["scale"] + manifest["scale"] // 4
    }
    if manifest["counts"] != expected:
        fail(f"Count contract mismatch: {manifest['counts']} != {expected}")
    for dataset_name, rows in (("assessments", assessments), ("sales", sales), ("profiles", profiles), ("appeals", appeals)):
        missing = {row["parcelId"] for row in rows} - parcel_ids
        if missing:
            fail(f"{dataset_name} contains unknown parcelIds: {sorted(missing)[:3]}")
    for row in assessments:
        if round(float(row["landValue"]) + float(row["improvementValue"]), 2) != round(float(row["assessedValue"]), 2):
            fail(f"Assessment arithmetic failed for {row['assessmentId']}")
    for row in appeals:
        resolved = row["status"] == "resolved"
        if resolved != bool(row["outcome"] and row["resolvedDate"]):
            fail(f"Appeal lifecycle failed for {row['appealId']}")
    forbidden = re.compile(r"\b(email|telephone|phone|ownerName)\b", re.IGNORECASE)
    if forbidden.search(json.dumps({"profiles": profiles, "appeals": appeals})):
        fail("Generated documents include a forbidden personal-data field.")
    parquet_path = str(GENERATED / "adls" / "assessment_appeals.parquet").replace("\\", "/")
    with duckdb.connect() as connection:
        parquet_ids = {row[0] for row in connection.execute("SELECT appealId FROM read_parquet(?)", [parquet_path]).fetchall()}
    if parquet_ids != {row["appealId"] for row in appeals}:
        fail("Appeal JSON and Parquet identifiers differ.")
    if not contract["synthetic"] or not all(row.get("synthetic") is True for row in profiles + appeals):
        fail("Synthetic markers are missing.")


def validate_artifacts() -> None:
    required = [
        "config/lab.json", "contracts/dataset-contract.json",
        "fabric/Property Assessment.Lakehouse/lakehouse.metadata.json",
        "fabric/Property Assessment Bronze Silver Gold.Notebook/notebook-content.py",
        "fabric/Property Assessment Warehouse/deploy.sql",
        "fabric/Property Assessment Model.SemanticModel/definition.pbism",
        "fabric/Property Assessment Model.SemanticModel/definition/model.tmdl",
        "fabric/Property Assessment Overview.Report/definition.pbir",
        "fabric/Property Assessment Ontology.Ontology/definition/model.tmdl",
        "fabric/Assessment Semantic Agent.DataAgent/Files/Config/data_agent.json",
        "fabric/Assessment Ontology Agent.DataAgent/Files/Config/data_agent.json",
        "docs/08-governance-operations.md"
    ]
    missing = [relative for relative in required if not (ROOT / relative).exists()]
    if missing:
        fail("Missing required artifacts: " + ", ".join(missing))
    unsupported_shortcuts = ROOT / "fabric" / "Property Assessment.Lakehouse" / "shortcuts.metadata.json"
    if unsupported_shortcuts.exists():
        fail("Lakehouse shortcuts.metadata.json must not be committed; create environment-specific shortcuts after Lakehouse deployment.")
    for path in ROOT.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    for path in ROOT.rglob("*.tmdl"):
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            fail(f"Empty TMDL file: {path.relative_to(ROOT)}")
        if "\t" not in content and path.name not in {"database.tmdl"}:
            fail(f"TMDL file has no indented properties: {path.relative_to(ROOT)}")
        if content.count("```") % 2:
            fail(f"Unbalanced TMDL expression fence: {path.relative_to(ROOT)}")
    report_definition = json.loads((ROOT / "fabric" / "Property Assessment Overview.Report" / "definition.pbir").read_text(encoding="utf-8"))
    if report_definition.get("version") != "4.0" or "datasetReference" not in report_definition:
        fail("PBIR definition is missing version 4.0 or datasetReference.")
    config = json.loads((ROOT / "config" / "lab.json").read_text(encoding="utf-8"))
    if config["workspace"]["id"] != "930bbe6f-b256-46b7-a70e-f3dcab99d2c9":
        fail("Target workspace ID changed unexpectedly.")
    display_names = [item["displayName"] for item in config["items"]]
    if len(display_names) != len(set(display_names)):
        fail("Fabric item display names must be unique.")
    invalid_display_names = [name for name in display_names if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{2,127}", name)]
    if invalid_display_names:
        fail(f"Fabric item display names are not API-safe: {invalid_display_names}")
    for item in config["items"]:
        source = ROOT / item["source"]
        platform_path = source / ".platform"
        if platform_path.exists():
            platform = json.loads(platform_path.read_text(encoding="utf-8"))
            if platform["metadata"]["displayName"] != item["displayName"]:
                fail(f".platform display name does not match config for {item['displayName']}")
        agent_path = source / "Files" / "Config" / "data_agent.json"
        if agent_path.exists():
            agent = json.loads(agent_path.read_text(encoding="utf-8"))
            if agent["name"] != item["displayName"]:
                fail(f"Data Agent name does not match config for {item['displayName']}")
    tracked_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in ROOT.rglob("*")
        if path.is_file() and ".state" not in path.parts and path.suffix.lower() not in {".parquet", ".pyc"}
    )
    secret_patterns = [
        r"(?i)client_secret\s*=\s*['\"][^<{$\s][^'\"]{7,}['\"]",
        r"(?i)tenant_id\s*=\s*['\"][0-9a-f-]{36}['\"]",
        r"(?i)password\s*=\s*['\"][^<{$\s][^'\"]{7,}['\"]",
    ]
    for pattern in secret_patterns:
        if re.search(pattern, tracked_text):
            fail(f"Potential committed secret matched pattern: {pattern}")


if __name__ == "__main__":
    validate_data()
    validate_artifacts()
    print("PASS: deterministic data, contracts, cross-source joins, JSON, and Fabric artifacts validated.")
    sys.exit(0)
