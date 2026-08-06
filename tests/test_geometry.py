"""Unit tests for geometry that do not require external data."""

import numpy as np
import pytest
from shapely.geometry import LineString

from holderness import coastsat_api, config, geometry


@pytest.fixture
def reference_line():
    return LineString([(0, 0), (0, 1000)])


@pytest.fixture
def transects(reference_line):
    return geometry.build_transects(
        reference_line,
        epsg=config.EPSG,
        spacing=config.MASTER_TRANSECT_SPACING_M,
        landward=config.INITIAL_TRANSECT_LANDWARD_M,
        seaward=config.INITIAL_TRANSECT_SEAWARD_M,
        window=config.TRANSECT_NORMAL_WINDOW_M,
    )


def test_master_transects_use_chainage_ids_and_fixed_extents(transects):
    assert len(transects) == 20
    assert transects.iloc[0].transect_id == 'HOL_00000'
    assert transects.iloc[1].transect_id == 'HOL_00050'
    assert transects.iloc[-1].transect_id == 'HOL_00950'
    assert transects.crs.to_epsg() == 27700

    first = np.asarray(transects.iloc[0].geometry.coords)
    assert first[0] == pytest.approx([-300, 0])
    assert first[-1] == pytest.approx([300, 0])


@pytest.mark.parametrize(
    'spacing,expected',
    [(spacing, 1000 // spacing)
     for spacing in config.TRANSECT_SUBSET_SPACINGS_M],
)
def test_chainage_subsets_are_deterministic(transects, spacing, expected):
    subset = geometry.subset_transects(transects, spacing)
    assert len(subset) == expected
    assert (subset.chainage_m % spacing == 0).all()
    assert set(subset.transect_id).issubset(set(transects.transect_id))


def test_excluding_one_transect_does_not_renumber_later_ids(reference_line):
    transects = geometry.build_transects(
        reference_line, epsg=27700, exclude_ranges=[(100, 100)]
    )
    assert 'HOL_00100' not in set(transects.transect_id)
    assert 'HOL_00150' in set(transects.transect_id)


def test_direction_and_crossing_checks(transects):
    seaward_line = LineString([(100, 0), (100, 1000)])
    assert geometry.verify_seaward(transects, seaward_line) == []
    assert geometry.find_crossings(transects) == []


def test_geojson_round_trip_preserves_ids_chainage_and_crs(transects, tmp_path):
    path = tmp_path / 'transects.geojson'
    geometry.write_geojson(transects, path)
    loaded = geometry.read_geojson(path)

    assert list(loaded.transect_id) == list(transects.transect_id)
    assert np.array_equal(loaded.chainage_m, transects.chainage_m)
    assert loaded.crs.to_epsg() == 27700


def test_os_seed_is_explicitly_provisional(reference_line):
    frame = geometry.seed_geodataframe(reference_line, epsg=27700)
    assert frame.iloc[0]['role'] == 'provisional_geometry_seed'
    assert bool(frame.iloc[0]['provisional']) is True


def test_availability_rois_have_fixed_cores_and_500_m_overlap():
    line = LineString([(0, 0), (0, 12_000)])
    rois = geometry.build_rois(
        line,
        epsg=config.EPSG,
        length=config.ROI_LENGTH_M,
        overlap=config.ROI_OVERLAP_M,
        half_width=config.INITIAL_MAX_DIST_REF_M,
        max_area=config.ROI_MAX_AREA_M2,
    )

    assert list(rois.roi_id) == ['HOL_ROI_01', 'HOL_ROI_02', 'HOL_ROI_03']
    assert list(rois.core_start_m) == [0, 5000, 10000]
    assert rois.iloc[0].extract_end_m - rois.iloc[1].extract_start_m == 500
    assert (rois.area_m2 <= config.ROI_MAX_AREA_M2).all()
    assert rois.provisional.all()


def test_coastsat_adapters_do_not_change_authoritative_geometry(transects,
                                                                 reference_line):
    reference = coastsat_api.reference_line_to_array(
        reference_line, spacing=config.COASTSAT_REFERENCE_STEP_M
    )
    coast_sat_transects = coastsat_api.transects_to_dict(transects)

    assert reference.shape[1] == 2
    assert reference[0] == pytest.approx([0, 0])
    assert reference[-1] == pytest.approx([0, 1000])
    assert list(coast_sat_transects)[:2] == ['HOL_00000', 'HOL_00050']
    assert coast_sat_transects['HOL_00000'].shape == (2, 2)
