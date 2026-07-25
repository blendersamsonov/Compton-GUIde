"""CODATA-style physical constants used by the GUI's local formula helpers
(peak_a0, sigma_e, the spread-estimate box, ...).

Re-exported from ``compton_suite.constants`` (the shared, pint-derived
source of truth also used by ``xigma_i``/``kascade``) rather than defined
here -- this module used to duplicate its own literal copy, on the same
precedent ``xigma_i.gui_adapter`` set of hand-duplicating a couple of
constants to avoid a cross-repo import; that precedent is gone now that
``compton_suite`` exists specifically to be cross-imported instead of
copied. Calls ``bootstrap.setup_paths()`` itself since ``app.py`` imports
this module before ``models.discover_models()`` runs.
"""

from . import bootstrap

bootstrap.setup_paths()

from compton_suite import constants as _suite_constants  # noqa: E402

C_LIGHT = _suite_constants.C_LIGHT        # [m/s]
E_CHARGE = _suite_constants.E_CHARGE      # [C]
HBAR = _suite_constants.HBAR              # [J*s]
EPS0 = _suite_constants.EPS0              # [F/m]
MEC2_EV = _suite_constants.MEC2_EV        # electron rest energy [eV]
MEC2_J = MEC2_EV * E_CHARGE               # electron rest energy [J]
