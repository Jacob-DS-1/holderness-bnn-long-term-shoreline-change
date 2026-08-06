"""Checks for the repository's licensing and data-release records."""

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "data-licence-manifest.json"


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text())


def test_project_licence_scope_matches_current_repository():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    licensing = (REPO_ROOT / "LICENSING.md").read_text()

    assert 'license = "GPL-3.0-only"' in pyproject
    assert "holderness/" in licensing
    assert "scripts/" in licensing
    assert "third_party/coastsat" not in licensing
    assert "workflow_v3" not in licensing
    assert "config/external" not in licensing


def test_data_manifest_has_all_planned_provider_groups():
    manifest = load_manifest()
    dataset_ids = {dataset["id"] for dataset in manifest["datasets"]}

    expected = {
        "os_openmap_local_tidal_boundary",
        "usgs_landsat_collection_2_level_1",
        "copernicus_sentinel_2_harmonized",
        "aviso_fes2022",
        "copernicus_cds_gtsm_v3",
        "copernicus_marine_nws_wave_reanalysis",
        "environment_agency_time_stamped_lidar",
        "east_riding_monitoring_surveys",
        "cefas_wavenet_hornsea",
        "bodc_regional_tide_gauges",
        "bgs_open_covariates",
    }
    assert expected <= dataset_ids


def test_every_dataset_has_a_complete_release_record_shape():
    manifest = load_manifest()
    required = {
        "id",
        "name",
        "role",
        "provider",
        "source",
        "coverage",
        "licensing",
        "attribution",
        "transformation_history",
        "publication",
    }

    ids = []
    for dataset in manifest["datasets"]:
        assert set(dataset) == required
        ids.append(dataset["id"])
        source_url = dataset["source"]["url"]
        licence_url = dataset["licensing"]["url"]
        assert source_url is None or source_url.startswith("https://")
        assert licence_url is None or licence_url.startswith("https://")
        assert dataset["attribution"]
        assert isinstance(dataset["transformation_history"], list)

        publication = dataset["publication"]
        assert isinstance(publication["release_ready"], bool)
        assert isinstance(publication["blockers"], list)
        if publication["release_ready"]:
            assert publication["blockers"] == []

    assert len(ids) == len(set(ids))


def test_sensitive_or_unresolved_sources_are_not_release_ready():
    datasets = {dataset["id"]: dataset for dataset in load_manifest()["datasets"]}
    restricted_or_unresolved = {
        "aviso_fes2022",
        "east_riding_monitoring_surveys",
        "cefas_wavenet_hornsea",
        "bodc_regional_tide_gauges",
        "bgs_open_covariates",
    }

    for dataset_id in restricted_or_unresolved:
        assert datasets[dataset_id]["publication"]["release_ready"] is False
        assert datasets[dataset_id]["publication"]["blockers"]


def test_os_seed_role_and_unavailable_acquisition_date_are_explicit():
    datasets = {dataset["id"]: dataset for dataset in load_manifest()["datasets"]}
    os_seed = datasets["os_openmap_local_tidal_boundary"]

    assert "not a dated shoreline observation" in os_seed["role"]
    assert os_seed["source"]["source_version"] is None
    assert os_seed["source"]["product_snapshot_or_supply_date"] is None
    assert os_seed["source"]["feature_acquisition_or_evidence_date"] is None
    assert "does not supply" in os_seed["source"]["date_note"]
    assert os_seed["source"]["download_date"] is None
    assert os_seed["source"]["checksum"].startswith("sha256:")
    assert len(os_seed["source"]["checksum"]) == 71
    assert os_seed["publication"]["release_ready"] is False
    assert "method_use_allowed" in os_seed["publication"]["derived_output_status"]
    assert "[year]" in os_seed["attribution"]
    assert any(
        "Do not cast the final 50 m master transects" in step
        for step in os_seed["transformation_history"]
    )


def test_output_licence_is_conditional_on_source_clearance():
    policy = load_manifest()["repository_policy"]

    assert policy["default_derived_data_licence"] == "CC-BY-4.0"
    assert policy["raw_data_committed"] is False
    assert "unresolved blockers" in policy["release_rule"]
