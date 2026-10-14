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
        "fabric/Property Assessment Overview.Report/definition/pages/PropertyAssessmentOverview/page.json",
        "fabric/Property Assessment Ontology.Ontology/database.tmdl",
        "fabric/Property Assessment Ontology.Ontology/design/intended-ontology.json",
        "fabric/Assessment Semantic Agent.DataAgent/Files/Config/data_agent.json",
        "fabric/Assessment Semantic Agent.DataAgent/Files/Config/draft/semantic_model-PropertyAssessmentModel/datasource.json",
        "fabric/Assessment Ontology Agent.DataAgent/Files/Config/data_agent.json",
        "fabric/Assessment Ontology Agent.DataAgent/Files/Config/draft/graph-PropertyAssessmentOntology/datasource.json",
        "scripts/prepare_gold.py",
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
    for placeholder in ("<FABRIC_WORKSPACE_ID>", "<FABRIC_LAKEHOUSE_ID>"):
        if placeholder not in notebook_text:
            fail(f"Notebook source is missing deployment placeholder {placeholder}")
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
    expressions = (semantic_definition / "expressions.tmdl").read_text(encoding="utf-8")
    expected_sql_source = 'Sql.Database("<FABRIC_SQL_ENDPOINT>", "<FABRIC_SQL_DATABASE>")'
    if expected_sql_source not in expressions or "Lakehouse.Contents" in expressions:
        fail("Direct Lake expression must use staged Sql.Database endpoint/database placeholders.")
    for annotation in (
        "annotation PBI_NavigationStepName = Navigation",
        "annotation PBI_ResultType = Table",
    ):
        if annotation not in expressions:
            fail(f"Direct Lake expression is missing required metadata: {annotation}")
    for table_path in (semantic_definition / "tables").glob("*.tmdl"):
        content = table_path.read_text(encoding="utf-8")
        if "mode: directLake" not in content or "expressionSource: PropertyAssessmentLakehouse" not in content:
            fail(f"Direct Lake partition is not bound to the shared expression: {table_path.name}")
    report_definition = json.loads((ROOT / "fabric" / "Property Assessment Overview.Report" / "definition.pbir").read_text(encoding="utf-8"))
    expected_report_binding = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "2.0",
        "datasetReference": {
            "byConnection": {
                "connectionString": "semanticModelId=<PROPERTY_ASSESSMENT_SEMANTIC_MODEL_ITEM_ID>"
            }
        },
    }
    if report_definition != expected_report_binding:
        fail("PBIR definition must use an in-memory staged semanticModelId connection.")
    report_root = ROOT / "fabric" / "Property Assessment Overview.Report" / "definition"
    report_version = json.loads((report_root / "version.json").read_text(encoding="utf-8"))
    if report_version != {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    }:
        fail("PBIR version metadata does not match the supported schema.")
    pages = json.loads((report_root / "pages" / "pages.json").read_text(encoding="utf-8"))
    if (
        pages.get("$schema")
        != "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json"
        or pages.get("pageOrder") != ["PropertyAssessmentOverview"]
        or pages.get("activePageName") != "PropertyAssessmentOverview"
    ):
        fail("PBIR page metadata must select the PropertyAssessmentOverview page.")
    page = json.loads(
        (report_root / "pages" / "PropertyAssessmentOverview" / "page.json").read_text(encoding="utf-8")
    )
    if (
        page.get("$schema")
        != "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json"
        or page.get("name") != "PropertyAssessmentOverview"
        or page.get("width") != 1280
        or page.get("height") != 720
    ):
        fail("PBIR overview page metadata is incomplete.")
    ontology_root = ROOT / "fabric" / "Property Assessment Ontology.Ontology"
    if any(path.is_file() for path in (ontology_root / "definition").rglob("*")):
        fail("Generation 2 Ontology definition parts must be item-root-relative, not nested under definition/.")
    if (ontology_root / "database.tmdl").read_text(encoding="utf-8") != "database\n\tcompatibilityLevel: 1000000\n":
        fail("Ontology must use the supported minimal Generation 2 database definition.")
    intended_ontology = json.loads((ontology_root / "design" / "intended-ontology.json").read_text(encoding="utf-8"))
    if not intended_ontology.get("synthetic") or intended_ontology.get("bindingStatus") != "manual-preview":
        fail("Ontology design must identify synthetic data and manual preview binding.")
    data_agent_schema = (
        "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/"
        "definition/dataAgent/2.1.0/schema.json"
    )
    data_source_schema = (
        "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/"
        "definition/dataSource/1.0.0/schema.json"
    )
    agent_expectations = (
        (
            "Assessment Semantic Agent.DataAgent",
            "semantic_model-PropertyAssessmentModel",
            "semantic_model",
            "<PROPERTY_ASSESSMENT_SEMANTIC_MODEL_ITEM_ID>",
        ),
        (
            "Assessment Ontology Agent.DataAgent",
            "graph-PropertyAssessmentOntology",
            "graph",
            "<PROPERTY_ASSESSMENT_ONTOLOGY_ITEM_ID>",
        ),
    )
    for folder_name, source_folder, source_type, item_placeholder in agent_expectations:
        agent_root = ROOT / "fabric" / folder_name / "Files" / "Config"
        if json.loads((agent_root / "data_agent.json").read_text(encoding="utf-8")) != {"$schema": data_agent_schema}:
            fail(f"{folder_name} top-level definition must contain only the supported schema.")
        stage = json.loads((agent_root / "draft" / "stage_config.json").read_text(encoding="utf-8"))
        if not stage.get("$schema", "").endswith("/stageConfiguration/1.0.0/schema.json") or not stage.get("aiInstructions"):
            fail(f"{folder_name} draft stage configuration is incomplete.")
        source = json.loads((agent_root / "draft" / source_folder / "datasource.json").read_text(encoding="utf-8"))
        if (
            source.get("$schema") != data_source_schema
            or source.get("artifactId") != item_placeholder
            or source.get("workspaceId") != "<FABRIC_WORKSPACE_ID>"
            or source.get("type") != source_type
        ):
            fail(f"{folder_name} data source must use staged workspace/item IDs and the supported source schema.")
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
    semantic_items = [item for item in config["items"] if item["type"] == "SemanticModel"]
    if len(semantic_items) != 1 or semantic_items[0].get("directLakeSourceDisplayName") != "PropertyAssessmentLakehouse":
        fail("Semantic model must resolve its Direct Lake binding from the owned Lakehouse.")
    notebook_items = [item for item in config["items"] if item["type"] == "Notebook"]
    if len(notebook_items) != 1 or notebook_items[0].get("defaultLakehouseDisplayName") != "PropertyAssessmentLakehouse":
        fail("Notebook must resolve its default binding from the owned Lakehouse.")
    report_items = [item for item in config["items"] if item["type"] == "Report"]
    if (
        len(report_items) != 1
        or report_items[0].get("automation") != "rest-definition"
        or report_items[0].get("semanticModelSourceDisplayName") != "PropertyAssessmentModel"
    ):
        fail("Report must deploy through REST with an owned semantic-model binding.")
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
