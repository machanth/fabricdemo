# Step 5 - Direct Lake semantic model and thin report

**Objective (35-70 min):** bind the TMDL model to the Lakehouse, validate relationships/measures, and open the thin PBIR report.

Use Fabric Git integration, REST definition deployment, or Power BI Desktop PBIP. The committed shared expression contains `<FABRIC_SQL_ENDPOINT>` and `<FABRIC_SQL_DATABASE>` placeholders. At deployment, the script reads `PropertyAssessmentLakehouse` through `GET /workspaces/{workspaceId}/lakehouses/{itemId}`, requires a ready `sqlEndpointProperties`, and stages `Sql.Database(connectionString, sqlEndpointId)` in memory. No workspace, endpoint, or tenant-specific source value is committed. Confirm one-to-many filters from dimensions to facts and mark `DimDate[Date]` as the date column if the deployment surface does not retain it.

The semantic definition can be deployed only against a provisioned Lakehouse SQL endpoint. Run the medallion notebook first to create `dim_property`, `dim_date`, `fact_assessment`, `fact_sale`, and `fact_appeal`; until those Gold Delta tables are visible through the endpoint, model framing or queries can fail even if item creation succeeds.

The TMDL definition uses standard folder serialization: `model.tmdl` contains only model properties and annotations; tables are auto-discovered from `definition/tables`, relationships from the root `relationships.tmdl`, and each RLS role has its own file under `definition/roles`. Do not add `ref table` or `ref role` lines to `model.tmdl`.

Business descriptions use TMDL `///` documentation comments immediately above tables, columns, and measures. This preserves descriptions while avoiding `description:` lines rejected by the current Fabric workload parser. Other colon-style lines are limited to validated TOM properties such as `dataType`, `formatString`, `sourceColumn`, partition mode, and Direct Lake entity source fields.

Measures include Total/average assessed value, illustrative estimated tax, sale value, assessment-to-sale ratio, appeal count, resolution rate, and requested adjustment. Technical keys are hidden. `ResidentialReviewer` sees RES/MUR; `CommercialReviewer` sees COM/AGR.

**Explore/checkpoint:** test totals by tax year, drill neighborhood -> parcel, and use **View as** for both roles. Capture the model diagram, measure cards/table, and persona results.

`PropertyAssessmentOverview` is deployed through the supported Report definition API. Its committed `definition.pbir` keeps a semantic-model placeholder; deployment resolves the owned `PropertyAssessmentModel` ID and changes the binding to `byConnection`/`semanticModelId` only in memory. `--verify` reads the Report definition back and confirms the staged model ID is present.

**Troubleshooting:** Direct Lake needs a valid Lakehouse binding; RLS roles require membership assignment in the service; the report is deliberately thin and contains an empty overview page so hackers can build visuals without overwriting a supplied answer.
