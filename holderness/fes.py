"""Small validation helpers for FES2022 tide predictions."""

import math


def component_height_metres(short_period_cm, long_period_cm):
    """Combine finite short- and long-period PyFES values in metres."""
    try:
        short_period_cm = float(short_period_cm)
        long_period_cm = float(long_period_cm)
    except (TypeError, ValueError) as error:
        raise ValueError('FES component values must be finite numbers') from error

    if not all(map(math.isfinite, (short_period_cm, long_period_cm))):
        raise ValueError('FES component values must be finite numbers')

    return (short_period_cm + long_period_cm) / 100.0


def quality_flag_description(flag):
    """Describe the PyFES interpolation flag for one prediction."""
    try:
        flag = int(flag)
    except (TypeError, ValueError) as error:
        raise ValueError('FES quality flag must be an integer') from error

    if flag == 0:
        return 'undefined'
    if flag < 0:
        return f'extrapolated from {-flag} points'
    noun = 'point' if flag == 1 else 'points'
    return f'interpolated from {flag} {noun}'


def require_interpolated_flag(flag, component):
    """Require a defined, interpolated rather than extrapolated prediction."""
    description = quality_flag_description(flag)
    flag = int(flag)
    if flag <= 0:
        raise ValueError(
            f'{component} FES prediction is {description}; '
            'choose a valid offshore point'
        )
    return flag
