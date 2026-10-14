# Step 4 - Warehouse star outputs

**Objective (25-50 min):** create the Warehouse, run `deploy.sql`, and load Gold outputs through a Fabric pipeline or `COPY INTO` from exported Parquet.

The Warehouse definition is intentionally split: REST creates the item, while SQL DDL runs in the Warehouse editor because source IDs, endpoint names, and cross-endpoint capabilities vary by tenant. Source control contains dimensions, facts, and the equity view.

```sql
SELECT TOP 20 * FROM assessment.vwNeighborhoodEquity
ORDER BY AverageAssessmentToSaleRatio DESC;

SELECT ReasonCode, COUNT(*) AppealCount
FROM assessment.FactAppeal GROUP BY ReasonCode ORDER BY AppealCount DESC;

SELECT p.PropertyClassCode, AVG(a.ConfidenceScore) AverageConfidence
FROM assessment.FactAssessment a JOIN assessment.DimProperty p ON p.PropertyKey=a.PropertyKey
GROUP BY p.PropertyClassCode;
```

**Checkpoint/evidence:** objects exist, rows are loaded, and all three queries return plausible fictional results.

**Troubleshooting:** `CREATE SCHEMA` is not idempotent after first run; use a clean lab Warehouse or guard it in your tenant-specific deployment. Empty tables mean load was not run.

