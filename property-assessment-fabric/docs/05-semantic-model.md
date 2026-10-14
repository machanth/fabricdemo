# Step 5 - Direct Lake semantic model and thin report

**Objective (35-70 min):** bind the TMDL model to the Lakehouse, validate relationships/measures, and open the thin PBIR report.

Use Fabric Git integration, REST definition deployment, or Power BI Desktop PBIP. Replace the generic `PropertyAssessmentLakehouse` expression through a supported source-binding workflow. Confirm one-to-many filters from dimensions to facts and mark `DimDate[Date]` as the date column if the deployment surface does not retain it.

The TMDL definition uses standard folder serialization: `model.tmdl` contains only model properties and annotations; tables are auto-discovered from `definition/tables`, relationships from the root `relationships.tmdl`, and each RLS role has its own file under `definition/roles`. Do not add `ref table` or `ref role` lines to `model.tmdl`.

Measures include Total/average assessed value, illustrative estimated tax, sale value, assessment-to-sale ratio, appeal count, resolution rate, and requested adjustment. Technical keys are hidden. `ResidentialReviewer` sees RES/MUR; `CommercialReviewer` sees COM/AGR.

**Explore/checkpoint:** test totals by tax year, drill neighborhood -> parcel, and use **View as** for both roles. Capture the model diagram, measure cards/table, and persona results.

**Troubleshooting:** Direct Lake needs a valid Lakehouse binding; RLS roles require membership assignment in the service; the report is deliberately thin and may need one UI save to materialize visuals in your PBIR version.
