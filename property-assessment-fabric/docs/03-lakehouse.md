# Step 3 - Lakehouse medallion layers

**Objective (35-60 min):** run `PropertyAssessmentMedallion` against the attached `PropertyAssessmentLakehouse`.

```powershell
python .\scripts\prepare_gold.py
```

This command uploads fixtures, stages the owned workspace/Lakehouse IDs into the notebook metadata, updates the deployed notebook, submits the Fabric `RunNotebook` job, polls to completion, and verifies the five managed Delta tables through OneLake. It can be rerun safely because source uploads and notebook writes are overwrite/idempotent.

The notebook writes five Bronze tables, four Silver tables, and five Gold tables. It adds source/audit hashes, types columns, removes duplicates, validates `parcelId`, checks assessment arithmetic, and leaves nullable `aiSentiment`, `aiSummary`, `aiTheme`, and `aiUrgencyScore` columns for enrichment.

The committed `notebook-content.py` is Fabric Git source, not a conventional standalone Python script: it must retain the exact `# Fabric notebook source` first line, LF line endings, notebook-level metadata, `# CELL ********************` separators, and per-cell language metadata.

**Explore:** inspect every landing folder before running; compare Bronze nested profiles to Silver flattened business fields; ask which neighborhood has the highest average assessment, which appeal reason dominates, whether every appeal joins to a parcel, and which Gold fact has the widest value distribution.

**Checkpoint/evidence:** uploaded path list, notebook item/job status, `dim_property`, `dim_date`, `fact_assessment`, `fact_sale`, and `fact_appeal` Delta-log paths, and zero failed notebook assertions. `.state/gold-readiness.json` contains nonsecret run evidence.

**Troubleshooting:** attach the correct Lakehouse; confirm landing paths and case; rerun from Bronze after source changes; do not suppress assertion failures.
