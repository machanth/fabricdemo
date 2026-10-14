from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from azure.identity import AzureCliCredential, ClientSecretCredential, DefaultAzureCredential
from requests.exceptions import ConnectTimeout, ReadTimeout, SSLError


ROOT = Path(__file__).resolve().parents[1]
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
TEXT_EXCLUDES = {"README.md", "deploy.sql"}
CLIENT_CREDENTIAL_ENV_VARS = ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")
SAFE_DISPLAY_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]{2,127}$")
MANAGED_DESCRIPTION = "Fictional property-assessment hackathon lab; managed by property-assessment-fabric."
TRANSIENT_POLL_EXCEPTIONS = (ConnectTimeout, ReadTimeout, SSLError)
MAX_TRANSIENT_POLL_FAILURES = 8
MAX_LRO_SECONDS = 900


class FabricOperationFailed(RuntimeError):
    pass


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


def validate_display_names(items: list[dict]) -> None:
    names = [item["displayName"] for item in items]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise RuntimeError(f"Fabric display names must be unique: {', '.join(duplicates)}")
    invalid = [name for name in names if not SAFE_DISPLAY_NAME.fullmatch(name)]
    if invalid:
        raise RuntimeError(
            "Fabric display names must use 3-128 alphanumeric characters, start with a letter, "
            f"and contain no spaces: {', '.join(invalid)}"
        )


class Fabric:
    def __init__(self, workspace_id: str, api_base: str) -> None:
        self.workspace_id = workspace_id
        self.api_base = api_base.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token()}", "Content-Type": "application/json"})

    @staticmethod
    def retry_after_seconds(response: requests.Response, default: int = 5) -> int:
        value = response.headers.get("Retry-After")
        if value and value.isdigit():
            return max(1, min(int(value), 60))
        return default

    def poll_operation(self, location: str, retry_after: int = 5) -> dict:
        deadline = time.monotonic() + MAX_LRO_SECONDS
        transient_failures = 0
        delay = max(1, min(retry_after, 60))
        while time.monotonic() < deadline:
            time.sleep(delay)
            try:
                operation = self.session.get(location, timeout=(30, 120))
            except TRANSIENT_POLL_EXCEPTIONS as exc:
                transient_failures += 1
                if transient_failures > MAX_TRANSIENT_POLL_FAILURES:
                    raise RuntimeError(
                        f"Fabric operation polling remained unavailable after {transient_failures} transient failures."
                    ) from exc
                delay = min(2 ** transient_failures, 30)
                continue
            if operation.status_code >= 400:
                raise FabricOperationFailed(f"Fabric operation failed: {operation.status_code} {operation.text}")
            payload = operation.json()
            status = payload.get("status")
            if status in {"Succeeded", "Failed", "Cancelled"}:
                if status != "Succeeded":
                    raise FabricOperationFailed(f"Fabric operation ended as {status}: {operation.text}")
                return payload
            transient_failures = 0
            delay = self.retry_after_seconds(operation)
        raise RuntimeError(f"Fabric operation polling exceeded {MAX_LRO_SECONDS} seconds.")

    def request(self, method: str, path: str, on_accepted=None, **kwargs) -> requests.Response:
        response = self.session.request(method, f"{self.api_base}{path}", timeout=120, **kwargs)
        if response.status_code == 202:
            location = response.headers.get("Location")
            if not location:
                raise RuntimeError("Fabric returned HTTP 202 without an operation Location header.")
            if on_accepted:
                on_accepted(response)
            self.poll_operation(location, self.retry_after_seconds(response))
            return response
        if response.status_code >= 400:
            raise RuntimeError(f"Fabric API {method} {path} failed: {response.status_code} {response.text}")
        return response

    def list_items(self) -> list[dict]:
        return self.request("GET", f"/workspaces/{self.workspace_id}/items").json().get("value", [])

    def get_workspace(self) -> dict:
        return self.request("GET", f"/workspaces/{self.workspace_id}").json()

    def get_item(self, item_id: str) -> dict:
        return self.request("GET", f"/workspaces/{self.workspace_id}/items/{item_id}").json()

    def create(self, item: dict, definition: dict | None, on_accepted=None) -> dict:
        body = {"displayName": item["displayName"], "type": item["type"], "description": MANAGED_DESCRIPTION}
        if definition:
            body["definition"] = definition
        response = self.request(
            "POST",
            f"/workspaces/{self.workspace_id}/items",
            json=body,
            on_accepted=on_accepted,
        )
        if response.status_code != 202 and response.content:
            payload = response.json()
            if payload.get("id"):
                return payload
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


