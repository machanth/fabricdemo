# Step 6 - Generation 2 ontology

**Objective (25-55 min):** deploy the source-controlled shell and bind it to Gold data.

```powershell
python .\scripts\fabric_deploy.py --include-preview
```

The REST payload is the officially supported minimal Generation 2 shell: item-root `.platform` plus `database.tmdl` at compatibility level `1000000`. Fabric synthesizes the default model and namespace on readback. `design/intended-ontology.json` source-controls the intended Parcel, Assessment, Sale, and Appeal entities and relationships but is excluded from the deployed definition because Gold bindings remain tenant/preview dependent.

In the Ontology UI, bind entity properties to `dim_property`, `fact_assessment`, `fact_sale`, and `fact_appeal`; map `parcelId`; validate one-to-many cardinality; and save. `python .\scripts\fabric_deploy.py --verify` invokes `getDefinition` and requires definition parts before success.

**Explore:** ask the ontology view to trace Parcel -> Assessment and Parcel -> Appeal. Identify properties that need synonyms such as valuation, tax roll, and review request.

**Checkpoint/evidence:** item ID, generation/readback, entity diagram, bound tables, and validation state.

**Troubleshooting:** Ontology is preview/region/capacity dependent. If REST rejects the minimal shell, retain `design/intended-ontology.json`, create Gen2 in UI, follow the exact bindings above, and record status/body without tokens.
