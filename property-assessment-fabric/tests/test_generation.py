import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_data import build  # noqa: E402


def test_generation_is_deterministic():
    first = build(24, 42)
    second = build(24, 42)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_expected_counts_and_keys():
    data = build(48, 7)
    assert len(data["parcels"]) == 48
    assert len(data["assessments"]) == 96
    assert len(data["sales"]) == 16
    assert len(data["property_profiles"]) == 48
    assert len(data["appeals"]) == 60
    parcel_ids = {row["parcelId"] for row in data["parcels"]}
    assert {row["parcelId"] for row in data["appeals"]} <= parcel_ids
    assert all(row["synthetic"] for row in data["property_profiles"])

