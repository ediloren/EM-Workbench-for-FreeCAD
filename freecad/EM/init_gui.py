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


__title__="FreeCAD E.M. Workbench GUI"
__author__ = "FastFieldSolvers - Enrico Di Lorenzo"
__url__ = "http://www.fastfieldsolvers.com"

import FreeCAD
import FreeCADGui

from ._paths import ICONS_DIR
import os


class EMWorkbench(FreeCADGui.Workbench):
    """ElectroMagnetic workbench."""
    Icon = os.path.join(ICONS_DIR, "EMWorkbench.svg")
    MenuText = "E.M."
    ToolTip = "ElectroMagnetic workbench"

    def Initialize(self):
        # Initialize Draft's commands and snapper before using its tools.
        import DraftTools, DraftGui
        FreeCADGui.addIconPath(ICONS_DIR)
        from . import (EM_About, EM_FHSolver, EM_FHNode, EM_FHSegment,
                       EM_FHPath, EM_FHPlane, EM_FHPlaneHole, EM_FHEquiv,
                       EM_FHPort, EM_FHInputFile, EM_VHSolver, EM_VHConductor,
                       EM_VHPort, EM_VHInputFile, EM_FCSolver, EM_FCConductor,
                       EM_FCDielectric, EM_FCExport, EM_FCImport)
        # E.M. tools
        self.emtools = ["EM_About"]
        self.emfhtools = ["EM_FHSolver", "EM_FHNode", "EM_FHSegment", "EM_FHPath", "EM_FHPlane",
                "EM_FHPlaneHole", "EM_FHPlaneAddRemoveNodeHole", "EM_FHEquiv", "EM_FHPort", "EM_FHInputFile"]
        self.emvhtools = ["EM_VHSolver", "EM_VHConductor", "EM_VHPort", "EM_VHCondPortVoxelize", "EM_VHVoxelizeAll", "EM_VHInputFile"]
        # FC tools follow the intended workflow: configure the document, wrap
        # conductor/dielectric sources, explicitly panelize for inspection, then
        # export or import solver data.  Panelize precedes Export because export
        # deliberately consumes the frozen preview rather than rebuilding it.
        self.emfctools = ["EM_FCSolver", "EM_FCConductor",
                "EM_FCDielectric", "EM_FCPanelize", "EM_FCExport",
                "EM_FCImport"]
        # draft tools
        # setup menus
        self.draftcmdList = ["Draft_Line","Draft_Rectangle"]
        self.draftmodtools = ["Draft_Move","Draft_Rotate","Draft_Offset",
                "Draft_Trimex", "Draft_Upgrade", "Draft_Downgrade", "Draft_Scale",
                "Draft_Shape2DView","Draft_Draft2Sketch","Draft_OrthoArray",
                "Draft_Clone"]
        self.treecmdList = ["Draft_SelectPlane", "Draft_ShowSnapBar","Draft_ToggleGrid"]
        self.snapList = ['Draft_Snap_Lock','Draft_Snap_Midpoint','Draft_Snap_Perpendicular',
                         'Draft_Snap_Grid','Draft_Snap_Intersection','Draft_Snap_Parallel',
                         'Draft_Snap_Endpoint','Draft_Snap_Angle','Draft_Snap_Center',
                         'Draft_Snap_Extension','Draft_Snap_Near','Draft_Snap_Ortho','Draft_Snap_Special',
                         'Draft_Snap_Dimensions','Draft_Snap_WorkingPlane']

        def QT_TRANSLATE_NOOP(scope, text): return text
        self.appendToolbar(QT_TRANSLATE_NOOP("Workbench","E.M. FastHenry tools"),self.emfhtools)
        self.appendToolbar(QT_TRANSLATE_NOOP("Workbench","E.M. VoxHenry tools"),self.emvhtools)
        self.appendToolbar(QT_TRANSLATE_NOOP("Workbench","E.M. FasterCap / FastCap tools"),self.emfctools)
        self.appendToolbar(QT_TRANSLATE_NOOP("Workbench","Draft creation tools"),self.draftcmdList)
        self.appendToolbar(QT_TRANSLATE_NOOP("Workbench","Draft mod tools"),self.draftmodtools)
        self.appendMenu(QT_TRANSLATE_NOOP("EM","&EM"),self.emfhtools + self.emvhtools + self.emfctools + self.emtools)
        self.appendMenu(QT_TRANSLATE_NOOP("EM","&Draft"),self.draftcmdList+self.draftmodtools+self.treecmdList)
        self.appendMenu([QT_TRANSLATE_NOOP("EM","&Draft"),QT_TRANSLATE_NOOP("arch","Snapping")],self.snapList)
        FreeCAD.Console.PrintLog('Loading EM module... done\n')

    def Activated(self):
        FreeCAD.Console.PrintLog("EM workbench activated\n")

    def Deactivated(self):
        FreeCAD.Console.PrintLog("EM workbench deactivated\n")

#    def ContextMenu(self, recipient):
#        self.appendContextMenu("Utilities",self.EMcontexttools)

    # needed if this is a pure Python workbench
    def GetClassName(self):
        return "Gui::PythonWorkbench"

FreeCADGui.addWorkbench(EMWorkbench())