def persist_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(state_path)


def is_managed_item(client: Fabric, item: dict) -> bool:
    if item.get("description") == MANAGED_DESCRIPTION:
        return True
    detail = client.get_item(item["id"])
    return detail.get("description") == MANAGED_DESCRIPTION


def discovery_report(config: dict, state: dict, existing: list[dict], client: Fabric) -> dict:
    owned_ids = {item["id"] for item in state["items"]}
    results = []
    for configured in config["items"]:
        matches = [
            item
            for item in existing
            if item["displayName"] == configured["displayName"] and item["type"] == configured["type"]
        ]
        reported_matches = []
        for match in matches:
            reported_matches.append(
                {
                    "id": match["id"],
                    "displayName": match["displayName"],
                    "type": match["type"],
                    "recordedOwned": match["id"] in owned_ids,
                    "managedMarker": is_managed_item(client, match),
                }
            )
        results.append(
            {
                "configuredDisplayName": configured["displayName"],
                "type": configured["type"],
                "matchCount": len(matches),
                "matches": reported_matches,
            }
        )
    return {
        "workspaceId": client.workspace_id,
        "readOnly": True,
        "configuredItems": results,
        "pendingOperations": state["operations"],
    }


def accepted_operation(response: requests.Response, item: dict) -> dict:
    location = response.headers["Location"]
    operation_id = (
        response.headers.get("x-ms-operation-id")
        or response.headers.get("requestId")
        or location.rstrip("/").rsplit("/", 1)[-1]
    )
    record = {
        "operationId": operation_id,
        "operationLocation": location,
        "displayName": item["displayName"],
        "type": item["type"],
        "status": "Accepted",
        "acceptedAt": datetime.now(timezone.utc).isoformat(),
    }
    try:
        payload = response.json() or {}
    except (ValueError, AttributeError):
        payload = {}
    early_item_id = payload.get("itemId") or payload.get("id")
    if early_item_id and early_item_id != operation_id:
        record["itemId"] = early_item_id
    return record


def reconcile_pending_operations(client: Fabric, state: dict, state_path: Path) -> None:
    changed = False
    for pending in state["operations"]:
        if pending["status"] != "Accepted":
            continue
        try:
            payload = client.poll_operation(pending["operationLocation"], retry_after=1)
        except FabricOperationFailed as exc:
            pending["status"] = "Failed"
            pending["lastCheckedAt"] = datetime.now(timezone.utc).isoformat()
            pending["error"] = str(exc)
            changed = True
            continue
        except RuntimeError:
            continue
        pending["status"] = "Succeeded"
        pending["lastCheckedAt"] = datetime.now(timezone.utc).isoformat()
        early_item_id = payload.get("itemId") or payload.get("id")
        if early_item_id:
            pending["itemId"] = early_item_id
        changed = True
    if changed:
        persist_state(state_path, state)


