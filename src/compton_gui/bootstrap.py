"""sys.path wiring so ``compton_gui`` can import ``dfe5_compton_mc`` and
``xigma_i`` without either being pip-installed.

Both physics packages currently live in locations that aren't stable
package-manager paths: ``dfe5_compton_mc`` is a loose script directory
(``MC-Kost/``, sibling of this project) with no packaging at all, and
``xigma_i`` lives in a sibling checkout whose directory name and exact
path are not stable across machines -- e.g. it may be a plain repo clone
on one machine and a git-worktree checkout on another, under whatever
name that machine's checkout happens to have (this has already changed
once, when ``xigma_i``'s GUI adapter moved out of a git worktree and into
that repo's ``main`` branch). A hardcoded ``pyproject.toml``
path-dependency, or even a hardcoded sibling directory *name*, would
break on the next machine or the next reorganization -- so this is a
runtime ``sys.path`` bootstrap that autodiscovers both locations by
content (looking for a marker file inside each candidate sibling
directory) rather than by name, with both still overridable via
environment variables for anyone whose checkout layout doesn't match
autodiscovery at all (e.g. it lives outside ``_XIGMA_ROOT`` entirely).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
# .../compton-gui/src/compton_gui -> .../compton-gui -> .../XIGMA (sibling dir)
_XIGMA_ROOT = _THIS_DIR.parents[2]

# Marker files used to recognize each physics package among _XIGMA_ROOT's
# sibling directories, relative to the sibling directory itself.
_DFE5_MARKER = "dfe5_compton_mc.py"
_XIGMA_MARKER = "src/xigma_i/gui_adapter.py"


def _find_siblings(root: Path, marker: str) -> list[Path]:
    """Sibling directories of this project (children of ``root``) that
    contain ``marker``, sorted by name for a deterministic pick among
    ties."""
    if not root.is_dir():
        return []
    return sorted(
        entry for entry in root.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
        and (entry / marker).exists()
    )


def _discover(root: Path, marker: str, env_var: str) -> Path | None:
    """A candidate sibling directory containing ``marker``, or ``None``.
    Warns (but does not fail) if more than one match is found -- pin the
    right one via ``env_var`` in that case."""
    matches = _find_siblings(root, marker)
    if not matches:
        return None
    if len(matches) > 1:
        print(
            f"compton_gui.bootstrap: multiple candidates found under {root} "
            f"(all contain {marker!r}): {[str(m) for m in matches]}; using "
            f"{matches[0]} -- set {env_var} to pin a specific one.",
            file=sys.stderr,
        )
    return matches[0]


def setup_paths() -> None:
    """Insert the dfe5 and xigma_i source directories into ``sys.path`` if
    they aren't already importable. Safe to call more than once.

    Resolution order for each, highest priority first:
      1. The relevant ``COMPTON_GUI_*`` environment variable, if set --
         used verbatim, no autodiscovery, for checkouts autodiscovery
         can't find (e.g. outside ``_XIGMA_ROOT``).
      2. Autodiscovery: the (alphabetically first, if several) sibling of
         this project containing the package's marker file.
    """
    dfe5_override = os.environ.get("COMPTON_GUI_DFE5_PATH")
    dfe5_path = (
        Path(dfe5_override) if dfe5_override
        else _discover(_XIGMA_ROOT, _DFE5_MARKER, "COMPTON_GUI_DFE5_PATH")
    )

    xigma_override = os.environ.get("COMPTON_GUI_XIGMA_SRC")
    xigma_src = (
        Path(xigma_override) if xigma_override
        else (lambda d: d / "src" if d is not None else None)(
            _discover(_XIGMA_ROOT, _XIGMA_MARKER, "COMPTON_GUI_XIGMA_SRC")
        )
    )

    for p, label, env_var in (
        (dfe5_path, "dfe5_compton_mc", "COMPTON_GUI_DFE5_PATH"),
        (xigma_src, "xigma_i", "COMPTON_GUI_XIGMA_SRC"),
    ):
        if p is None:
            print(
                f"compton_gui.bootstrap: could not find {label} under "
                f"{_XIGMA_ROOT} -- set {env_var} to its location if it's "
                f"installed elsewhere.",
                file=sys.stderr,
            )
            continue
        p_str = str(p)
        if p.is_dir() and p_str not in sys.path:
            sys.path.insert(0, p_str)
