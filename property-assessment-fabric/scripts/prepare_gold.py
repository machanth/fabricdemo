from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from fabric_deploy import (
    ROOT,
    Fabric,
    definition_for,
    notebook_replacements,
    owned_item,
    persist_state,
    upload_generated_fixtures,
    wait_for_gold_tables,
)


def main() -> None:
    config = json.loads((ROOT / "config" / "lab.json").read_text(encoding="utf-8"))
    workspace_id = os.getenv("FABRIC_WORKSPACE_ID", config["workspace"]["id"])
    api_base = os.getenv("FABRIC_API_BASE", "https://api.fabric.microsoft.com/v1")
    state_path = ROOT / config["ownership"]["stateFile"]
    if not state_path.exists():
        raise RuntimeError("Ownership state is missing. Deploy the Lakehouse and Notebook first.")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state["workspaceId"] != workspace_id:
        raise RuntimeError("Ownership state belongs to another workspace.")

    lakehouse = owned_item(state, "PropertyAssessmentLakehouse", "Lakehouse")
    notebook = owned_item(state, "PropertyAssessmentMedallion", "Notebook")
    notebook_config = next(
        item for item in config["items"]
        if item["displayName"] == notebook["displayName"] and item["type"] == "Notebook"
    )

    uploaded = upload_generated_fixtures(workspace_id, lakehouse["id"])
    for remote_path in uploaded:
        print(f"uploaded {remote_path}")

    client = Fabric(workspace_id, api_base)
    replacements = notebook_replacements(state, notebook_config, workspace_id)
    definition = definition_for(ROOT / notebook_config["source"], replacements=replacements)
    client.update_definition(notebook["id"], definition)
    print(f"bound notebook {notebook['id']} to Lakehouse {lakehouse['id']}")

    job = client.run_notebook(notebook["id"])
    print(f"notebook job completed with status {job.get('status', 'Completed')}")

    gold_tables = wait_for_gold_tables(workspace_id, lakehouse["id"])
    evidence = {
        "workspaceId": workspace_id,
        "lakehouseId": lakehouse["id"],
        "notebookId": notebook["id"],
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "uploadedFiles": uploaded,
        "goldTables": gold_tables,
        "jobStatus": job.get("status", "Completed"),
        "synthetic": True,
    }
    evidence_path = ROOT / ".state" / "gold-readiness.json"
    persist_state(evidence_path, evidence)
    print(f"Gold readiness passed for {len(gold_tables)} tables.")


if __name__ == "__main__":
    main()
