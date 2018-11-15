#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2018                                                    *  
#*   FastFieldSolvers S.R.L.  http://www.fastfieldsolvers.com              *  
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
        self.emtools = ["EM_FHSolver", "EM_FHNode", "EM_FHSegment", "EM_FHPort", "EM_FHInputFile"]
                     
        def QT_TRANSLATE_NOOP(scope, text): return text
        self.appendToolbar(QT_TRANSLATE_NOOP("Workbench","E.M. tools"),self.emtools)
        self.appendMenu(QT_TRANSLATE_NOOP("EM","&EM"),self.emtools)
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



