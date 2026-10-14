from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import time
from pathlib import Path

import requests
from azure.identity import AzureCliCredential, ClientSecretCredential, DefaultAzureCredential


ROOT = Path(__file__).resolve().parents[1]
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
TEXT_EXCLUDES = {"README.md", "deploy.sql"}
CLIENT_CREDENTIAL_ENV_VARS = ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")


def credential_mode() -> str:
    configured = [name for name in CLIENT_CREDENTIAL_ENV_VARS if os.getenv(name)]
    if configured and len(configured) != len(CLIENT_CREDENTIAL_ENV_VARS):
        missing = [name for name in CLIENT_CREDENTIAL_ENV_VARS if not os.getenv(name)]
        raise RuntimeError(f"Incomplete Fabric client credentials. Missing environment variables: {', '.join(missing)}")
    if len(configured) == len(CLIENT_CREDENTIAL_ENV_VARS):
        return "client-secret"
    if shutil.which("az"):
        return "azure-cli"
    return "default-azure-credential"


def credential():
    mode = credential_mode()
    if mode == "client-secret":
        return ClientSecretCredential(
            tenant_id=os.environ["AZURE_TENANT_ID"],
            client_id=os.environ["AZURE_CLIENT_ID"],
            client_secret=os.environ["AZURE_CLIENT_SECRET"],
        )
    if mode == "azure-cli":
        return AzureCliCredential()
    return DefaultAzureCredential(
        exclude_environment_credential=True,
        exclude_cli_credential=True,
        exclude_interactive_browser_credential=True,
    )


def token() -> str:
    return credential().get_token(FABRIC_SCOPE).token


class Fabric:
    def __init__(self, workspace_id: str, api_base: str) -> None:
        self.workspace_id = workspace_id
        self.api_base = api_base.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token()}", "Content-Type": "application/json"})

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        response = self.session.request(method, f"{self.api_base}{path}", timeout=120, **kwargs)
        if response.status_code == 202:
            location = response.headers.get("Location")
            retry_after = int(response.headers.get("Retry-After", "5"))
            while location:
                time.sleep(retry_after)
                operation = self.session.get(location, timeout=120)
                if operation.status_code >= 400:
                    raise RuntimeError(f"Fabric operation failed: {operation.status_code} {operation.text}")
                payload = operation.json()
                if payload.get("status") in {"Succeeded", "Failed", "Cancelled"}:
                    if payload["status"] != "Succeeded":
                        raise RuntimeError(f"Fabric operation ended as {payload['status']}: {operation.text}")
                    break
                retry_after = int(operation.headers.get("Retry-After", "5"))
            return response
        if response.status_code >= 400:
            raise RuntimeError(f"Fabric API {method} {path} failed: {response.status_code} {response.text}")
        return response

    def list_items(self) -> list[dict]:
        return self.request("GET", f"/workspaces/{self.workspace_id}/items").json().get("value", [])

    def get_workspace(self) -> dict:
        return self.request("GET", f"/workspaces/{self.workspace_id}").json()

    def create(self, item: dict, definition: dict | None) -> dict:
        body = {"displayName": item["displayName"], "type": item["type"], "description": "Fictional property-assessment hackathon lab; managed by property-assessment-fabric."}
        if definition:
            body["definition"] = definition
        response = self.request("POST", f"/workspaces/{self.workspace_id}/items", json=body)
        if response.content:
            return response.json()
        matches = [candidate for candidate in self.list_items() if candidate["displayName"] == item["displayName"] and candidate["type"] == item["type"]]
        if len(matches) != 1:
            raise RuntimeError(f"Unable to resolve created item {item['displayName']}.")
        return matches[0]

    def update_definition(self, item_id: str, definition: dict) -> None:
        self.request("POST", f"/workspaces/{self.workspace_id}/items/{item_id}/updateDefinition", json={"definition": definition})


