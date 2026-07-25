"""Thin re-export of ``compton_suite``'s parameter-semantics/unit
normalisation framework, per ``Conventions-and-units.md``.

The framework itself (``PhysicalQuantity``, the enums, canonical
conversion, ``ParameterSpec``/``ModelSpec``, ``adapt_to_model``) lives in
the sibling ``compton_suite`` repo now, found via
``compton_guide.bootstrap.setup_paths()`` -- **not defined here**, so
``compton_guide.physics_params.PhysicalQuantity`` is the literal same
class as e.g. ``xigma_i.params.PhysicalQuantity``, not an independently-
defined look-alike (an earlier version of this move gave each repo its own
copy, which broke exactly that; see git history if curious). This module
exists so existing `from compton_guide.physics_params import ...` call
sites don't need to change, and so `compton_guide.physics_params.
schemas.kascade`'s `KASCADE_SPEC` has somewhere local to import the
framework types from.

**xigma-i's schema moved out of this repo.** `schemas/xigma.py`'s
`XIGMA_SPEC`/`XIGMA_DIAGNOSTIC_SPEC` now live in that model's own repo as
`xigma_i.params` (see that repo's `CLAUDE.md`, "Parameter semantics &
units") -- the model declares its own parameter contract instead of the
GUI declaring it on the model's behalf. `kascade` hasn't had the same
move yet, so `schemas/kascade.py`'s `KASCADE_SPEC` still lives here.

Typical use (see `schemas/kascade.py` for a concrete local spec,
`xigma_i.params` for xigma-i's, and `scripts/physics_params_demo.py` for a
full cross-repo example):

    from compton_guide import bootstrap
    bootstrap.setup_paths()

    from compton_guide.physics_params import (
        PhysicalQuantity, PhysicalMeaning, WidthConvention, adapt_to_model,
    )
    from xigma_i.params import XIGMA_SPEC

    laser_width = PhysicalQuantity(
        magnitude=5.0, unit="micrometer",
        meaning=PhysicalMeaning.LASER_WIDTH,
        convention=WidthConvention.FWHM_INTENSITY,
    )
    adapted = adapt_to_model({"sigma0_l": laser_width, ...}, XIGMA_SPEC)
    # adapted["sigma0_l"] is now in XIGMA_SPEC's own convention/unit
"""

from .. import bootstrap

bootstrap.setup_paths()

from compton_suite import (  # noqa: E402
    CANONICAL_CONVENTIONS,
    CANONICAL_UNIT,
    AmplitudeConvention,
    MeaningMismatchError,
    MissingConventionError,
    ModelSpec,
    ParameterSpec,
    PhysicalMeaning,
    PhysicalQuantity,
    PhysicsParamsError,
    TimeConvention,
    UnitMismatchError,
    UnknownConversionError,
    WidthConvention,
    adapt_to_model,
    from_canonical,
    params_to_floats,
    to_canonical,
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
