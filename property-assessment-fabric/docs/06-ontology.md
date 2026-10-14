# Step 6 - Generation 2 ontology

**Objective (25-55 min):** deploy the source-controlled shell and bind it to Gold data.

```powershell
python .\scripts\fabric_deploy.py --include-preview
```

The definition declares Parcel, Assessment, and Appeal entities and one-to-many relationships. In the Ontology UI, bind entity properties to `dim_property`, `fact_assessment`, and `fact_appeal`; add Sale and Inspection if supported; map `propertyKey`/`parcelId`; validate cardinality; and save. Read the definition back or inspect the item before claiming success.

**Explore:** ask the ontology view to trace Parcel -> Assessment and Parcel -> Appeal. Identify properties that need synonyms such as valuation, tax roll, and review request.

**Checkpoint/evidence:** item ID, generation/readback, entity diagram, bound tables, and validation state.

**Troubleshooting:** Ontology is preview/region/capacity dependent. If REST rejects the definition, retain the shell, create Gen2 in UI, follow the exact bindings above, and record status/body without tokens.

