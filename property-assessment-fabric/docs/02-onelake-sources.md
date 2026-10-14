# Step 2 - Azure sources and OneLake exploration

**Objective (30-75 min):** deploy or inspect Azure sources, then expose them to Fabric without embedding credentials.

```powershell
.\scripts\deploy_sources.ps1 -PlanOnly
.\scripts\deploy_sources.ps1
.\scripts\seed_sources.ps1
```

For the deterministic lab path, deploy the Lakehouse and Notebook, then run:

```powershell
python .\scripts\prepare_gold.py
```

The command uses the process credential with the official OneLake DFS endpoint, workspace ID as the filesystem, and owned Lakehouse ID as the item path. It treats the workspace filesystem root, Lakehouse artifact root, and managed `Files` root as platform-owned; it creates only `Files/landing/...` descendants. It overwrites deterministic files under `Files/landing/property-assessment/{sql,cosmos,adls}`, then binds/runs the notebook and verifies Gold. No storage key, SAS, token, endpoint ID, or secret is logged or persisted.

For the Azure-source extension, create managed connections for Azure SQL, Cosmos DB, and ADLS Gen2 using organizational identity or an approved connection. Use mirroring where your capacity/region supports it. Otherwise create pipelines to land SQL/Cosmos extracts and an ADLS Gen2 shortcut to `assessment-data/appeals`. Shortcut definitions are deliberately not committed because their schema and connection/target values are environment-specific.

Inspect Lakehouse **Files** and compare SQL CSV row shape, nested Cosmos profile documents, appeal JSON narratives, and Parquet schema. Confirm the deterministic path and file sizes in the `prepare_gold.py` output.

**Checkpoint/evidence:** uploaded OneLake paths, source endpoint names, optional item/connection IDs and shortcut paths, plus screenshots of Files. A precise `401`, `403`, capacity, region, or tenant-setting blocker is acceptable evidence; an unattempted claim is not.

**Troubleshooting:** allow RBAC propagation; use storage `--auth-mode login`; grant Cosmos data-plane contributor; grant SQL database roles separately from Azure RBAC.
