# Step 8 - Governance, operations, verification, teardown

**Objective (30-60 min):** prove the solution is discoverable, governed, observable, and safely removable.

1. Open lineage from report/data agent back through semantic model, Lakehouse/Warehouse, and sources.
2. In OneLake Catalog, add descriptions, domain, contacts, sensitivity labels, and **Promoted** endorsement. Use **Certified** only with an authorized reviewer.
3. In Purview, capture scan/catalog evidence if configured; otherwise record the exact tenant/subscription prerequisite.
4. Run the notebook at scale 240 and a larger approved scale, then capture Fabric Capacity Metrics CU/time by item. Never create uncontrolled load.
5. Run local validation again and list deployed item IDs/readback status.

**Verification checklist:** generated counts match contract; Gold joins have zero unknown parcels; Warehouse queries work; Direct Lake measures work; both RLS personas differ; ontology bindings validate; agent answers carry the synthetic warning; lineage is complete or gaps are documented.

**Safe teardown:**

```powershell
python .\scripts\fabric_teardown.py --confirm DELETE-OWNED-PROPERTY-ASSESSMENT-ITEMS
```

Only IDs in `.state/owned-items.json` are deleted. Azure source teardown is manual by design: review `.state/azure-sources.json`, verify the resource group contains only lab-owned synthetic resources, then delete that exact resource group through your approved process.

**Checkpoint/evidence:** lineage screenshot, Catalog/Purview evidence, Capacity Metrics screenshot, final verification output, and teardown dry review.

**Troubleshooting:** missing lineage often indicates manual file copies; missing metrics can reflect reporting delay; endorsement and Purview roles are separate from workspace roles.

