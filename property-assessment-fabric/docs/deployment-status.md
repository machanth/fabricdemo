# Deployment status

Checked on 2026-10-13 against target workspace `MaddysWS` (`930bbe6f-b256-46b7-a70e-f3dcab99d2c9`).

- Local data generation: **passed** at scale 240 and seed 20261013.
- Contract/artifact validation: **passed**.
- Unit tests: **8 passed**, including display-name policy, client-credential selection, partial-configuration rejection, and authorization-header safety tests.
- Fabric deployment dry run: **passed**; four automatable non-preview items selected. The thin PBIR report is source controlled but intentionally manual until its semantic-model binding is materialized.
- Live Fabric authentication/readback: **client-credential authentication succeeded in the parent session**. The first create request failed before an item was created: `POST /v1/workspaces/930bbe6f-b256-46b7-a70e-f3dcab99d2c9/items` returned HTTP 400, request ID `258759b8-094f-4b80-bba5-83972454e223`, `InvalidInput / InvalidParameter`, because `Property Assessment` was invalid for the Lakehouse display name. All configured Fabric display names are now unique alphanumeric identifiers without spaces, and validation rejects regressions before an API call.
- Azure source deployment: **not attempted**. Azure SQL, Cosmos DB, and ADLS provisioning remains separate and still requires Azure CLI.

Exact noninteractive sequence after the parent process injects `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET`:

```powershell
$env:FABRIC_WORKSPACE_ID = "930bbe6f-b256-46b7-a70e-f3dcab99d2c9"
.\scripts\preflight.ps1 -RequireFabricAccess
python .\scripts\fabric_deploy.py
python .\scripts\fabric_deploy.py --verify
Remove-Item Env:AZURE_CLIENT_SECRET -ErrorAction SilentlyContinue
```

Required platform values: workspace `930bbe6f-b256-46b7-a70e-f3dcab99d2c9` must be assigned to an eligible Fabric capacity; the service principal must be allowed in Fabric tenant settings and assigned Contributor/Admin on the workspace. Post-create source values remain tenant-specific: the Lakehouse attachment/SQL endpoint for semantic-model binding, `Files/landing/property-assessment` data, and deployed semantic-model/ontology item IDs before Data Agent publication.
