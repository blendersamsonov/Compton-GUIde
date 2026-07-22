"""sys.path wiring so ``compton_gui`` can import ``dfe5_compton_mc`` and
``xigma_i`` without either being pip-installed.

Both physics packages currently live in locations that aren't stable
package-manager paths: ``dfe5_compton_mc`` is a loose script directory
(``MC-Kost/``, sibling of this project) with no packaging at all, and
``xigma_i`` lives inside a git worktree checkout whose path will change
once that worktree is merged/removed. A hardcoded ``pyproject.toml``
path-dependency on either would break, so this is a runtime ``sys.path``
bootstrap instead, with both locations overridable via environment
variables for anyone whose checkout layout differs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
# .../compton-gui/src/compton_gui -> .../compton-gui -> .../XIGMA (sibling dir)
_XIGMA_ROOT = _THIS_DIR.parents[2]

DEFAULT_DFE5_PATH = _XIGMA_ROOT / "MC-Kost"
# Default xigma_i src location as of this writing; override via
# COMPTON_GUI_XIGMA_SRC once the worktree this currently lives in is
# merged/removed.
DEFAULT_XIGMA_SRC = (
    _XIGMA_ROOT / "git-repo-claude" / ".claude" / "worktrees" / "integration" / "src"
)


def setup_paths() -> None:
    """Insert the dfe5 and xigma_i source directories into ``sys.path`` if
    they aren't already importable. Safe to call more than once."""
    dfe5_path = Path(os.environ.get("COMPTON_GUI_DFE5_PATH", DEFAULT_DFE5_PATH))
    xigma_src = Path(os.environ.get("COMPTON_GUI_XIGMA_SRC", DEFAULT_XIGMA_SRC))

    for p in (dfe5_path, xigma_src):
        p_str = str(p)
        if p.is_dir() and p_str not in sys.path:
            sys.path.insert(0, p_str)
