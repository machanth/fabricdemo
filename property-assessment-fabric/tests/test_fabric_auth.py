import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential, ClientSecretCredential
from requests.exceptions import ReadTimeout


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fabric_deploy  # noqa: E402


def clear_auth_environment(monkeypatch):
    for name in fabric_deploy.CLIENT_CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_complete_client_credentials_are_selected(monkeypatch):
    clear_auth_environment(monkeypatch)
    monkeypatch.setenv("AZURE_TENANT_ID", "00000000-0000-0000-0000-000000000001")
    monkeypatch.setenv("AZURE_CLIENT_ID", "00000000-0000-0000-0000-000000000002")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "transient-test-value")
    monkeypatch.setattr(fabric_deploy.shutil, "which", lambda _: None)

    assert fabric_deploy.credential_mode() == "client-secret"
    assert isinstance(fabric_deploy.credential(), ClientSecretCredential)


def test_partial_client_credentials_are_rejected(monkeypatch):
    clear_auth_environment(monkeypatch)
    monkeypatch.setenv("AZURE_CLIENT_ID", "00000000-0000-0000-0000-000000000002")

    with pytest.raises(RuntimeError, match="AZURE_TENANT_ID, AZURE_CLIENT_SECRET"):
        fabric_deploy.credential_mode()


def test_azure_cli_is_used_when_client_credentials_are_absent(monkeypatch):
    clear_auth_environment(monkeypatch)
    monkeypatch.setattr(
        fabric_deploy.shutil,
        "which",
        lambda name: "C:\\Program Files\\Azure CLI\\az.cmd" if name == "az" else None,
    )

    assert fabric_deploy.credential_mode() == "azure-cli"
    assert isinstance(fabric_deploy.credential(), AzureCliCredential)


def test_fabric_session_uses_access_token_not_client_secret(monkeypatch):
    monkeypatch.setattr(fabric_deploy, "token", lambda: "short-lived-access-token")
    client = fabric_deploy.Fabric("workspace-id", "https://api.fabric.microsoft.com/v1")

    assert client.session.headers["Authorization"] == "Bearer short-lived-access-token"
    assert "client-secret" not in str(client.session.headers)


def test_configured_fabric_display_names_are_api_safe():
    config = json.loads((ROOT / "config" / "lab.json").read_text(encoding="utf-8"))

    fabric_deploy.validate_display_names(config["items"])


def test_invalid_fabric_display_name_is_rejected():
    with pytest.raises(RuntimeError, match="contain no spaces"):
        fabric_deploy.validate_display_names(
            [{"displayName": "Property Assessment", "type": "Lakehouse"}]
        )


