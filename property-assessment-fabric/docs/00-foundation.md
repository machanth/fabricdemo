# Step 0 - Foundation and preflight

**Objective (15-30 min):** prove the workstation, identity, configuration, and ownership model are safe before creating resources.

```powershell
python -m pip install -r .\requirements.txt
.\scripts\preflight.ps1
.\scripts\preflight.ps1 -RequireAzure
python .\scripts\fabric_deploy.py --dry-run
```

The Fabric deployment script supports complete process-scoped `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` client credentials without Azure CLI. It rejects partial configuration and never logs or persists the secret. Azure CLI remains supported for interactive Fabric access and is still required by the Azure source provisioning scripts. `.state/owned-items.json` is written only after successful Fabric creation and prevents cross-workspace teardown or mutation of an unowned same-name item.

Noninteractive access check:

```powershell
# Inject all three AZURE_* values through the calling process/secret manager.
.\scripts\preflight.ps1 -RequireFabricAccess
python .\scripts\fabric_deploy.py --check-access
```

**Explore:** Which tenant settings are required for service principals and preview items? Why is a group preferable to a person as Azure SQL Entra administrator?

**Checkpoint/evidence:** preflight output, dry-run JSON, and a short note identifying the intended identity and Fabric workspace role.

**Troubleshooting:** client credentials must be complete and process-scoped; the service principal needs Fabric API tenant permission plus workspace Contributor/Admin; use `az account show` only for the CLI path; never paste tokens or secrets into logs or issues.