def definition_for(folder: Path) -> dict | None:
    if not folder.exists():
        return None
    parts = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.name in TEXT_EXCLUDES:
            continue
        relative = path.relative_to(folder).as_posix()
        parts.append({"path": relative, "payload": base64.b64encode(path.read_bytes()).decode("ascii"), "payloadType": "InlineBase64"})
    return {"parts": parts} if parts else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Idempotently deploy supported Fabric item definitions.")
    parser.add_argument("--include-preview", action="store_true", help="Deploy Ontology and DataAgent preview definitions.")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--dry-run", action="store_true")
    operation.add_argument("--check-access", action="store_true", help="Acquire a token and read the target workspace.")
    operation.add_argument("--verify", action="store_true", help="Verify every owned item still exists with the expected type and name.")
    args = parser.parse_args()
    config = json.loads((ROOT / "config" / "lab.json").read_text(encoding="utf-8"))
    workspace_id = os.getenv("FABRIC_WORKSPACE_ID", config["workspace"]["id"])
    api_base = os.getenv("FABRIC_API_BASE", "https://api.fabric.microsoft.com/v1")
    state_path = ROOT / config["ownership"]["stateFile"]
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"workspaceId": workspace_id, "items": []}
    if state["workspaceId"] != workspace_id:
        raise SystemExit("Ownership state belongs to another workspace; refusing deployment.")
    preview_types = {"Ontology", "DataAgent"}
    allowed_modes = {"rest-definition", "create-then-sql", "rest-definition-preview"}
    selected = [item for item in config["items"] if item["automation"] in allowed_modes and (args.include_preview or item["type"] not in preview_types)]
    if args.dry_run:
        print(json.dumps({"workspaceId": workspace_id, "items": selected}, indent=2))
        return
    client = Fabric(workspace_id, api_base)
    if args.check_access:
        workspace = client.get_workspace()
        print(f"Fabric access verified: {workspace.get('displayName', '<unknown>')} ({workspace_id}) using {credential_mode()}.")
        return
    if args.verify:
        if not state["items"]:
            raise RuntimeError("No owned Fabric items are recorded. Deploy supported artifacts before verification.")
        live_by_id = {item["id"]: item for item in client.list_items()}
        failures = []
        for owned in state["items"]:
            live = live_by_id.get(owned["id"])
            if not live:
                failures.append(f"missing {owned['type']} {owned['displayName']} ({owned['id']})")
                continue
            if live["displayName"] != owned["displayName"] or live["type"] != owned["type"]:
                failures.append(f"identity mismatch for {owned['id']}")
                continue
            print(f"verified {owned['type']}: {owned['displayName']} ({owned['id']})")
        if failures:
            raise RuntimeError("Fabric verification failed: " + "; ".join(failures))
        print(f"Verified {len(state['items'])} owned Fabric items in workspace {workspace_id}.")
        return
    existing = client.list_items()
    owned_by_key = {(row["displayName"], row["type"]): row for row in state["items"]}
    for item in selected:
        key = (item["displayName"], item["type"])
        collisions = [candidate for candidate in existing if (candidate["displayName"], candidate["type"]) == key]
        owned = owned_by_key.get(key)
        if collisions and not owned:
            raise RuntimeError(f"Unowned item collision for {key}; rename or explicitly adopt it before deployment.")
        definition = definition_for(ROOT / item["source"])
        if owned:
            if definition and item["type"] != "Warehouse":
                client.update_definition(owned["id"], definition)
            print(f"updated {item['type']}: {item['displayName']} ({owned['id']})")
            continue
        created = client.create(item, None if item["type"] == "Warehouse" else definition)
        record = {"id": created["id"], "displayName": item["displayName"], "type": item["type"]}
        state["items"].append(record)
        owned_by_key[key] = record
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        print(f"created {item['type']}: {item['displayName']} ({created['id']})")
    print("Definitions deployed. Run Warehouse/deploy.sql in the Warehouse SQL editor and bind source IDs where placeholders remain.")


if __name__ == "__main__":
    main()
