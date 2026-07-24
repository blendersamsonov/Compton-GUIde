"""One canonical convention + unit per physical meaning.

The canonical choices below match what both engines already agree on
internally (see each engine's ``params_to_config``): a Gaussian width is
canonically the RMS of the *intensity*/density profile, a duration is
canonically a time in seconds (even though both engines store the
corresponding ``Config`` field as ``c * duration`` in metres -- see
``units.py``'s light-time context), and a laser amplitude is canonically
its peak value. Nothing here is arbitrary; it was chosen to make
``to_canonical`` a no-op convention-wise for both of this project's real
models, so mismatches show up as loudly as possible if a third model ever
disagrees.
"""

from __future__ import annotations

from . import converters
from .enums import AmplitudeConvention, PhysicalMeaning, TimeConvention, WidthConvention
from .quantities import PhysicalQuantity
from .units import LIGHT_TIME_CONTEXT
from .validation import MeaningMismatchError, validate_quantity

CANONICAL_CONVENTIONS: dict[PhysicalMeaning, object] = {
    PhysicalMeaning.LASER_WIDTH: WidthConvention.SIGMA_INTENSITY_RMS,
    PhysicalMeaning.ELECTRON_BEAM_SIZE: WidthConvention.SIGMA_INTENSITY_RMS,
    PhysicalMeaning.PULSE_DURATION: TimeConvention.SIGMA_INTENSITY_RMS,
    PhysicalMeaning.BUNCH_LENGTH: TimeConvention.SIGMA_INTENSITY_RMS,
    PhysicalMeaning.LASER_AMPLITUDE: AmplitudeConvention.A0_PEAK,
}

CANONICAL_UNIT: dict[PhysicalMeaning, str] = {
    PhysicalMeaning.LASER_WIDTH: "meter",
    PhysicalMeaning.ELECTRON_BEAM_SIZE: "meter",
    PhysicalMeaning.PULSE_DURATION: "second",
    PhysicalMeaning.BUNCH_LENGTH: "second",
    PhysicalMeaning.LASER_AMPLITUDE: "dimensionless",
}

# Meanings whose native storage unit can be a length standing in for a time
# (``sigma_par_L = c * pulse_duration``) -- these need the light-time pint
# context to reach/leave the canonical (time) unit.
_TIME_LIKE = {PhysicalMeaning.PULSE_DURATION, PhysicalMeaning.BUNCH_LENGTH}

_CONVERTER_BY_MEANING = {
    PhysicalMeaning.LASER_WIDTH: converters.convert_width,
    PhysicalMeaning.ELECTRON_BEAM_SIZE: converters.convert_width,
    PhysicalMeaning.PULSE_DURATION: converters.convert_time,
    PhysicalMeaning.BUNCH_LENGTH: converters.convert_time,
    PhysicalMeaning.LASER_AMPLITUDE: converters.convert_amplitude,
}


def _context_for(meaning: PhysicalMeaning) -> str | None:
    return LIGHT_TIME_CONTEXT if meaning in _TIME_LIKE else None


def to_canonical(q: PhysicalQuantity) -> PhysicalQuantity:
    """Convert ``q`` to this project's single canonical convention+unit for
    its meaning, regardless of what convention/unit it started in."""
    validate_quantity(q)
    canonical_convention = CANONICAL_CONVENTIONS[q.meaning]
    canonical_unit = CANONICAL_UNIT[q.meaning]
    convert_fn = _CONVERTER_BY_MEANING[q.meaning]

    q_canonical_unit = q.to_unit(canonical_unit, context=_context_for(q.meaning))
    canonical_value = convert_fn(q_canonical_unit.magnitude, q.convention, canonical_convention)
    return PhysicalQuantity(canonical_value, canonical_unit, q.meaning, canonical_convention)


def from_canonical(q: PhysicalQuantity, target_convention, target_unit: str) -> PhysicalQuantity:
    """Convert a canonical ``q`` to a target convention and unit (typically
    what a specific model's ``ParameterSpec`` asks for)."""
    validate_quantity(q)
    canonical_convention = CANONICAL_CONVENTIONS[q.meaning]
    if q.convention != canonical_convention:
        raise MeaningMismatchError(
            f"from_canonical expects a quantity already in the canonical convention "
            f"{canonical_convention!r} for {q.meaning!r}; got {q.convention!r}. "
            f"Call to_canonical() first."
        )
    convert_fn = _CONVERTER_BY_MEANING[q.meaning]
    target_value = convert_fn(q.magnitude, q.convention, target_convention)
    target_in_canonical_unit = PhysicalQuantity(target_value, q.unit, q.meaning, target_convention)
    return target_in_canonical_unit.to_unit(target_unit, context=_context_for(q.meaning))
