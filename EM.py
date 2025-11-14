# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the ElectroMagnetic addon.

################################################################################
#                                                                              #
#   © 2018 Efficient Power Conversion Corporation, Inc. ( http://epc-co.com )  #
#                                                                              #
#   Developed by FastFieldSolvers S.R.L. ( http://www.fastfieldsolvers.com )   #
#   under contract by Efficient Power Conversion Corporation, Inc.             #
#                                                                              #
#   This addon is free software: you can redistribute it and/or modify it      #
#   under the terms of the GNU Lesser General Public License as published      #
#   by the Free Software Foundation, either version 2.1 of the License,        #
#   or (at your option) any later version.                                     #
#                                                                              #
#   This addon is distributed in the hope that it will be useful,              #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser                          #
#   General Public License along with this addon.                              #
#   If not, see https://www.gnu.org/licenses                                   #
#                                                                              #
################################################################################


__title__="FreeCAD E.M. Workbench API"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

## \defgroup EM E.M.
#  \ingroup PYTHONWORKBENCHES
#  \brief ElectroMagnetic tools
#
#  This module provides tools for ElectroMagnetic analysis,
#  enabling to create suitable geometries, launching field solvers,
#  and post-processing the results

'''The E.M. module provides tools for ElectroMagnetic analysis'''

import sys

# Python3 compatibility
if sys.version_info >= (3, 4):
    from importlib import reload
elif sys.version_info >= (3, 0):
    from imp import reload

import FreeCAD
if FreeCAD.GuiUp:
	import FreeCADGui
	FreeCADGui.updateLocale()

from EM_Globals import *
from EM_About import *
# FastHenry specific
from EM_FHNode import *
from EM_FHSegment import *
from EM_FHPath import *
from EM_FHPlaneHole import *
from EM_FHPlane import *
from EM_FHPort import *
from EM_FHEquiv import *
from EM_FHSolver import *
from EM_FHInputFile import *
# VoxHenry specific
from EM_VHSolver import *
from EM_VHConductor import *
from EM_VHPort import *
from EM_VHInputFile import *

# for debugging
#import EM_Globals
#reload(EM_Globals)
#from EM_Globals import *
#import EM_About
#reload(EM_About)
#from EM_About import *
#import EM_FHNode
#reload(EM_FHNode)
#from EM_FHNode import *
#import EM_FHSegment
#reload(EM_FHSegment)
#from EM_FHSegment import *
#import EM_FHPath
#reload(EM_FHPath)
#from EM_FHPath import *
#import EM_FHPlaneHole
#reload(EM_FHPlaneHole)
#from EM_FHPlaneHole import *
#import EM_FHPlane
#reload(EM_FHPlane)
#from EM_FHPlane import *
#import EM_FHPort
#reload(EM_FHPort)
#from EM_FHPort import *
#import EM_FHEquiv
#reload(EM_FHEquiv)
#from EM_FHEquiv import *
#import EM_FHSolver
#reload(EM_FHSolver)
#from EM_FHSolver import *
#import EM_FHInputFile
#reload(EM_FHInputFile)
#from EM_FHInputFile import *
#import EM_VHSolver
#reload(EM_VHSolver)
#from EM_VHSolver import *
#import EM_VHConductor
#reload(EM_VHConductor)
#from EM_VHConductor import *
#import EM_VHPort
#reload(EM_VHPort)
#from EM_VHPort import *
#import EM_VHInputFile
#reload(EM_VHInputFile)
#from EM_VHInputFile import *
