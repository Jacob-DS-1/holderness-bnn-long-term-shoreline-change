"""Fast validation for the canonical implementation plan."""

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_implementation_plan_structure_and_identifiers():
    plan = json.loads((REPO_ROOT / "implementation-plan.json").read_text())

    assert isinstance(plan, list)
    assert len(plan) == 130
    assert [entry["id"] for entry in plan] == [
        f"P{number:03d}" for number in range(1, 131)
    ]

    required = {"id", "phase", "kind", "item"}
    for entry in plan:
        assert set(entry) == required
        assert all(isinstance(entry[field], str) and entry[field] for field in required)

    p012 = plan[11]["item"]
    assert "reanalysis v3" in p012
    assert "historical/future v1" in p012

    p020 = plan[19]["item"]
    assert "approved retrieval-candidate Design 1" in p020
    assert "14 Landsat scenes" in p020

    p024 = plan[23]["item"]
    assert "uses two of the five" in p024
    assert "reserves three" in p024
