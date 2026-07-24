"""The value + unit + meaning + convention wrapper.

Every number that crosses the GUI <-> model boundary should travel as a
``PhysicalQuantity``, never as a bare float -- a bare float has silently
dropped the information (RMS or FWHM? metres or a duration?) that this
whole package exists to keep attached to the number.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .enums import PhysicalMeaning
from .units import Quantity, ureg


@dataclass(frozen=True)
class PhysicalQuantity:
    magnitude: float
    unit: str
    meaning: PhysicalMeaning
    convention: Enum

    @property
    def quantity(self) -> Quantity:
        return ureg.Quantity(self.magnitude, self.unit)

    def to_unit(self, unit: str, *, context: str | None = None) -> "PhysicalQuantity":
        """Pure unit conversion (metres <-> centimetres, ps <-> s, ...).
        Never changes ``convention`` -- use ``converters``/``canonical`` for
        that. ``context`` is a pint context name (see ``units.py``'s
        ``LIGHT_TIME_CONTEXT``) for conversions pint can't do unaided, such
        as length <-> time via c."""
        q = self.quantity
        converted = q.to(unit, context) if context else q.to(unit)
        return PhysicalQuantity(float(converted.magnitude), unit, self.meaning, self.convention)
