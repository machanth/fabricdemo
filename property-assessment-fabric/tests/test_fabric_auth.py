import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
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