def test_lro_poll_retries_read_timeout(monkeypatch):
    responses = [
        ReadTimeout("temporary timeout"),
        SimpleNamespace(
            status_code=200,
            headers={"Retry-After": "1"},
            text='{"status":"Succeeded"}',
            json=lambda: {"status": "Succeeded"},
        ),
    ]

    class FakeSession:
        def get(self, _location, timeout):
            assert timeout == (30, 120)
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

    client = fabric_deploy.Fabric.__new__(fabric_deploy.Fabric)
    client.session = FakeSession()
    monotonic_values = iter([0, 1, 2])
    monkeypatch.setattr(fabric_deploy.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(fabric_deploy.time, "sleep", lambda _seconds: None)

    assert client.poll_operation("https://operation.example", retry_after=1)["status"] == "Succeeded"


def test_discovery_reports_marker_without_modifying_state():
    item = {
        "id": "item-id",
        "displayName": "PropertyAssessmentLakehouse",
        "type": "Lakehouse",
        "description": fabric_deploy.MANAGED_DESCRIPTION,
    }
    config = {
        "workspace": {"id": "workspace-id"},
        "items": [{"displayName": item["displayName"], "type": item["type"]}],
    }
    state = {"items": [], "operations": []}
    client = SimpleNamespace(workspace_id="workspace-id")

    report = fabric_deploy.discovery_report(config, state, [item], client)

    assert report["readOnly"] is True
    assert report["configuredItems"][0]["matches"][0]["managedMarker"] is True
    assert state == {"items": [], "operations": []}


def test_accepted_operation_captures_identity_without_secret():
    response = SimpleNamespace(
        headers={
            "Location": "https://operation.example/operations/operation-id",
            "x-ms-operation-id": "operation-id",
        }
    )
    item = {"displayName": "PropertyAssessmentLakehouse", "type": "Lakehouse"}

    operation = fabric_deploy.accepted_operation(response, item)

    assert operation["operationId"] == "operation-id"
    assert operation["displayName"] == item["displayName"]
    assert "secret" not in json.dumps(operation).lower()


def test_accepted_operation_handles_empty_202_body():
    response = SimpleNamespace(
        content=b"",
        headers={
            "Location": "https://operation.example/operations/header-operation-id",
            "x-ms-operation-id": "header-operation-id",
        },
        json=lambda: None,
    )
    item = {"displayName": "PropertyAssessmentLakehouse", "type": "Lakehouse"}

    operation = fabric_deploy.accepted_operation(response, item)

    assert operation["operationId"] == "header-operation-id"
    assert operation["operationLocation"] == response.headers["Location"]
    assert "itemId" not in operation


def test_create_resolves_lro_result_by_exact_name_and_type():
    client = fabric_deploy.Fabric.__new__(fabric_deploy.Fabric)
    client.workspace_id = "workspace-id"
    response = SimpleNamespace(status_code=202, content=b'{"status":"Accepted"}')
    client.request = lambda *args, **kwargs: response
    client.list_items = lambda: [
        {
            "id": "created-id",
            "displayName": "PropertyAssessmentLakehouse",
            "type": "Lakehouse",
        }
    ]
    item = {"displayName": "PropertyAssessmentLakehouse", "type": "Lakehouse"}

    assert client.create(item, definition=None)["id"] == "created-id"


def test_lakehouse_definition_excludes_environment_specific_shortcuts():
    folder = ROOT / "fabric" / "Property Assessment.Lakehouse"

    definition = fabric_deploy.definition_for(folder)
    paths = {part["path"] for part in definition["parts"]}

    assert "lakehouse.metadata.json" in paths
    assert "shortcuts.metadata.json" not in paths


def test_reconcile_marks_terminal_failed_operation(monkeypatch, tmp_path):
    state = {
        "workspaceId": "workspace-id",
        "items": [],
        "operations": [
            {
                "operationId": "operation-id",
                "operationLocation": "https://operation.example/operation-id",
                "displayName": "PropertyAssessmentLakehouse",
                "type": "Lakehouse",
                "status": "Accepted",
            }
        ],
    }
    client = SimpleNamespace(
        poll_operation=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            fabric_deploy.FabricOperationFailed("Fabric operation ended as Failed")
        )
    )
    state_path = tmp_path / "owned-items.json"
    monkeypatch.setattr(fabric_deploy, "persist_state", lambda _path, _state: None)

    fabric_deploy.reconcile_pending_operations(client, state, state_path)

    assert state["operations"][0]["status"] == "Failed"
    assert "ended as Failed" in state["operations"][0]["error"]


def test_notebook_uses_exact_fabric_git_source_prologue():
    notebook = (
        ROOT
        / "fabric"
        / "Property Assessment Bronze Silver Gold.Notebook"
        / "notebook-content.py"
    ).read_bytes()

    assert notebook.startswith(
        b"# Fabric notebook source\n\n# METADATA ********************\n"
    )
    assert b"\r\n" not in notebook


def test_semantic_model_pbism_uses_supported_minimal_schema():
    definition = json.loads(
        (
            ROOT
            / "fabric"
            / "Property Assessment Model.SemanticModel"
            / "definition.pbism"
        ).read_text(encoding="utf-8")
    )

    assert definition == {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "5.0",
        "settings": {"qnaEnabled": True},
    }


