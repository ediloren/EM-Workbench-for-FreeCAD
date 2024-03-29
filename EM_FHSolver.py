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


__title__="FreeCAD E.M. Workbench FastHenry Solver Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
#
# copper conductivity 1/(m*Ohms)
EMFHSOLVER_DEF_SEGSIGMA = 5.8e7
# allowed .units
EMFHSOLVER_UNITS = ["km", "m", "cm", "mm", "um", "in", "mils"]
EMFHSOLVER_UNITS_VALS = [1e3, 1, 1e-2, 1e-3, 1e-6, 2.54e-2, 1e-3]
EMFHSOLVER_DEFUNITS = "mm"
EMFHSOLVER_DEFNHINC = 1
EMFHSOLVER_DEFNWINC = 1
EMFHSOLVER_DEFRW = 2
EMFHSOLVER_DEFRH = 2
EMFHSOLVER_DEFFMIN = 1
EMFHSOLVER_DEFFMAX = 1e9
EMFHSOLVER_DEFNDEC = 1
# default input file name
EMFHSOLVER_DEF_FILENAME = "fasthenry_input_file.inp"

import FreeCAD, FreeCADGui, Mesh, Part, MeshPart, Draft, DraftGeomUtils, os
from FreeCAD import Vector

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtGui
    from DraftTools import translate
    from PySide.QtCore import QT_TRANSLATE_NOOP
else:
    # \cond
    def translate(ctxt,txt):
        return txt
    def QT_TRANSLATE_NOOP(ctxt,txt):
        return txt
    # \endcond

__dir__ = os.path.dirname(__file__)
iconPath = os.path.join( __dir__, 'Resources' )

def makeFHSolver(units=None,sigma=None,nhinc=None,nwinc=None,rh=None,rw=None,fmin=None,fmax=None,ndec=None,folder=None,filename=None,name='FHSolver'):
    ''' Creates a FastHenry Solver object (all statements needed for the simulation)

        'units' is the FastHenry unit of measurement. Each unit in FreeCad will be
            one unit of the corresponding unit of measurement in FastHenry.
            Allowed values are: "km", "m", "cm", "mm", "um", "in", "mils".
            Defaults to EMFHSOLVER_DEFUNITS
        'sigma' is the float default conductivity. Defaults to EMFHSOLVER_DEF_SEGSIGMA
        'nhinc' is the integer default nhinc parameter in FastHenry, for defining
            the segment height discretization into filaments. Defaults to EMFHSOLVER_DEFNHINC
        'nwinc' is the integer default nwinc parameter in FastHenry, for defining
            the segment width discretization into filaments. Defaults to EMFHSOLVER_DEFNWINC
        'rh' is the integer default rh parameter in FastHenry, for defining
            the segment height discretization ratio. Defaults to EMFHSOLVER_DEFRH
        'rw' is the integer default rw parameter in FastHenry, for defining
            the segment width discretization ratio. Defaults to EMFHSOLVER_DEFRW
        'fmin' is the float minimum simulation frequency
        'fmax' is the float maximum simulation frequency
        'ndec' is the float value defining how many frequency points per decade
            will be simulated
        'folder' is the folder into which the FastHenry file will be saved.
            Defaults to the user's home path (e.g. in Windows "C:\\Documents
             and Settings\\username\\My Documents", in Linux "/home/username")
        'filename' is the name of the file that will be exported.
            Defaults to EMFHSOLVER_DEF_FILENAME
        'name' is the name of the object
    Example:
        solver = makeFHSolver()
'''
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    # this adds the relevant properties to the object
    #'obj' (e.g. 'Base' property) making it a _FHSolver
    _FHSolver(obj)
    # manage ViewProvider object
    if FreeCAD.GuiUp:
        _ViewProviderFHSolver(obj.ViewObject)
        # set base ViewObject properties to user-selected values (if any)
    if units in EMFHSOLVER_UNITS:
        obj.Units = units
    else:
        obj.Units = EMFHSOLVER_DEFUNITS
    if sigma:
        obj.Sigma = sigma
    else:
        # use default sigma, but scale it according to the chosen units of measurement
        obj.Sigma = EMFHSOLVER_DEF_SEGSIGMA * EMFHSOLVER_UNITS_VALS[EMFHSOLVER_UNITS.index(obj.Units)]
    if nhinc:
        obj.nhinc = nhinc
    else:
        obj.nhinc = EMFHSOLVER_DEFNHINC
    if nwinc:
        obj.nwinc = nwinc
    else:
        obj.nwinc = EMFHSOLVER_DEFNWINC
    if rh:
        obj.rh = rh
    else:
        obj.rh = EMFHSOLVER_DEFRH
    if rw:
        obj.rw = rw
    else:
        obj.rw = EMFHSOLVER_DEFRW
    if fmin:
        obj.fmin = fmin
    else:
        obj.fmin = EMFHSOLVER_DEFFMIN
    if fmax:
        obj.fmax = rw
    else:
        obj.fmax = EMFHSOLVER_DEFFMAX
    if ndec:
        obj.ndec = ndec
    else:
        obj.ndec = EMFHSOLVER_DEFNDEC
    if filename:
        obj.Filename = filename
    else:
        obj.Filename = EMFHSOLVER_DEF_FILENAME
    if folder:
        obj.Folder = folder
    else:
        # if not specified, default to the user's home path
        # (e.g. in Windows "C:\Documents and Settings\username\My Documents", in Linux "/home/username")
        obj.Folder = FreeCAD.ConfigGet("UserHomePath")
    # return the newly created Python object
    return obj

