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
#*   as published by the Free Software Foundation; either version 2 of     *
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
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

class EMWorkbench(Workbench):
    "E.M. workbench object"
    def __init__(self):
        self.__class__.Icon = FreeCAD.getUserAppDataDir()+ "Mod/EM/Resources/EMWorkbench.svg"
        self.__class__.MenuText = "E.M."
        self.__class__.ToolTip = "ElectroMagnetic workbench"

    def Initialize(self):
        import DraftTools,DraftGui
        from DraftTools import translate
        # import the EM module (and therefore all commands makeXXX)
        import EM
        # E.M. tools
        self.emfhtools = ["EM_FHSolver", "EM_FHNode", "EM_FHSegment", "EM_FHPath", "EM_FHPlane",
                "EM_FHPlaneHole", "EM_FHPlaneAddRemoveNodeHole", "EM_FHEquiv", "EM_FHPort", "EM_FHInputFile"]
        # draft tools
        # setup menus
        self.draftcmdList = ["Draft_Line","Draft_Rectangle"]
        self.draftmodtools = ["Draft_Move","Draft_Rotate","Draft_Offset",
                "Draft_Trimex", "Draft_Upgrade", "Draft_Downgrade", "Draft_Scale",
                "Draft_Shape2DView","Draft_Draft2Sketch","Draft_Array",
                "Draft_Clone"]
        self.treecmdList = ["Draft_SelectPlane", "Draft_ShowSnapBar","Draft_ToggleGrid"]
        self.snapList = ['Draft_Snap_Lock','Draft_Snap_Midpoint','Draft_Snap_Perpendicular',
                         'Draft_Snap_Grid','Draft_Snap_Intersection','Draft_Snap_Parallel',
                         'Draft_Snap_Endpoint','Draft_Snap_Angle','Draft_Snap_Center',
                         'Draft_Snap_Extension','Draft_Snap_Near','Draft_Snap_Ortho','Draft_Snap_Special',
                         'Draft_Snap_Dimensions','Draft_Snap_WorkingPlane']

        def QT_TRANSLATE_NOOP(scope, text): return text
        self.appendToolbar(QT_TRANSLATE_NOOP("Workbench","E.M. tools"),self.emfhtools)
        self.appendToolbar(QT_TRANSLATE_NOOP("Workbench","Draft creation tools"),self.draftcmdList)
        self.appendToolbar(QT_TRANSLATE_NOOP("Workbench","Draft mod tools"),self.draftmodtools)
        self.appendMenu(QT_TRANSLATE_NOOP("EM","&EM"),self.emfhtools)
        self.appendMenu(QT_TRANSLATE_NOOP("EM","&Draft"),self.draftcmdList+self.draftmodtools+self.treecmdList)
        self.appendMenu([QT_TRANSLATE_NOOP("EM","&Draft"),QT_TRANSLATE_NOOP("arch","Snapping")],self.snapList)
        #FreeCADGui.addIconPath(":/icons")
        #FreeCADGui.addLanguagePath(":/translations")
        #FreeCADGui.addPreferencePage(":/ui/preferences-EM.ui","EM")
        #FreeCADGui.addPreferencePage(":/ui/preferences-aEMdefaults.ui","EM")
        Log ('Loading EM module... done\n')

    def Activated(self):
        Log("EM workbench activated\n")
        
    def Deactivated(self):
        Log("EM workbench deactivated\n")

#    def ContextMenu(self, recipient):
#        self.appendContextMenu("Utilities",self.EMcontexttools)

    # needed if this is a pure Python workbench
    def GetClassName(self): 
        return "Gui::PythonWorkbench"

FreeCADGui.addWorkbench(EMWorkbench)

# File format pref pages are independent and can be loaded at startup
#import EM_rc
#FreeCADGui.addPreferencePage(":/ui/preferences-inp.ui","Import-Export")