def test_tmdl_model_uses_folder_discovery_not_ref_declarations():
    definition = (
        ROOT
        / "fabric"
        / "Property Assessment Model.SemanticModel"
        / "definition"
    )
    model = (definition / "model.tmdl").read_text(encoding="utf-8")

    assert "ref table" not in model
    assert "ref role" not in model
    assert not (definition / "roles.tmdl").exists()
    assert {
        path.name for path in (definition / "roles").glob("*.tmdl")
    } == {"ResidentialReviewer.tmdl", "CommercialReviewer.tmdl"}


def test_tmdl_descriptions_use_documentation_comments():
    tables = (
        ROOT
        / "fabric"
        / "Property Assessment Model.SemanticModel"
        / "definition"
        / "tables"
    )
    content = "\n".join(
        path.read_text(encoding="utf-8") for path in tables.glob("*.tmdl")
    )

    assert "description:" not in content
    assert "/// Fictional parcel and neighborhood attributes" in content
    assert "/// Sum of fictional certified assessed values." in content


def test_extract_direct_lake_binding_from_lakehouse_properties():
    lakehouse = {
        "properties": {
            "sqlEndpointProperties": {
                "connectionString": "example.datawarehouse.fabric.microsoft.com",
                "id": "11111111-2222-3333-4444-555555555555",
                "provisioningStatus": "Success",
            }
        }
    }

    assert fabric_deploy.extract_direct_lake_binding(lakehouse) == {
        "<FABRIC_SQL_ENDPOINT>": "example.datawarehouse.fabric.microsoft.com",
        "<FABRIC_SQL_DATABASE>": "11111111-2222-3333-4444-555555555555",
    }


def test_semantic_definition_stages_live_direct_lake_values_in_memory():
    folder = ROOT / "fabric" / "Property Assessment Model.SemanticModel"
    replacements = {
        "<FABRIC_SQL_ENDPOINT>": "example.datawarehouse.fabric.microsoft.com",
        "<FABRIC_SQL_DATABASE>": "11111111-2222-3333-4444-555555555555",
    }

    definition = fabric_deploy.definition_for(folder, replacements=replacements)
    expressions_part = next(
        part for part in definition["parts"]
        if part["path"] == "definition/expressions.tmdl"
    )
    staged = base64.b64decode(expressions_part["payload"]).decode("utf-8")
    committed = (folder / "definition" / "expressions.tmdl").read_text(encoding="utf-8")

    assert 'Sql.Database("example.datawarehouse.fabric.microsoft.com", "11111111-2222-3333-4444-555555555555")' in staged
    assert "<FABRIC_SQL_" not in staged
    assert "<FABRIC_SQL_ENDPOINT>" in committed
    assert "<FABRIC_SQL_DATABASE>" in committed


def test_report_definition_stages_live_semantic_model_id_in_memory():
    config = json.loads((ROOT / "config" / "lab.json").read_text(encoding="utf-8"))
    report_item = next(item for item in config["items"] if item["type"] == "Report")
    state = {
        "items": [
            {
                "id": "59badcb1-1b17-4043-867e-302462515677",
                "displayName": "PropertyAssessmentModel",
                "type": "SemanticModel",
            }
        ]
    }

    replacements = fabric_deploy.item_reference_replacements(
        state,
        report_item,
        "930bbe6f-b256-46b7-a70e-f3dcab99d2c9",
    )
    definition = fabric_deploy.definition_for(
        ROOT / report_item["source"],
        replacements=replacements,
    )
    binding_part = next(
        part for part in definition["parts"] if part["path"] == "definition.pbir"
    )
    staged = base64.b64decode(binding_part["payload"]).decode("utf-8")
    committed = (ROOT / report_item["source"] / "definition.pbir").read_text(encoding="utf-8")

    assert "semanticModelId=59badcb1-1b17-4043-867e-302462515677" in staged
    assert "<PROPERTY_ASSESSMENT_SEMANTIC_MODEL_ITEM_ID>" not in staged
    assert "<PROPERTY_ASSESSMENT_SEMANTIC_MODEL_ITEM_ID>" in committed


