#!/usr/bin/env python3
"""Exercise compton_guide.physics_params end to end.

Takes one set of laser/electron parameters expressed the way a GUI user
would naturally type them (FWHM in micrometres, a duration in
picoseconds, ...), pushes each through the canonical layer, and adapts it
to both XIGMA_SPEC and KASCADE_SPEC. Prints the result and asserts the two
models land on the same numbers -- expected, since both engines' hand-written
params_to_config already agree on convention (see schemas/kascade.py's
docstring); this is the machine-checked version of that fact.

No cupy/GPU/tkinter needed -- pure physics_params + pint.

    python3 scripts/physics_params_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from compton_guide.physics_params import (  # noqa: E402
    PhysicalMeaning,
    PhysicalQuantity,
    TimeConvention,
    WidthConvention,
    adapt_to_model,
    params_to_floats,
)
from compton_guide.physics_params.schemas.kascade import KASCADE_SPEC  # noqa: E402
from compton_guide.physics_params.schemas.xigma import XIGMA_SPEC  # noqa: E402

# GUI-style raw input: a laser waist given as a FWHM in micrometres, and a
# pulse duration given as a sigma in picoseconds -- deliberately two
# different conventions/units to show the conversion actually does work.
raw_inputs = {
    "sigma0_x": PhysicalQuantity(8.0e-6, "meter", PhysicalMeaning.ELECTRON_BEAM_SIZE, WidthConvention.SIGMA_INTENSITY_RMS),
    "sigma0_y": PhysicalQuantity(6.0e-6, "meter", PhysicalMeaning.ELECTRON_BEAM_SIZE, WidthConvention.SIGMA_INTENSITY_RMS),
    "sigma_par_e": PhysicalQuantity(50.0, "picosecond", PhysicalMeaning.BUNCH_LENGTH, TimeConvention.SIGMA_INTENSITY_RMS),
    "sigma0_l": PhysicalQuantity(12.0, "micrometer", PhysicalMeaning.LASER_WIDTH, WidthConvention.FWHM_INTENSITY),
    "sigma_par_L": PhysicalQuantity(2.0, "picosecond", PhysicalMeaning.PULSE_DURATION, TimeConvention.SIGMA_INTENSITY_RMS),
}

xigma_out = params_to_floats(adapt_to_model(raw_inputs, XIGMA_SPEC))
kascade_out = params_to_floats(adapt_to_model(raw_inputs, KASCADE_SPEC))

print(f"{'key':<14}{'xigma-i [m]':>16}{'kascade [m]':>16}")
for key in XIGMA_SPEC:
    print(f"{key:<14}{xigma_out[key]:>16.6e}{kascade_out[key]:>16.6e}")

for key in XIGMA_SPEC:
    assert abs(xigma_out[key] - kascade_out[key]) <= 1e-15 * abs(xigma_out[key]), (
        f"{key}: xigma-i and kascade specs disagree ({xigma_out[key]!r} vs {kascade_out[key]!r}) "
        "-- they are supposed to share a convention, see schemas/kascade.py's docstring"
    )

# sigma0_l came in as a FWHM; confirm the module actually converted it
# (sigma = FWHM / 2.35...), not just passed the number through.
from compton_guide.physics_params.converters import fwhm_to_sigma_intensity  # noqa: E402

expected_sigma0_l = fwhm_to_sigma_intensity(12.0e-6)
assert abs(xigma_out["sigma0_l"] - expected_sigma0_l) < 1e-12, "FWHM->sigma conversion did not apply"

# sigma_par_L/sigma_par_e came in as durations (ps); confirm the light-time
# context turned them into c*duration lengths.
from compton_guide.physics_params.units import ureg  # noqa: E402

c = ureg.Quantity(1.0, "speed_of_light").to("meter/second").magnitude
expected_sigma_par_L = 2.0e-12 * c
assert abs(xigma_out["sigma_par_L"] - expected_sigma_par_L) < 1e-12 * expected_sigma_par_L, (
    "duration->length (c*t) conversion did not apply"
)

print("\nOK: xigma-i and kascade specs agree; FWHM->sigma and duration->length "
      "conversions verified.")