class _FHSolver:
    '''The EM FastHenry Solver object'''
    def __init__(self, obj):
        ''' Add properties '''
        obj.addProperty("App::PropertyEnumeration","Units","EM",QT_TRANSLATE_NOOP("App::Property","The FastHenry '.units'"))
        obj.addProperty("App::PropertyFloat","Sigma","EM",QT_TRANSLATE_NOOP("App::Property","Default Segment conductivity ('sigma' segment parameter in '.default')"))
        obj.addProperty("App::PropertyInteger","nhinc","EM",QT_TRANSLATE_NOOP("App::Property","Default number of filaments in the height direction ('nhinc' segment parameter in '.default')"))
        obj.addProperty("App::PropertyInteger","nwinc","EM",QT_TRANSLATE_NOOP("App::Property","Default number of filaments in the width direction ('nwinc' segment parameter in '.default')"))
        obj.addProperty("App::PropertyInteger","rh","EM",QT_TRANSLATE_NOOP("App::Property","Default ratio of adjacent filaments in the height direction ('rh' segment parameter in '.default')"))
        obj.addProperty("App::PropertyInteger","rw","EM",QT_TRANSLATE_NOOP("App::Property","Default ratio of adjacent filaments in the width direction ('rw' segment parameter in '.default')"))
        obj.addProperty("App::PropertyFloat","fmin","EM",QT_TRANSLATE_NOOP("App::Property","Lowest simulation frequency ('fmin' parameter in '.freq')"))
        obj.addProperty("App::PropertyFloat","fmax","EM",QT_TRANSLATE_NOOP("App::Property","Highest simulation frequency ('fmzx' parameter in '.freq')"))
        obj.addProperty("App::PropertyFloat","ndec","EM",QT_TRANSLATE_NOOP("App::Property","Number of desired frequency points per decade ('ndec' parameter in '.freq')"))
        obj.addProperty("App::PropertyPath","Folder","EM",QT_TRANSLATE_NOOP("App::Property","Folder path for exporting the file in FastHenry input file format"))
        obj.addProperty("App::PropertyString","Filename","EM",QT_TRANSLATE_NOOP("App::Property","Simulation filename when exporting to FastHenry input file format"))
        obj.Proxy = self
        self.Type = "FHSolver"
        obj.Units = EMFHSOLVER_UNITS

    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute()
    '''
        # but nothing to do
        return

    def onChanged(self, obj, prop):
        ''' take action if an object property 'prop' changed
    '''
        #FreeCAD.Console.PrintWarning("\n_FHSolver onChanged(" + str(prop)+")\n") #debug
        if not hasattr(self,"Object"):
            # on restore, self.Object is not there anymore (JSON does not serialize complex objects
            # members of the class, so __getstate__() and __setstate__() skip them);
            # so we must "re-attach" (re-create) the 'self.Object'
            self.Object = obj

    def serialize(self,fid,headOrTail):
        ''' Serialize the object to the 'fid' file descriptor
    '''
        if headOrTail == "head":
            fid.write("* FastHenry input file created using FreeCAD's ElectroMagnetic Workbench\n")
            fid.write("* See http://www.freecad.org, http://www.fastfieldsolvers.com and http://epc-co.com\n")
            fid.write("\n")
            fid.write(".units " + self.Object.Units + "\n")
            fid.write("\n")
            fid.write(".default sigma=" + str(self.Object.Sigma) + " nhinc=" + str(self.Object.nhinc) + " nwinc=" + str(self.Object.nwinc))
            fid.write(" rh=" + str(self.Object.rh) + " rw=" + str(self.Object.rw) + "\n")
            fid.write("\n")
        else:
            fid.write(".freq fmin=" + str(self.Object.fmin) + " fmax=" + str(self.Object.fmax) + " ndec=" + str(self.Object.ndec) + "\n")
            fid.write("\n")
            fid.write(".end\n")

    def __getstate__(self):
        return self.Type

    def __setstate__(self,state):
        if state:
            self.Type = state

class _ViewProviderFHSolver:
    def __init__(self, obj):
        ''' Set this object to the proxy object of the actual view provider '''
        obj.Proxy = self
        self.Object = obj.Object

    def attach(self, obj):
        ''' Setup the scene sub-graph of the view provider, this method is mandatory '''
        # on restore, self.Object is not there anymore (JSON does not serialize complex objects
        # members of the class, so __getstate__() and __setstate__() skip them);
        # so we must "re-attach" (re-create) the 'self.Object'
        self.Object = obj.Object
        return

    def updateData(self, fp, prop):
        ''' If a property of the handled feature has changed we have the chance to handle this here '''
        #FreeCAD.Console.PrintMessage("ViewProvider updateData(),  property: " + str(prop) + "\n") # debug
        return

    def getDefaultDisplayMode(self):
        ''' Return the name of the default display mode. It must be defined in getDisplayModes. '''
        return "Flat Lines"

    def onChanged(self, vp, prop):
        ''' If the 'prop' property changed for the ViewProvider 'vp' '''
        #FreeCAD.Console.PrintMessage("ViewProvider onChanged(), property: " + str(prop) + "\n") # debug

    def getIcon(self):
        ''' Return the icon which will appear in the tree view. This method is optional
        and if not defined a default icon is shown.
        '''
        return os.path.join(iconPath, 'EM_FHSolver.svg')

    def __getstate__(self):
        return None

    def __setstate__(self,state):
        return None

class _CommandFHSolver:
    ''' The EM FastHenry Solver command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'EM_FHSolver.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_FHSolver","FHSolver"),
                'Accel': "E, X",
                'ToolTip': QT_TRANSLATE_NOOP("EM_FHSolver","Creates a FastHenry Solver object")}

    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        # preferences
        #p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/EM")
        #self.Width = p.GetFloat("Width",200)
        FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FHSolver"))
        FreeCADGui.addModule("EM")
        FreeCADGui.doCommand('obj=EM.makeFHSolver()')
        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_FHSolver',_CommandFHSolver())