def test_data_agent_definitions_stage_owned_source_and_workspace_ids():
    config = json.loads((ROOT / "config" / "lab.json").read_text(encoding="utf-8"))
    state = {
        "items": [
            {
                "id": "59badcb1-1b17-4043-867e-302462515677",
                "displayName": "PropertyAssessmentModel",
                "type": "SemanticModel",
            },
            {
                "id": "ontology-id",
                "displayName": "PropertyAssessmentOntology",
                "type": "Ontology",
            },
        ]
    }
    expected = {
        "AssessmentSemanticAgent": "59badcb1-1b17-4043-867e-302462515677",
        "AssessmentOntologyAgent": "ontology-id",
    }

    for item in (item for item in config["items"] if item["type"] == "DataAgent"):
        replacements = fabric_deploy.item_reference_replacements(
            state,
            item,
            "930bbe6f-b256-46b7-a70e-f3dcab99d2c9",
        )
        definition = fabric_deploy.definition_for(
            ROOT / item["source"],
            replacements=replacements,
        )
        staged = fabric_deploy.decoded_definition_text(definition)
        paths = {part["path"] for part in definition["parts"]}

        assert expected[item["displayName"]] in staged
        assert "930bbe6f-b256-46b7-a70e-f3dcab99d2c9" in staged
        assert "<PROPERTY_ASSESSMENT_" not in staged
        assert "<FABRIC_WORKSPACE_ID>" not in staged
        assert all(not path.startswith("tests/") for path in paths)


def test_ontology_definition_is_minimal_and_excludes_design_files():
    folder = ROOT / "fabric" / "Property Assessment Ontology.Ontology"

    definition = fabric_deploy.definition_for(folder)
    paths = {part["path"] for part in definition["parts"]}

    assert paths == {".platform", "database.tmdl"}
    assert all(not path.startswith("design/") for path in paths)


def test_get_definition_returns_synchronous_definition():
    expected = {
        "parts": [
            {
                "path": "definition.pbir",
                "payload": base64.b64encode(b"{}").decode("ascii"),
                "payloadType": "InlineBase64",
            }
        ]
    }

    class Session:
        def post(self, url, timeout):
            assert url.endswith(
                "/workspaces/workspace-id/items/report-id/getDefinition"
            )
            assert timeout == 120
            return SimpleNamespace(
                status_code=200,
                text="",
                json=lambda: {"definition": expected},
            )

    client = fabric_deploy.Fabric.__new__(fabric_deploy.Fabric)
    client.api_base = "https://api.fabric.microsoft.com/v1"
    client.workspace_id = "workspace-id"
    client.session = Session()

    assert client.get_definition("report-id") == expected


def test_notebook_definition_stages_owned_lakehouse_binding_in_memory():
    config = json.loads((ROOT / "config" / "lab.json").read_text(encoding="utf-8"))
    notebook_item = next(item for item in config["items"] if item["type"] == "Notebook")
    state = {
        "items": [
            {
                "id": "f4aa015d-1eb8-4ca3-8c5e-6119300f819b",
                "displayName": "PropertyAssessmentLakehouse",
                "type": "Lakehouse",
            }
        ]
    }
    replacements = fabric_deploy.notebook_replacements(
        state,
        notebook_item,
        "930bbe6f-b256-46b7-a70e-f3dcab99d2c9",
    )
    definition = fabric_deploy.definition_for(
        ROOT / notebook_item["source"],
        replacements=replacements,
    )
    notebook_part = next(
        part for part in definition["parts"] if part["path"] == "notebook-content.py"
    )
    staged = base64.b64decode(notebook_part["payload"]).decode("utf-8")

    assert "<FABRIC_" not in staged
    assert "f4aa015d-1eb8-4ca3-8c5e-6119300f819b" in staged
    assert "930bbe6f-b256-46b7-a70e-f3dcab99d2c9" in staged


