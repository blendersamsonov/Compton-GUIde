"""Canonical params -> a specific model's own convention/units.

This is the last step before a value is allowed to reach model code: once
``adapt_to_model`` has run, every value is a plain float already in the
unit and convention the target ``Config``/``set_*_parameters`` call
expects, so model code itself performs no conversion (Conventions-and-units.md
section 8B).
"""

from __future__ import annotations

from .canonical import from_canonical, to_canonical
from .quantities import PhysicalQuantity
from .schema import ModelSpec
from .validation import validate_against_spec


def adapt_to_model(canonical_params: dict[str, PhysicalQuantity], model_spec: ModelSpec) -> dict[str, PhysicalQuantity]:
    """``canonical_params`` may be in any convention/unit as long as the
    meaning matches; each is round-tripped through the canonical
    representation and back out in ``model_spec``'s convention/unit."""
    validate_against_spec(canonical_params, model_spec)
    result: dict[str, PhysicalQuantity] = {}
    for key, pspec in model_spec.items():
        q_canonical = to_canonical(canonical_params[key])
        result[key] = from_canonical(q_canonical, pspec.convention, pspec.unit)
    return result


def params_to_floats(adapted: dict[str, PhysicalQuantity]) -> dict[str, float]:
    """Strip the semantic wrapper for the final call into model code, which
    wants plain floats in the unit it asked for (``adapt_to_model`` already
    guaranteed that unit)."""
    return {key: q.magnitude for key, q in adapted.items()}
