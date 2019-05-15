#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2018                                                    *                                                                      *
#*   FastFieldSolvers S.R.L.                                               *
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



__title__="FreeCAD E.M. Workbench About class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# imported defines
from EM_Globals import EM_VERSION

# defines
# about information
EM_AUTHOR = 'Copyright 2019 FastFieldSolvers S.R.L. and Efficient Power Conversion Inc.\nhttp://www.fastfieldsolvers.com, http://epc-co.com\nPartially developed by FastFieldSolvers S.R.L. under contract by EPC Inc.\n'
EM_LICENSE = 'Licensed under GNU Lesser General Public License (LGPL) version 2\n'

import FreeCAD, FreeCADGui, Mesh, Part, MeshPart, Draft, DraftGeomUtils, os
from FreeCAD import Vector

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtGui
    from DraftTools import translate
    from PySide.QtCore import QT_TRANSLATE_NOOP
else:
    # \cond
    def translate(ctxt,txt, utf8_decode=False):
        return txt
    def QT_TRANSLATE_NOOP(ctxt,txt):
        return txt
    # \endcond

__dir__ = os.path.dirname(__file__)
iconPath = os.path.join( __dir__, 'Resources' )

  
class _CommandAbout:
    ''' The EM About command definition
'''
    def GetResources(self):
        # no need of icon or accelerator
        return {'MenuText': QT_TRANSLATE_NOOP("EM_About","About"),
                'ToolTip': QT_TRANSLATE_NOOP("EM_About","About the ElectroMagnetic Workbench")}
                
    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        msg = translate("EM","ElectroMagnetic Workbench version ") + EM_VERSION + "\n\n" + EM_AUTHOR + "\n" + EM_LICENSE

        if FreeCAD.GuiUp:
            # Simple QMessageBox providing "about" information
            diag = QtGui.QMessageBox(QtGui.QMessageBox.Information, translate("EM_About","About ElectroMagnetic workbench"), msg)
            diag.setWindowModality(QtCore.Qt.ApplicationModal)
            diag.exec_()
        else:
            FreeCAD.Console.PrintWarning(msg)

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_About',_CommandAbout())
