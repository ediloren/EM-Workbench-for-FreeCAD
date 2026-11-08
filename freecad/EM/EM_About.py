#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2026 FastFieldSolvers                                   *
#*   Enrico Di Lorenzo                                                     *
#*   https://www.fastfieldsolvers.com                                      *
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



__title__="FreeCAD E.M. Workbench About class"
__author__ = "FastFieldSolvers - Enrico Di Lorenzo"
__url__ = "http://www.fastfieldsolvers.com"


# defines
# about information
EM_AUTHOR = 'Copyright 2026 FastFieldSolvers - Enrico Di Lorenzo\nhttps://www.fastfieldsolvers.com\n\n FastHenry support is copyright by FastFieldSolers\n and Efficient Power Conversion Inc.\n Developed under contract by EPC Inc.\n https://www.fastfieldsolvers.com, http://epc-co.com\n'
EM_LICENSE = 'Licensed under GNU Lesser General Public License (LGPL) version 2.1 or later\n'

import FreeCAD, Mesh, Part, MeshPart, Draft, DraftGeomUtils, os
from FreeCAD import Vector
from . import EM
if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtWidgets
    from FreeCAD import Qt
    translate = Qt.translate
    from PySide.QtCore import QT_TRANSLATE_NOOP
else:
    # \cond
    def translate(ctxt,txt):
        return txt
    def QT_TRANSLATE_NOOP(ctxt,txt):
        return txt
    # \endcond

from ._paths import ICONS_DIR as iconPath


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
        msg = translate("EM","ElectroMagnetic Workbench version ") + EM.EM_VERSION + "\n\n" + EM_AUTHOR + "\n" + EM_LICENSE

        if FreeCAD.GuiUp:
            # Simple QMessageBox providing "about" informaiton
            diag = QtWidgets.QMessageBox(FreeCADGui.getMainWindow())
            diag.setIcon(QtWidgets.QMessageBox.Information)
            diag.setWindowTitle(translate("EM_About","About ElectroMagnetic workbench"))
            diag.setText(msg)
            diag.setStandardButtons(QtWidgets.QMessageBox.Ok)
            diag.setWindowModality(QtCore.Qt.ApplicationModal)
            if hasattr(diag, "exec"):
                diag.exec()
            else:
                diag.exec_()
        else:
            FreeCAD.Console.PrintWarning(msg)

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_About',_CommandAbout())
