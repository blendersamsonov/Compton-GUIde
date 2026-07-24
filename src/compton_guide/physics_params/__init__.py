"""Parameter semantics & unit normalisation layer, per ``Conventions-and-units.md``.

Solves two independent problems for parameters shared between this GUI and
its pluggable physics engines (xigma-i, kascade):

1. **Units** -- handled by ``pint`` (see ``units.py``).
2. **Semantics/convention** -- is a "width" the RMS of the intensity
   profile, the FWHM, or the 1/e^2 radius? Is a "duration" a sigma or a
   FWHM? Is an amplitude peak or RMS? Handled by this module: every value
   is a ``PhysicalQuantity`` (value + unit + meaning + convention), never a
   bare float, converted through one project-wide canonical representation
   per meaning (``canonical.py``) and out to whatever convention/unit a
   specific model declares in its ``ModelSpec`` (``schemas/``).

Typical use (see ``schemas/xigma.py`` and ``schemas/kascade.py`` for the
concrete specs, and ``scripts/physics_params_demo.py`` for a full example):

    from compton_guide.physics_params import (
        PhysicalQuantity, PhysicalMeaning, WidthConvention, adapt_to_model,
    )
    from compton_guide.physics_params.schemas.xigma import XIGMA_SPEC

    laser_width = PhysicalQuantity(
        magnitude=5.0, unit="micrometer",
        meaning=PhysicalMeaning.LASER_WIDTH,
        convention=WidthConvention.FWHM_INTENSITY,
    )
    adapted = adapt_to_model({"sigma0_l": laser_width, ...}, XIGMA_SPEC)
    # adapted["sigma0_l"] is now in XIGMA_SPEC's own convention/unit
"""

from .adapter import adapt_to_model, params_to_floats
from .canonical import CANONICAL_CONVENTIONS, CANONICAL_UNIT, from_canonical, to_canonical
from .enums import AmplitudeConvention, PhysicalMeaning, TimeConvention, WidthConvention
from .quantities import PhysicalQuantity
from .schema import ModelSpec, ParameterSpec
from .validation import (
    MeaningMismatchError,
    MissingConventionError,
    PhysicsParamsError,
    UnitMismatchError,
    UnknownConversionError,
    validate_against_spec,
    validate_quantity,
)

__all__ = [
    "PhysicalQuantity",
    "PhysicalMeaning",
    "WidthConvention",
    "TimeConvention",
    "AmplitudeConvention",
    "ParameterSpec",
    "ModelSpec",
    "CANONICAL_CONVENTIONS",
    "CANONICAL_UNIT",
    "to_canonical",
    "from_canonical",
    "adapt_to_model",
    "params_to_floats",
    "validate_quantity",
    "validate_against_spec",
    "PhysicsParamsError",
    "MissingConventionError",
    "UnknownConversionError",
    "UnitMismatchError",
    "MeaningMismatchError",
]
