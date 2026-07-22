"""Model discovery/registration -- deliberately free of any tkinter/matplotlib
import so it can be exercised headlessly (e.g. by scripts/headless_test.py)
without a display or those packages installed.
"""

from __future__ import annotations

from compton_gui.model_api import UnavailableAdapter, register, registered_models


def discover_models() -> dict:
    """Populate the model registry. Never raises -- a model that can't be
    imported/used (e.g. xigma-i without a working cupy/CUDA install) is
    registered as an UnavailableAdapter so it still shows up, disabled, in
    the GUI's Model menu instead of silently vanishing. Returns the
    registry snapshot (see ``model_api.registered_models``)."""
    from compton_gui import bootstrap
    bootstrap.setup_paths()

    from compton_gui.adapters.dfe5_adapter import Dfe5Adapter
    register("dfe5", Dfe5Adapter())

    try:
        from xigma_i import gui_adapter as _xigma_gui
        register("xigma-i", _xigma_gui.XigmaAdapter())
    except Exception as e:
        register("xigma-i", UnavailableAdapter(
            _name="xigma-i", _reason=str(e), _display_name="XIGMA-I (experimental)"))

    return registered_models()