def test_generated_fixture_upload_paths_are_deterministic():
    uploads = fabric_deploy.generated_fixture_uploads("lakehouse-id")
    remote_paths = [remote for _local, remote in uploads]

    assert remote_paths == [
        "lakehouse-id/Files/landing/property-assessment/sql/assessments.csv",
        "lakehouse-id/Files/landing/property-assessment/sql/buildings.csv",
        "lakehouse-id/Files/landing/property-assessment/sql/parcels.csv",
        "lakehouse-id/Files/landing/property-assessment/sql/sales.csv",
        "lakehouse-id/Files/landing/property-assessment/cosmos/property_profiles.json",
        "lakehouse-id/Files/landing/property-assessment/cosmos/property_profiles.jsonl",
        "lakehouse-id/Files/landing/property-assessment/adls/assessment_appeals.json",
        "lakehouse-id/Files/landing/property-assessment/adls/assessment_appeals.parquet",
    ]


def test_onelake_directory_creation_skips_artifact_and_files_roots():
    created = []

    class Directory:
        def __init__(self, path):
            self.path = path

        def create_directory(self):
            created.append(self.path)

    file_system = SimpleNamespace(
        get_directory_client=lambda path: Directory(path)
    )

    fabric_deploy.ensure_onelake_directory(
        file_system,
        "lakehouse-id/Files/landing/property-assessment/sql",
    )

    assert created == [
        "lakehouse-id/Files/landing",
        "lakehouse-id/Files/landing/property-assessment",
        "lakehouse-id/Files/landing/property-assessment/sql",
    ]
    assert "" not in created
    assert "lakehouse-id" not in created
    assert "lakehouse-id/Files" not in created


def test_verify_gold_tables_accepts_default_schema_paths(monkeypatch):
    class Directory:
        def __init__(self, path):
            self.path = path

        def get_directory_properties(self):
            if "/Tables/dbo/" not in self.path:
                raise ResourceNotFoundError("not found")
            return {"path": self.path}

    file_system = SimpleNamespace(
        get_directory_client=lambda path: Directory(path)
    )
    monkeypatch.setattr(fabric_deploy, "onelake_file_system", lambda _workspace: file_system)

    result = fabric_deploy.verify_gold_tables("workspace-id", "lakehouse-id")

    assert set(result) == set(fabric_deploy.GOLD_TABLES)
    assert all("/Tables/dbo/" in path for path in result.values())


def test_run_notebook_submits_job_and_polls_completed(monkeypatch):
    calls = {}

    class Session:
        def post(self, url, json, timeout):
            calls["post"] = (url, json, timeout)
            return SimpleNamespace(
                status_code=202,
                headers={"Location": "https://job.example/instance", "Retry-After": "1"},
                content=b"",
                text="",
            )

        def get(self, url, timeout):
            calls["get"] = (url, timeout)
            return SimpleNamespace(
                status_code=200,
                headers={},
                text='{"status":"Completed"}',
                json=lambda: {"status": "Completed"},
            )

    client = fabric_deploy.Fabric.__new__(fabric_deploy.Fabric)
    client.api_base = "https://api.fabric.microsoft.com/v1"
    client.workspace_id = "workspace-id"
    client.session = Session()
    monotonic_values = iter([0, 1])
    monkeypatch.setattr(fabric_deploy.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(fabric_deploy.time, "sleep", lambda _seconds: None)

    result = client.run_notebook("notebook-id")

    assert result["status"] == "Completed"
    assert calls["post"][0].endswith(
        "/workspaces/workspace-id/items/notebook-id/jobs/instances?jobType=RunNotebook"
    )
    assert calls["post"][1] == {"executionData": {}}
    assert calls["get"] == ("https://job.example/instance", (30, 120))
