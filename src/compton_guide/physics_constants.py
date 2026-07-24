"""CODATA-style physical constants used by the GUI's local formula helpers
(peak_a0, sigma_e, the spread-estimate box, ...).

Duplicated here rather than imported from ``kascade`` so this project
depends on that engine only through ``adapters/kascade_adapter.py`` --
mirrors the same precedent already set by ``xigma_i.gui_adapter``, which
duplicates the two constants it needs (MEC2_EV, HBAR) instead of
cross-importing them from kascade.
"""

C_LIGHT = 2.99792458e8        # [m/s]
E_CHARGE = 1.602176634e-19    # [C]
HBAR = 1.054571817e-34        # [J*s]
EPS0 = 8.8541878128e-12       # [F/m]
MEC2_EV = 510_998.95000       # electron rest energy [eV]
MEC2_J = MEC2_EV * E_CHARGE   # electron rest energy [J]