def main() -> None:
    parser = argparse.ArgumentParser(description="Idempotently deploy supported Fabric item definitions.")
    parser.add_argument("--include-preview", action="store_true", help="Deploy Ontology and DataAgent preview definitions.")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--dry-run", action="store_true")
    operation.add_argument("--check-access", action="store_true", help="Acquire a token and read the target workspace.")
    operation.add_argument("--discover", action="store_true", help="Read current exact name/type matches without changing state or items.")
    operation.add_argument("--verify", action="store_true", help="Verify every owned item still exists with the expected type and name.")
    args = parser.parse_args()
    config = json.loads((ROOT / "config" / "lab.json").read_text(encoding="utf-8"))
    workspace_id = os.getenv("FABRIC_WORKSPACE_ID", config["workspace"]["id"])
    api_base = os.getenv("FABRIC_API_BASE", "https://api.fabric.microsoft.com/v1")
    state_path = ROOT / config["ownership"]["stateFile"]
    state = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.exists()
        else {"workspaceId": workspace_id, "items": [], "operations": []}
    )
    state.setdefault("operations", [])
    if state["workspaceId"] != workspace_id:
        raise SystemExit("Ownership state belongs to another workspace; refusing deployment.")
    preview_types = {"Ontology", "DataAgent"}
    allowed_modes = {"rest-definition", "create-then-sql", "rest-definition-preview"}
    selected = [item for item in config["items"] if item["automation"] in allowed_modes and (args.include_preview or item["type"] not in preview_types)]
    validate_display_names(config["items"])
    if args.dry_run:
        print(json.dumps({"workspaceId": workspace_id, "items": selected}, indent=2))
        return
    client = Fabric(workspace_id, api_base)
    if args.check_access:
        workspace = client.get_workspace()
        print(f"Fabric access verified: {workspace.get('displayName', '<unknown>')} ({workspace_id}) using {credential_mode()}.")
        return
    if args.discover:
        print(json.dumps(discovery_report(config, state, client.list_items(), client), indent=2))
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
    reconcile_pending_operations(client, state, state_path)
    existing = client.list_items()
    owned_by_key = {(row["displayName"], row["type"]): row for row in state["items"]}
    for item in selected:
        key = (item["displayName"], item["type"])
        collisions = [candidate for candidate in existing if (candidate["displayName"], candidate["type"]) == key]
        owned = owned_by_key.get(key)
        if len(collisions) > 1:
            raise RuntimeError(f"Multiple exact matches exist for {key}; run --discover and resolve the ambiguity.")
        if owned and collisions and collisions[0]["id"] != owned["id"]:
            raise RuntimeError(f"Owned state and live exact match disagree for {key}; run --discover before changing anything.")
        if collisions and not owned:
            candidate = collisions[0]
            if not is_managed_item(client, candidate):
                raise RuntimeError(
                    f"Unowned item collision for {key}. The exact match lacks the deployment marker; "
                    "run --discover and resolve it manually."
                )
            owned = {"id": candidate["id"], "displayName": item["displayName"], "type": item["type"]}
            state["items"].append(owned)
            owned_by_key[key] = owned
            for pending in state["operations"]:
                if pending["displayName"] == item["displayName"] and pending["type"] == item["type"] and pending["status"] == "Accepted":
                    pending["status"] = "Reconciled"
                    pending["itemId"] = candidate["id"]
            persist_state(state_path, state)
            print(f"adopted marked {item['type']}: {item['displayName']} ({candidate['id']})")
        pending_operations = [
            pending
            for pending in state["operations"]
            if pending["displayName"] == item["displayName"]
            and pending["type"] == item["type"]
            and pending["status"] == "Accepted"
        ]
        if not collisions and not owned and pending_operations:
            raise RuntimeError(
                f"An indeterminate accepted operation exists for {key}. Run --discover and wait for reconciliation before retrying create."
            )
        definition = definition_for(ROOT / item["source"])
        if owned:
            if definition and item["type"] != "Warehouse":
                client.update_definition(owned["id"], definition)
            print(f"updated {item['type']}: {item['displayName']} ({owned['id']})")
            continue
        pending_record = None

        def record_accepted(response):
            nonlocal pending_record
            pending_record = accepted_operation(response, item)
            state["operations"].append(pending_record)
            persist_state(state_path, state)

        try:
            created = client.create(
                item,
                None if item["type"] == "Warehouse" else definition,
                on_accepted=record_accepted,
            )
        except FabricOperationFailed as exc:
            if pending_record:
                pending_record["status"] = "Failed"
                pending_record["lastCheckedAt"] = datetime.now(timezone.utc).isoformat()
                pending_record["error"] = str(exc)
                persist_state(state_path, state)
            raise
        record = {"id": created["id"], "displayName": item["displayName"], "type": item["type"]}
        state["items"].append(record)
        owned_by_key[key] = record
        if pending_record:
            pending_record["status"] = "Succeeded"
            pending_record["itemId"] = created["id"]
        persist_state(state_path, state)
        print(f"created {item['type']}: {item['displayName']} ({created['id']})")
    print("Definitions deployed. Run Warehouse/deploy.sql in the Warehouse SQL editor and bind source IDs where placeholders remain.")


if __name__ == "__main__":
    main()
