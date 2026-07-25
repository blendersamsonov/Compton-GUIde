"""ModelSpec for kascade (formerly dfe5_compton_mc), at the boundary its own
adapter already uses: ``kascade.Config``'s fields.

Verified field-by-field against ``MC-Kost/kascade.py``:

* ``laser_density``'s docstring/body Gaussian-izes both the transverse
  extent via ``sigma0_l`` (``sp2 = sigma0_l**2 * (1 + (u/R_sf)**2)``, an
  RMS width of the photon-density profile) and the longitudinal one via
  ``sigma_par_L`` (``exp(-(u - c t)**2 / (2 sigma_par_L**2))``) -- both are
  the RMS of a density profile, matching xigma-i's ``sigma_lr0``/
  ``sigma_lz`` convention exactly (see ``schemas/xigma.py``).
* ``Config``'s own field comments confirm the length<->duration relation
  directly: ``sigma_par_e: ... # m (rms bunch length, = c*duration)`` and
  ``sigma_par_L: ... # m (rms pulse length, = c*duration)``.

This is the same convention as xigma-i's ``Config`` in every field that
exists in both -- expected, since both adapters' ``params_to_config`` were
written (independently, by hand) with identical arithmetic; see this
package's top-level docstring and ``scripts/physics_params_demo.py`` for
why that agreement is exactly what this module exists to make explicit and
machine-checkable instead of a coincidence nobody would notice breaking.
"""

from __future__ import annotations

from compton_suite import AmplitudeConvention, ParameterSpec, PhysicalMeaning, TimeConvention, WidthConvention

KASCADE_SPEC: dict[str, ParameterSpec] = {
    "sigma0_x": ParameterSpec(
        name="sigma0_x",
        meaning=PhysicalMeaning.ELECTRON_BEAM_SIZE,
        convention=WidthConvention.SIGMA_INTENSITY_RMS,
        unit="meter",
        description="Horizontal electron-bunch RMS size at the waist (Config.sigma0_x).",
    ),
    "sigma0_y": ParameterSpec(
        name="sigma0_y",
        meaning=PhysicalMeaning.ELECTRON_BEAM_SIZE,
        convention=WidthConvention.SIGMA_INTENSITY_RMS,
        unit="meter",
        description="Vertical electron-bunch RMS size at the waist (Config.sigma0_y).",
    ),
    "sigma_par_e": ParameterSpec(
        name="sigma_par_e",
        meaning=PhysicalMeaning.BUNCH_LENGTH,
        convention=TimeConvention.SIGMA_INTENSITY_RMS,
        unit="meter",
        description="Electron-bunch RMS length, = c * RMS duration (Config.sigma_par_e).",
    ),
    "sigma0_l": ParameterSpec(
        name="sigma0_l",
        meaning=PhysicalMeaning.LASER_WIDTH,
        convention=WidthConvention.SIGMA_INTENSITY_RMS,
        unit="meter",
        description="Laser transverse RMS size of the photon-density profile (Config.sigma0_l).",
    ),
    "sigma_par_L": ParameterSpec(
        name="sigma_par_L",
        meaning=PhysicalMeaning.PULSE_DURATION,
        convention=TimeConvention.SIGMA_INTENSITY_RMS,
        unit="meter",
        description="Laser pulse RMS length, = c * RMS duration (Config.sigma_par_L).",
    ),
}
"""Config-level input parameters with a width/duration convention."""

KASCADE_DIAGNOSTIC_SPEC: dict[str, ParameterSpec] = {
    "a0": ParameterSpec(
        name="a0",
        meaning=PhysicalMeaning.LASER_AMPLITUDE,
        convention=AmplitudeConvention.A0_PEAK,
        unit="dimensionless",
        description=(
            "sqrt(laser_a0sq(...)) at the pulse centre (x=y=z=t=0), where "
            "laser_density peaks -- not a direct GUI input (derived from "
            "pulse energy N_L + geometry), so not part of KASCADE_SPEC."
        ),
    ),
}
"""Read-only/derived quantities with a documented convention -- see this
module's docstring and ``schemas/xigma.py``'s analogous ``XIGMA_DIAGNOSTIC_SPEC``."""
