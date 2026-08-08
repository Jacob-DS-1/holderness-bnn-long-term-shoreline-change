"""Fast checks for FES2022 validation helpers."""

import numpy as np
import pytest

from holderness import fes


def test_component_height_combines_centimetres_as_metres():
    assert fes.component_height_metres(-232.5, 2.5) == pytest.approx(-2.3)


@pytest.mark.parametrize('invalid_value', [None, 'bad', np.nan, np.inf, -np.inf])
def test_component_height_rejects_non_finite_values(invalid_value):
    with pytest.raises(ValueError, match='finite numbers'):
        fes.component_height_metres(invalid_value, 0.0)


@pytest.mark.parametrize(
    ('flag', 'description'),
    [
        (4, 'interpolated from 4 points'),
        (1, 'interpolated from 1 point'),
        (0, 'undefined'),
        (-3, 'extrapolated from 3 points'),
    ],
)
def test_quality_flag_description(flag, description):
    assert fes.quality_flag_description(flag) == description


def test_require_interpolated_flag_accepts_positive_values():
    assert fes.require_interpolated_flag(4, 'ocean') == 4


@pytest.mark.parametrize(
    ('flag', 'message'),
    [(0, 'undefined'), (-2, 'extrapolated from 2 points')],
)
def test_require_interpolated_flag_rejects_invalid_values(flag, message):
    with pytest.raises(ValueError, match=message):
        fes.require_interpolated_flag(flag, 'ocean')
