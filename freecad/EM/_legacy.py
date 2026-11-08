#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2018                                                    *
#*   Efficient Power Conversion Corporation, Inc.  http://epc-co.com       *
#*                                                                         *
#*   Developed by FastFieldSolvers S.R.L. under contract by EPC            *
#*   http://www.fastfieldsolvers.com                                       *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2.1 of   *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   This program is distributed in the hope that it will be useful,       *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Library General Public License for more details.                  *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************

"""Lazy, read-only import bridge for pre-namespace FH/VH document proxies.

Only the historical persistence modules are exposed. Classes are always defined
in freecad.EM, so saving a restored document writes their modern module paths.
No legacy EM scripting API or FC document compatibility is provided.
"""

from importlib import import_module
from importlib.util import spec_from_file_location
import sys
from types import ModuleType


LEGACY_MODULES = (
    "EM_FHNode", "EM_FHSegment", "EM_FHPath", "EM_FHPlane",
    "EM_FHPlaneHole", "EM_FHEquiv", "EM_FHPort", "EM_FHSolver",
    "EM_VHSolver", "EM_VHConductor", "EM_VHPort",
)


class _LegacyModule(ModuleType):
    def __getattr__(self, name):
        # Import machinery probes metadata such as __path__. Do not load a
        # solver for those probes, or pretend these flat modules are packages.
        if name.startswith("__"):
            raise AttributeError(name)
        implementation = import_module("." + self.__name__, __package__)
        value = getattr(implementation, name)
        setattr(self, name, value)
        return value


def install():
    """Make old proxy names importable before any workbench is activated."""
    for name in LEGACY_MODULES:
        if name not in sys.modules:
            module = _LegacyModule(name)
            # FreeCAD validates document imports against addon file origins.
            # These synthetic aliases originate here, not in an unknown path.
            module.__file__ = __file__
            module.__spec__ = spec_from_file_location(name, __file__)
            sys.modules[name] = module
