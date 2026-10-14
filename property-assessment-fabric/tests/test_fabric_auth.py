import sys
from pathlib import Path

import pytest
from azure.identity import AzureCliCredential, ClientSecretCredential


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
