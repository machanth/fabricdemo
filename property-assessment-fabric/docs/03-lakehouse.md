# Step 3 - Lakehouse medallion layers

**Objective (35-60 min):** run `PropertyAssessmentMedallion` against the attached `PropertyAssessmentLakehouse`.

The notebook writes five Bronze tables, four Silver tables, and five Gold tables. It adds source/audit hashes, types columns, removes duplicates, validates `parcelId`, checks assessment arithmetic, and leaves nullable `aiSentiment`, `aiSummary`, `aiTheme`, and `aiUrgencyScore` columns for enrichment.

**Explore:** force one unknown `parcelId` in a copy and observe the assertion; compare Bronze nested profiles to Silver flattened business fields; identify skew by neighborhood.

**Checkpoint/evidence:** `dim_property`, `dim_date`, `fact_assessment`, `fact_sale`, and `fact_appeal` are Delta tables; every assertion passes.

**Troubleshooting:** attach the correct Lakehouse; confirm landing paths and case; rerun from Bronze after source changes; do not suppress assertion failures.
