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
    notebook_path = ROOT / "fabric" / "Property Assessment Bronze Silver Gold.Notebook" / "notebook-content.py"
    notebook_bytes = notebook_path.read_bytes()
    expected_prologue = b"# Fabric notebook source\n\n# METADATA ********************\n"
    if not notebook_bytes.startswith(expected_prologue):
        fail("Fabric notebook source must begin with the exact Git-source prologue and LF line endings.")
    if b"\r\n" in notebook_bytes:
        fail("Fabric notebook source must use LF line endings.")
    notebook_text = notebook_bytes.decode("utf-8")
    if notebook_text.count("# CELL ********************") != 6:
        fail("Fabric notebook source must contain exactly six serialized cells.")
    if notebook_text.count("# METADATA ********************") != 7:
        fail("Fabric notebook source must contain notebook metadata plus metadata for all six cells.")
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
    semantic_definition = ROOT / "fabric" / "Property Assessment Model.SemanticModel" / "definition"
    model_tmdl = (semantic_definition / "model.tmdl").read_text(encoding="utf-8")
    if re.search(r"(?m)^\s*ref\s+(table|role)\b", model_tmdl):
        fail("model.tmdl must not contain ref table/ref role declarations; folder serialization auto-discovers those objects.")
    if (semantic_definition / "roles.tmdl").exists():
        fail("TMDL folder serialization requires one file per role under definition/roles.")
    role_paths = sorted((semantic_definition / "roles").glob("*.tmdl"))
    if {path.stem for path in role_paths} != {"ResidentialReviewer", "CommercialReviewer"}:
        fail("Semantic model must contain the two expected role files.")
    table_columns = {}
    allowed_table_properties = {
        "dataType", "formatString", "sourceColumn", "sortByColumn",
        "mode", "entityName", "schemaName", "expressionSource",
    }
    for table_path in (semantic_definition / "tables").glob("*.tmdl"):
        content = table_path.read_text(encoding="utf-8")
        if re.search(r"(?m)^\s*description\s*:", content):
            fail(f"Use TMDL /// description comments instead of unsupported description: properties in {table_path.name}")
        property_names = set(re.findall(r"(?m)^\s*([A-Za-z][A-Za-z0-9]*)\s*:", content))
        unsupported_properties = property_names - allowed_table_properties
        if unsupported_properties:
            fail(f"Unsupported colon-style TMDL properties in {table_path.name}: {sorted(unsupported_properties)}")
        table_match = re.search(r"(?m)^table\s+'?([^'\r\n]+)'?\s*$", content)
        if not table_match:
            fail(f"Unable to parse table declaration in {table_path.name}")
        table_name = table_match.group(1)
        table_columns[table_name] = set(
            re.findall(r"(?m)^\s*column\s+'?([^'\r\n]+)'?\s*$", content)
        )
    relationships = (semantic_definition / "relationships.tmdl").read_text(encoding="utf-8")
    for table_name, column_name in re.findall(r"(?m)^\s*(?:fromColumn|toColumn):\s*([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\s*$", relationships):
        if table_name not in table_columns or column_name not in table_columns[table_name]:
            fail(f"Relationship references unknown TMDL object {table_name}.{column_name}")
    for role_path in role_paths:
        content = role_path.read_text(encoding="utf-8")
        if not re.search(r"(?m)^role\s+" + re.escape(role_path.stem) + r"\s*$", content):
            fail(f"Role declaration does not match file name: {role_path.name}")
        if not re.search(r"tablePermission\s+DimProperty\s*=\s*DimProperty\[PropertyClassCode\]", content):
            fail(f"Role filter must use a qualified DimProperty column: {role_path.name}")
    report_definition = json.loads((ROOT / "fabric" / "Property Assessment Overview.Report" / "definition.pbir").read_text(encoding="utf-8"))
    if report_definition.get("version") != "4.0" or "datasetReference" not in report_definition:
        fail("PBIR definition is missing version 4.0 or datasetReference.")
    semantic_model_definition = json.loads(
        (ROOT / "fabric" / "Property Assessment Model.SemanticModel" / "definition.pbism").read_text(encoding="utf-8")
    )
    expected_pbism = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "5.0",
        "settings": {"qnaEnabled": True},
    }
    if semantic_model_definition != expected_pbism:
        fail("definition.pbism must match the supported minimal schema; unsupported settings are forbidden.")
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
