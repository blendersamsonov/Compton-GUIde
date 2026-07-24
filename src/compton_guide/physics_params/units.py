"""Shared pint unit registry.

One registry for the whole package (pint quantities from different
registries can't interoperate), plus a custom ``"light_time"`` context that
lets a length convert to/from a duration via ``length = c * time``. Both
``xigma_i`` and ``kascade`` store pulse/bunch "length" natively as a
position-domain sigma (``sigma_par_L = c * pulse_duration``, see each
engine's ``params_to_config``) rather than as a time, so ``PULSE_DURATION``/
``BUNCH_LENGTH`` quantities need this context to move between the unit a
GUI would naturally show (seconds, picoseconds) and the unit the physics
code actually stores (metres, centimetres).
"""

from __future__ import annotations

import pint

ureg = pint.UnitRegistry()
Quantity = ureg.Quantity

_C = ureg.speed_of_light

LIGHT_TIME_CONTEXT = "light_time"

_ctx = pint.Context(LIGHT_TIME_CONTEXT)
_ctx.add_transformation(
    "[length]", "[time]", lambda ureg_, length: (length / _C).to("second")
)
_ctx.add_transformation(
    "[time]", "[length]", lambda ureg_, time: (time * _C).to("meter")
)
ureg.add_context(_ctx)
