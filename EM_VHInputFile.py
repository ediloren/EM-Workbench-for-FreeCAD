#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2019                                                    *
#*   FastFieldSolvers S.R.L., http://www.fastfieldsolvers.com              *
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


__title__="FreeCAD E.M. Workbench VoxHenry create input file command"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

import FreeCAD, FreeCADGui, Mesh, Part, MeshPart, Draft, DraftGeomUtils, os
from FreeCAD import Vector
from PySide import QtCore, QtGui

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

def createVHInputFile(doc=None,filename=None,folder=None):
    '''Outputs a VoxHenry input file based on the active document geometry
    
       'doc' is the Document object that must contain at least one 
            EM_VHSolver object and the relevant geometry.
            If no 'doc' is given, the active document is used, if any.
       'filename' is the filename to use. If not passed as an argument,
            the 'Filename' property of the VHSolver object contained in the document
            will be used. If the "Filename" string in the VHSolver object is empty,
            the function builds a filename concatenating the document name
            with the default extension EMVHSOLVER_DEF_FILENAME.
            Whatever the name, if a file with the same name exists in the target
            folder, the user is prompted to know if he/she wants to overwrite it.
        'folder' is the folder where the file will be stored. If not passed
            as an argument, the 'Folder' property of the VHSolver object
            contained in the document will be used. If the 'Folder' string
            in the VHSolver object is empty, the function defaults to the
            user's home path (e.g. in Windows "C:\Documents and Settings\
            username\My Documents", in Linux "/home/username")
    
    Example:
         createVHInputFile()
'''
    if not doc:
        doc = FreeCAD.ActiveDocument
    if not doc:
        FreeCAD.Console.PrintWarning(translate("EM","No active document available. Aborting."))
        return
    # get the solver object, if any
    solver = [obj for obj in doc.Objects if Draft.getType(obj) == "VHSolver"]
    if solver == []:
        # error
        FreeCAD.Console.PrintWarning(translate("EM","VHSolver object not found in the document. Aborting."))
        return
    else:
        if len(solver) > 1:
            FreeCAD.Console.PrintWarning(translate("EM","More than one VHSolver object found in the document. Using the first one."))
        solver = solver[0]
    if not filename:
        # if 'filename' was not passed as an argument, retrieve it from the 'solver' object
        # (this should be the standard way)
        if solver.Filename == "":
            # build a filename concatenating the document name
            solver.Filename = doc.Name + EM.EMVHSOLVER_DEF_FILENAME
        filename = solver.Filename
    else:
        # otherwise, if the user passed a filename to the function, update it in the 'solver' object
        solver.Filename = filename
    if not folder:
        # if 'folder' was not passed as an argument, retrieve it from the 'solver' object
        # (this should be the standard way)
        if solver.Folder == "":
            # if not specified, default to the user's home path
            # (e.g. in Windows "C:\Documents and Settings\username\My Documents", in Linux "/home/username")
            solver.Folder = FreeCAD.ConfigGet("UserHomePath")
        folder = solver.Folder
    if not os.path.isdir(folder):
        # if 'folder' does not exists, create it
        os.mkdir(folder)
    # check if exists
    if os.path.isfile(folder + os.sep + filename):
        # filename already exists! Check if overwrite
        diag = QtGui.QMessageBox()
        diag.setText("File '" + str(filename) + "' exists in the folder '" + str(folder) + "'")
        diag.setInformativeText("Do you want to overwrite?")
        diag.setStandardButtons(QtGui.QMessageBox.Cancel | QtGui.QMessageBox.Ok)
        ret = diag.exec_()
        if ret == QtGui.QMessageBox.Cancel:
            return
    FreeCAD.Console.PrintMessage(QT_TRANSLATE_NOOP("EM","Exporting to VoxHenry file ") + "'" + folder + os.sep + filename + "'\n")
    with open(folder + os.sep + filename, 'w') as fid:
        # serialize the header
        solver.Proxy.serialize(fid)
        # check if there are superconductors
        isSupercond = solver.Proxy.isSupercond()
        if isSupercond:
            fid.write("* Specify there are superconductors\n")
            fid.write("Superconductor\n")
            fid.write("\n")
        # now the conductors
        fid.write("* Voxel list\n")
        fid.write("* Format is:\n")
        fid.write("* V <index_x> <index_y> <index_z> <conductivity S/m>\n")
        fid.write("*\n")
        fid.write("StartVoxelList\n")
        conds = [obj for obj in doc.Objects if Draft.getType(obj) == "VHConductor"]
        for cond in conds:
            FreeCAD.Console.PrintMessage(QT_TRANSLATE_NOOP("EM","  Exporting conductor ") + "'" + cond.Label + "'\n")
            cond.Proxy.serialize(fid, isSupercond)
        fid.write("EndVoxelList\n")
        fid.write("\n")
        # then the ports
        ports = [obj for obj in doc.Objects if Draft.getType(obj) == "VHPort"]
        if ports:
            fid.write("* Port nodes list\n")
            fid.write("* Format is:\n")
            fid.write("* N <portname> <excitation or ground (P/N)> <voxel_index_x> <voxel_index_y> <voxel_index_z> <node (+z,-z,+x,-x,+y,-y)>\n")
            fid.write("*\n")
            for port in ports:
                port.Proxy.serialize(fid)
            fid.write("\n")
    FreeCAD.Console.PrintMessage(QT_TRANSLATE_NOOP("EM","Finished exporting")+"\n")

class _CommandVHInputFile:
    ''' The EM VoxHenry create input file command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'EM_VHInputFile.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_VHInputFile","VHInputFile"),
                'Accel': "E, I",
                'ToolTip': QT_TRANSLATE_NOOP("EM_VHInputFile","Creates a FastHenry input file")}
                
    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        # preferences
        #p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/EM")
        #self.Width = p.GetFloat("Width",200)
        FreeCAD.ActiveDocument.openTransaction(translate("EM","Create a VoxHenry file"))
        FreeCADGui.addModule("EM")
        FreeCADGui.doCommand('obj=EM.createVHInputFile(App.ActiveDocument)')
        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_VHInputFile',_CommandVHInputFile())
