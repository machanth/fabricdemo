# Deployment status

Checked on 2026-10-13 against target workspace `MaddysWS` (`930bbe6f-b256-46b7-a70e-f3dcab99d2c9`).

- Local data generation: **passed** at scale 240 and seed 20261013.
- Contract/artifact validation: **passed**.
- Unit tests: **2 passed**.
- Fabric deployment dry run: **passed**; four automatable non-preview items selected. The thin PBIR report is source controlled but intentionally manual until its semantic-model binding is materialized.
- Live Fabric authentication/readback: **not attempted because Azure CLI is not installed or not available on PATH in this execution environment**. `preflight.ps1 -RequireFabricAccess` stopped at `Missing 'az'. Install Azure CLI.` No Fabric API request was made, no item IDs or status codes were produced, and no deployment is claimed.
- Azure source deployment: **not attempted for the same Azure CLI blocker**.

Recommended next action: install Azure CLI, run `az login`, then rerun `.\scripts\preflight.ps1 -RequireFabricAccess`. Only after it passes, run `python .\scripts\fabric_deploy.py`; add `--include-preview` only after confirming Ontology and Data Agent availability.
