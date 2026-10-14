from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from fabric_deploy import Fabric


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete only Fabric items recorded as owned by this lab.")
    parser.add_argument("--confirm", required=True, help="Must equal DELETE-OWNED-PROPERTY-ASSESSMENT-ITEMS.")
    args = parser.parse_args()
    if args.confirm != "DELETE-OWNED-PROPERTY-ASSESSMENT-ITEMS":
        raise SystemExit("Confirmation phrase did not match; nothing deleted.")
    config = json.loads((ROOT / "config" / "lab.json").read_text(encoding="utf-8"))
    state_path = ROOT / config["ownership"]["stateFile"]
    if not state_path.exists():
        raise SystemExit("No ownership state exists; nothing deleted.")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    workspace_id = os.getenv("FABRIC_WORKSPACE_ID", config["workspace"]["id"])
    if state["workspaceId"] != workspace_id:
        raise SystemExit("Ownership state workspace mismatch; refusing teardown.")
    client = Fabric(workspace_id, os.getenv("FABRIC_API_BASE", "https://api.fabric.microsoft.com/v1"))
    for item in reversed(state["items"]):
        client.request("DELETE", f"/workspaces/{workspace_id}/items/{item['id']}")
        print(f"deleted {item['type']}: {item['displayName']} ({item['id']})")
    state_path.unlink()


if __name__ == "__main__":
    main()

