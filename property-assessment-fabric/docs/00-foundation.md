# Step 0 - Foundation and preflight

**Objective (15-30 min):** prove the workstation, identity, configuration, and ownership model are safe before creating resources.

```powershell
python -m pip install -r .\requirements.txt
.\scripts\preflight.ps1
.\scripts\preflight.ps1 -RequireAzure
python .\scripts\fabric_deploy.py --dry-run
```

The scripts support Azure CLI user, service principal, managed identity, and federated workload identity through the Azure Identity credential chain. Secrets remain outside Git. `.state/owned-items.json` is written only after successful Fabric creation and prevents cross-workspace teardown or mutation of an unowned same-name item.

**Explore:** Which tenant settings are required for service principals and preview items? Why is a group preferable to a person as Azure SQL Entra administrator?

**Checkpoint/evidence:** preflight output, dry-run JSON, and a short note identifying the intended identity and Fabric workspace role.

**Troubleshooting:** install missing commands; use `az account show`; verify Fabric token acquisition; do not paste tokens into logs or issues.

