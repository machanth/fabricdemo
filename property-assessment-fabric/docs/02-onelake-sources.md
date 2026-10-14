# Step 2 - Azure sources and OneLake exploration

**Objective (30-75 min):** deploy or inspect Azure sources, then expose them to Fabric without embedding credentials.

```powershell
.\scripts\deploy_sources.ps1 -PlanOnly
.\scripts\deploy_sources.ps1
.\scripts\seed_sources.ps1
```

In Fabric, first deploy the Lakehouse without shortcut metadata. Then create managed connections for Azure SQL, Cosmos DB, and ADLS Gen2 using organizational identity or an approved connection. Use mirroring where your capacity/region supports it. Otherwise create pipelines to land SQL/Cosmos extracts and an ADLS Gen2 shortcut to `assessment-data/appeals`. Shortcut definitions are deliberately not committed because their schema and connection/target values are environment-specific. Upload local generated data to `Files/landing/property-assessment/{sql,cosmos,adls}` when Azure deployment is unavailable.

Inspect Lakehouse **Files** and compare CSV row shape, nested profile documents, JSON appeal narratives, and Parquet schema. Record connection IDs outside Git or replace placeholders only in a deployment environment.

**Checkpoint/evidence:** source endpoint names, item/connection IDs, shortcut paths, and screenshots of Files. A precise `401`, `403`, capacity, region, or tenant-setting blocker is acceptable evidence; an unattempted claim is not.

**Troubleshooting:** allow RBAC propagation; use storage `--auth-mode login`; grant Cosmos data-plane contributor; grant SQL database roles separately from Azure RBAC.
