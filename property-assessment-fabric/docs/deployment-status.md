# Deployment status

Checked on 2026-10-13 against target workspace `MaddysWS` (`930bbe6f-b256-46b7-a70e-f3dcab99d2c9`).

- Local data generation: **passed** at scale 240 and seed 20261013.
- Contract/artifact validation: **passed**.
- Unit tests: **16 passed**, including exact Fabric notebook prologue/LF validation, exclusion of shortcut metadata, terminal-failure reconciliation, empty-202 handling, display-name policy, LRO timeout retry, read-only discovery, accepted-operation persistence shape, client-credential selection, and authorization-header safety.
- Fabric deployment dry run: **passed**; four automatable non-preview items selected. The thin PBIR report is source controlled but intentionally manual until its semantic-model binding is materialized.
- Live Fabric authentication/readback: **client-credential authentication succeeded in the parent session**. The first create request failed before an item was created: `POST /v1/workspaces/930bbe6f-b256-46b7-a70e-f3dcab99d2c9/items` returned HTTP 400, request ID `258759b8-094f-4b80-bba5-83972454e223`, `InvalidInput / InvalidParameter`, because `Property Assessment` was invalid for the Lakehouse display name. All configured Fabric display names are now unique alphanumeric identifiers without spaces, and validation rejects regressions before an API call.
- Second live attempt: authentication/preflight passed and the create entered long-running-operation polling. The redirect-host poll timed out after 120 seconds, so creation is **indeterminate**. The deployer now retries transient connect/read/SSL poll failures with bounded backoff, follows `Retry-After`, records accepted operation identity before polling, and reconciles exact live matches before any create.
- Third live attempt: Fabric returned HTTP 202 with an empty body. The accepted-operation callback treated a `None` JSON payload as an object and failed before state persistence, so creation is again **indeterminate**. Empty 202 bodies are now normalized to `{}` and operation identity is captured from `Location` and operation headers before polling.
- The operation later completed definitively as **Failed**: `FailedToParseContent`, message `Failed to parse shortcuts.metadata.json file. Please make sure the content matches expected schema.`, created `2026-10-14T03:08:07.3818461Z`, updated `2026-10-14T03:08:08.8673045Z`. The unsupported placeholder file has been removed. Lakehouse shortcuts are now an explicit post-create REST/UI step using environment-specific connections. On the next normal deploy, persisted accepted operations are re-polled and a terminal failed operation is marked `Failed` so it cannot block a safe retry.
- Next live progress: `PropertyAssessmentLakehouse` was created and recorded as item `f4aa015d-1eb8-4ca3-8c5e-6119300f819b`. Notebook creation failed definitively with `PyToIPynbFailure`, trace ID `39fd87bc-6390-4bfe-864e-0dde8e280689`, because the Python source prologue was not the exact Fabric Git format; created `2026-10-14T03:10:19.7942998Z`, failed `2026-10-14T03:10:20.1612479Z`. The notebook now begins with exact bytes `# Fabric notebook source` followed by LF, notebook metadata, official cell separators, and per-cell language metadata. Validation rejects CRLF or prologue/cell metadata regressions. Ownership state retains the successful Lakehouse and marks the notebook operation failed.
- Azure source deployment: **not attempted**. Azure SQL, Cosmos DB, and ADLS provisioning remains separate and still requires Azure CLI.

Exact noninteractive sequence after the parent process injects `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET`:

```powershell
$env:FABRIC_WORKSPACE_ID = "930bbe6f-b256-46b7-a70e-f3dcab99d2c9"
.\scripts\preflight.ps1 -RequireFabricAccess
python .\scripts\fabric_deploy.py --discover
python .\scripts\fabric_deploy.py
python .\scripts\fabric_deploy.py --verify
Remove-Item Env:AZURE_CLIENT_SECRET -ErrorAction SilentlyContinue
```

Required platform values: workspace `930bbe6f-b256-46b7-a70e-f3dcab99d2c9` must be assigned to an eligible Fabric capacity; the service principal must be allowed in Fabric tenant settings and assigned Contributor/Admin on the workspace. Post-create source values remain tenant-specific: the Lakehouse attachment/SQL endpoint for semantic-model binding, `Files/landing/property-assessment` data, and deployed semantic-model/ontology item IDs before Data Agent publication.

Interpret discovery before retry: one exact match with `managedMarker: true` is safely adopted on the next normal deploy; an unmarked or multiple match is a hard stop; zero matches with a recorded `Accepted` operation remains indeterminate and must not trigger another create until the operation settles.
