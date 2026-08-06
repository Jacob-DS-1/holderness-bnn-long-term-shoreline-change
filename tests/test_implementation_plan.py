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
