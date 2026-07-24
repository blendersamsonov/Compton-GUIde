"""Explicit numeric transformations between conventions of the same
meaning. Every function here is a pure scalar-factor conversion -- unit
independent, valid whether the underlying quantity is in metres or
centimetres -- so ``canonical.py`` applies these to the magnitude only,
separately from any unit conversion.
"""

from __future__ import annotations

import numpy as np

from .enums import AmplitudeConvention, TimeConvention, WidthConvention
from .validation import UnknownConversionError

_FWHM_OVER_SIGMA = 2.0 * np.sqrt(2.0 * np.log(2.0))


# ---------------------------------------------------------------------------
# Gaussian width/time algebra
# ---------------------------------------------------------------------------
def fwhm_to_sigma_intensity(fwhm: float) -> float:
    return fwhm / _FWHM_OVER_SIGMA


def sigma_intensity_to_fwhm(sigma: float) -> float:
    return sigma * _FWHM_OVER_SIGMA


def sigma_field_to_sigma_intensity(sigma_field: float) -> float:
    return sigma_field / np.sqrt(2.0)


def sigma_intensity_to_sigma_field(sigma_intensity: float) -> float:
    return sigma_intensity * np.sqrt(2.0)


def w0_to_sigma_intensity(w0: float) -> float:
    return w0 / 2.0


def sigma_intensity_to_w0(sigma_intensity: float) -> float:
    return sigma_intensity * 2.0


# ---------------------------------------------------------------------------
# Amplitude algebra (linear polarisation: <a^2> = a0_peak^2 / 2)
# ---------------------------------------------------------------------------
def a0_peak_to_a0_rms(a0_peak: float) -> float:
    return a0_peak / np.sqrt(2.0)


def a0_rms_to_a0_peak(a0_rms: float) -> float:
    return a0_rms * np.sqrt(2.0)


# ---------------------------------------------------------------------------
# Unified per-family engines: convert(value, from_convention, to_convention)
# ---------------------------------------------------------------------------
_WIDTH_TO_CANONICAL = {
    WidthConvention.SIGMA_INTENSITY_RMS: lambda v: v,
    WidthConvention.SIGMA_FIELD_RMS: sigma_field_to_sigma_intensity,
    WidthConvention.FWHM_INTENSITY: fwhm_to_sigma_intensity,
    WidthConvention.W0_1E2: w0_to_sigma_intensity,
}
_WIDTH_FROM_CANONICAL = {
    WidthConvention.SIGMA_INTENSITY_RMS: lambda v: v,
    WidthConvention.SIGMA_FIELD_RMS: sigma_intensity_to_sigma_field,
    WidthConvention.FWHM_INTENSITY: sigma_intensity_to_fwhm,
    WidthConvention.W0_1E2: sigma_intensity_to_w0,
}

_TIME_TO_CANONICAL = {
    TimeConvention.SIGMA_INTENSITY_RMS: lambda v: v,
    TimeConvention.SIGMA_FIELD_RMS: sigma_field_to_sigma_intensity,
    TimeConvention.FWHM_INTENSITY: fwhm_to_sigma_intensity,
}
_TIME_FROM_CANONICAL = {
    TimeConvention.SIGMA_INTENSITY_RMS: lambda v: v,
    TimeConvention.SIGMA_FIELD_RMS: sigma_intensity_to_sigma_field,
    TimeConvention.FWHM_INTENSITY: sigma_intensity_to_fwhm,
}

_AMPLITUDE_TO_CANONICAL = {
    AmplitudeConvention.A0_PEAK: lambda v: v,
    AmplitudeConvention.A0_RMS: a0_rms_to_a0_peak,
}
_AMPLITUDE_FROM_CANONICAL = {
    AmplitudeConvention.A0_PEAK: lambda v: v,
    AmplitudeConvention.A0_RMS: a0_peak_to_a0_rms,
}


def _convert(value: float, from_conv, to_conv, to_canonical: dict, from_canonical: dict, family: str) -> float:
    try:
        to_c = to_canonical[from_conv]
    except KeyError as exc:
        raise UnknownConversionError(f"no {family} conversion registered for {from_conv!r}") from exc
    try:
        from_c = from_canonical[to_conv]
    except KeyError as exc:
        raise UnknownConversionError(f"no {family} conversion registered for {to_conv!r}") from exc
    return from_c(to_c(value))


def convert_width(value: float, from_conv: WidthConvention, to_conv: WidthConvention) -> float:
    return _convert(value, from_conv, to_conv, _WIDTH_TO_CANONICAL, _WIDTH_FROM_CANONICAL, "width")


def convert_time(value: float, from_conv: TimeConvention, to_conv: TimeConvention) -> float:
    return _convert(value, from_conv, to_conv, _TIME_TO_CANONICAL, _TIME_FROM_CANONICAL, "time")


def convert_amplitude(value: float, from_conv: AmplitudeConvention, to_conv: AmplitudeConvention) -> float:
    return _convert(value, from_conv, to_conv, _AMPLITUDE_TO_CANONICAL, _AMPLITUDE_FROM_CANONICAL, "amplitude")
