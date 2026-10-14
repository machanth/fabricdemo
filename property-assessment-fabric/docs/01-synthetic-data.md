# Step 1 - Deterministic synthetic data

**Objective (20-40 min):** generate relational, document, JSON, and Parquet records with shared `parcelId` keys.

```powershell
python .\scripts\generate_data.py --scale 240 --seed 20261013
python .\scripts\validate_lab.py
python -m pytest .\tests -q
```

Expected counts at scale 240: 240 parcels, 240 buildings, 480 assessments, 80 sales, 240 profiles, and 300 appeals. `contracts/dataset-contract.json` defines required fields and cross-source quality rules. `seed.generated.sql` is deterministic and idempotent after the schema script clears tables in dependency order.

**Explore:** Which class has the greatest lot/value spread? Which appeal reasons are overrepresented? How does changing scale affect counts without changing the first generated parcel?

**Checkpoint/evidence:** `manifest.json`, identical JSON/Parquet appeal IDs, zero unknown parcel keys, and passing tests.

**Troubleshooting:** install DuckDB/PyArrow; delete only `data/generated` if regenerating; never substitute real addresses or owner data.

