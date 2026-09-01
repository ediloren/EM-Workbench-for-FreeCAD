#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2026                                                    *
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


__title__="FreeCAD E.M. Workbench FasterCap / FastCap Solver Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
#
# supported capacitance solvers
EMFCSOLVER_SOLVERS = ["FasterCap", "FastCap"]
EMFCSOLVER_DEFSOLVER = "FasterCap"
# Units are not declared in a FasterCap / FastCap input file. They are kept
# here so that the future geometry exporter can scale coordinates consistently
# and the result importer can scale the capacitance matrix accordingly.
EMFCSOLVER_UNITS = ["km", "m", "cm", "mm", "um", "nm", "in", "mils"]
EMFCSOLVER_UNITS_VALS = [1e3, 1, 1e-2, 1e-3, 1e-6, 1e-9, 2.54e-2, 2.54e-5]
EMFCSOLVER_DEFUNITS = "mm"
# FasterCap defaults, from CAutoRefGlobalVars::Reset()
EMFCSOLVER_DEF_AUTO_MAX_ERR = 0.01
EMFCSOLVER_DEF_MESH_EPS = 0.1
EMFCSOLVER_DEF_MESH_CURV_COEFF = 3.0
EMFCSOLVER_DEF_GMRES_TOL = 0.01
# FastCap defaults. A partitioning depth of zero means automatic selection.
EMFCSOLVER_DEF_EXPANSION_ORDER = 2
EMFCSOLVER_DEF_PARTITIONING_DEPTH = 0
EMFCSOLVER_DEF_PERMITTIVITY_FACTOR = 1.0
# FastCap ABSTOL is compile-time configurable. Keep a neutral placeholder
# until the workbench defines which FastCap binary/build it supports.
EMFCSOLVER_DEF_ITERATION_TOL = 0.01
# default input file name
EMFCSOLVER_DEF_FILENAME = "fastercap_input_file.lst"

import FreeCAD, FreeCADGui, os

if FreeCAD.GuiUp:
    import FreeCADGui
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

def makeFCSolver(solver=None,units=None,autoMaxErr=None,meshEps=None,
                 meshCurvCoeff=None,gmresTol=None,expansionOrder=None,
                 partitioningDepth=None,permittivityFactor=None,
                 iterationTol=None,folder=None,filename=None,name='FCSolver'):
    ''' Creates a FasterCap / FastCap Solver object

        'solver' selects either "FasterCap" or "FastCap".
        'units' specifies how one FreeCAD unit is interpreted by the exporter.
        'autoMaxErr', 'meshEps', 'meshCurvCoeff' and 'gmresTol' are FasterCap
            solver parameters corresponding to the -a, -m, -mc and -t options.
        'expansionOrder', 'partitioningDepth', 'permittivityFactor' and
            'iterationTol' are FastCap parameters corresponding to the -o, -d,
            -p and -t options. A zero partitioning depth selects automatic mode.
        'folder' is the folder into which the input file will be saved.
        'filename' is the name of the file that will be exported.
        'name' is the name of the object.
    Example:
        solver = makeFCSolver()
'''
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    # this adds the relevant properties to the object, making it a _FCSolver
    _FCSolver(obj)
    # manage ViewProvider object
    if FreeCAD.GuiUp:
        _ViewProviderFCSolver(obj.ViewObject)
    if solver in EMFCSOLVER_SOLVERS:
        obj.Solver = solver
    else:
        obj.Solver = EMFCSOLVER_DEFSOLVER
    if units in EMFCSOLVER_UNITS:
        obj.Units = units
    else:
        obj.Units = EMFCSOLVER_DEFUNITS
    obj.AutoMaxError = autoMaxErr if autoMaxErr is not None else EMFCSOLVER_DEF_AUTO_MAX_ERR
    obj.MeshRefinement = meshEps if meshEps is not None else EMFCSOLVER_DEF_MESH_EPS
    obj.MeshCurvature = meshCurvCoeff if meshCurvCoeff is not None else EMFCSOLVER_DEF_MESH_CURV_COEFF
    obj.GmresTolerance = gmresTol if gmresTol is not None else EMFCSOLVER_DEF_GMRES_TOL
    obj.ExpansionOrder = expansionOrder if expansionOrder is not None else EMFCSOLVER_DEF_EXPANSION_ORDER
    obj.PartitioningDepth = partitioningDepth if partitioningDepth is not None else EMFCSOLVER_DEF_PARTITIONING_DEPTH
    obj.PermittivityFactor = permittivityFactor if permittivityFactor is not None else EMFCSOLVER_DEF_PERMITTIVITY_FACTOR
    obj.IterationTolerance = iterationTol if iterationTol is not None else EMFCSOLVER_DEF_ITERATION_TOL
    obj.Filename = filename if filename is not None else EMFCSOLVER_DEF_FILENAME
    if folder is not None:
        obj.Folder = folder
    else:
        obj.Folder = FreeCAD.ConfigGet("UserHomePath")
    # return the newly created Python object
    return obj

class _FCSolver:
    '''The EM FasterCap / FastCap Solver object'''
    def __init__(self, obj):
        ''' Add properties '''
        obj.addProperty("App::PropertyEnumeration","Solver","EM",QT_TRANSLATE_NOOP("App::Property","Capacitance solver used for the simulation"))
        obj.addProperty("App::PropertyEnumeration","Units","EM",QT_TRANSLATE_NOOP("App::Property","Measurement units used when exporting geometry"))
        obj.addProperty("App::PropertyFloatConstraint","AutoMaxError","FasterCap",QT_TRANSLATE_NOOP("App::Property","Maximum relative error for FasterCap automatic refinement (-a)"))
        obj.addProperty("App::PropertyFloatConstraint","MeshRefinement","FasterCap",QT_TRANSLATE_NOOP("App::Property","FasterCap mesh relative refinement value (-m)"))
        obj.addProperty("App::PropertyFloatConstraint","MeshCurvature","FasterCap",QT_TRANSLATE_NOOP("App::Property","FasterCap mesh curvature coefficient (-mc)"))
        obj.addProperty("App::PropertyFloatConstraint","GmresTolerance","FasterCap",QT_TRANSLATE_NOOP("App::Property","FasterCap GMRES iteration tolerance (-t)"))
        obj.addProperty("App::PropertyIntegerConstraint","ExpansionOrder","FastCap",QT_TRANSLATE_NOOP("App::Property","FastCap multipole expansion order (-o)"))
        obj.addProperty("App::PropertyIntegerConstraint","PartitioningDepth","FastCap",QT_TRANSLATE_NOOP("App::Property","FastCap partitioning depth (-d); zero selects automatic mode"))
        obj.addProperty("App::PropertyFloatConstraint","PermittivityFactor","FastCap",QT_TRANSLATE_NOOP("App::Property","FastCap permittivity factor (-p)"))
        obj.addProperty("App::PropertyFloatConstraint","IterationTolerance","FastCap",QT_TRANSLATE_NOOP("App::Property","FastCap iterative loop tolerance (-t)"))
        obj.addProperty("App::PropertyPath","Folder","EM",QT_TRANSLATE_NOOP("App::Property","Folder path for exporting the capacitance solver input file"))
        obj.addProperty("App::PropertyString","Filename","EM",QT_TRANSLATE_NOOP("App::Property","Simulation filename when exporting the capacitance solver input file"))
        obj.Proxy = self
        self.Type = "FCSolver"
        self.Object = obj
        obj.Solver = EMFCSOLVER_SOLVERS
        obj.Units = EMFCSOLVER_UNITS
        # Constraints prevent values unsupported by the two command-line parsers.
        obj.AutoMaxError = (EMFCSOLVER_DEF_AUTO_MAX_ERR, 1e-12, 1.0, 1e-4)
        obj.MeshRefinement = (EMFCSOLVER_DEF_MESH_EPS, 1e-12, 1e+12, 0.01)
        obj.MeshCurvature = (EMFCSOLVER_DEF_MESH_CURV_COEFF, 0.0, 1e+12, 0.1)
        obj.GmresTolerance = (EMFCSOLVER_DEF_GMRES_TOL, 1e-12, 1.0, 1e-4)
        obj.ExpansionOrder = (EMFCSOLVER_DEF_EXPANSION_ORDER, 1, 100, 1)
        obj.PartitioningDepth = (EMFCSOLVER_DEF_PARTITIONING_DEPTH, 0, 100, 1)
        obj.PermittivityFactor = (EMFCSOLVER_DEF_PERMITTIVITY_FACTOR, 0.0, 1e+12, 0.1)
        obj.IterationTolerance = (EMFCSOLVER_DEF_ITERATION_TOL, 1e-12, 1.0, 1e-4)

    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute()
    '''
        # but nothing to do
        return

    def onChanged(self, obj, prop):
        ''' take action if an object property 'prop' changed
    '''
        if not hasattr(self,"Object"):
            self.Object = obj
        # TODO: Once the execution/export workflow is defined, use Solver to
        # expose only the properties applicable to FasterCap or FastCap.

    def serialize(self,fid,headOrTail):
        ''' Serialize the solver portion of a FasterCap / FastCap list file

            Geometry records cannot be emitted until FC conductor and dielectric
            objects are defined. Solver controls are command-line options rather
            than statements in the input file and are therefore not serialized.
    '''
        if headOrTail == "head":
            fid.write("* FasterCap / FastCap input file created using FreeCAD's ElectroMagnetic Workbench\n")
            fid.write("* See http://www.freecad.org and http://www.fastfieldsolvers.com\n")
            fid.write("* Geometry units: " + self.Object.Units + "\n")
            fid.write("\n")
            # TODO: The future FC input-file exporter must serialize conductor
            # (C), dielectric (D) and group (G) records after this header.
        else:
            # FasterCap / FastCap list files have no mandatory end statement.
            return

    def getCommandLineOptions(self):
        ''' Return solver command-line options represented by this object '''
        if self.Object.Solver == "FasterCap":
            return ["-a" + str(self.Object.AutoMaxError),
                    "-m" + str(self.Object.MeshRefinement),
                    "-mc" + str(self.Object.MeshCurvature),
                    "-t" + str(self.Object.GmresTolerance)]
        options = ["-o" + str(self.Object.ExpansionOrder),
                   "-p" + str(self.Object.PermittivityFactor),
                   "-t" + str(self.Object.IterationTolerance)]
        if self.Object.PartitioningDepth > 0:
            options.append("-d" + str(self.Object.PartitioningDepth))
        return options

    def __getstate__(self):
        return self.Type

    def __setstate__(self,state):
        if state:
            self.Type = state

class _ViewProviderFCSolver:
    def __init__(self, obj):
        ''' Set this object to the proxy object of the actual view provider '''
        obj.Proxy = self
        self.Object = obj.Object

    def attach(self, obj):
        ''' Setup the scene sub-graph of the view provider, this method is mandatory '''
        self.Object = obj.Object
        return

    def updateData(self, fp, prop):
        ''' If a property of the handled feature has changed we have the chance to handle this here '''
        return

    def getDefaultDisplayMode(self):
        ''' Return the name of the default display mode. It must be defined in getDisplayModes. '''
        return "Flat Lines"

    def onChanged(self, vp, prop):
        ''' If the 'prop' property changed for the ViewProvider 'vp' '''
        return

    def getIcon(self):
        ''' Return the icon which will appear in the tree view. '''
        # TODO: Add Resources/EM_FCSolver.svg when the solver command is wired
        # into the workbench. Use the existing generic solver icon meanwhile.
        fcIcon = os.path.join(iconPath, 'EM_FCSolver.svg')
        if os.path.exists(fcIcon):
            return fcIcon
        return os.path.join(iconPath, 'EM_FHSolver.svg')

    def __getstate__(self):
        return None

    def __setstate__(self,state):
        return None

class _CommandFCSolver:
    ''' The EM FasterCap / FastCap Solver command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'EM_FCSolver.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_FCSolver","FasterCap / FastCap Solver"),
                'Accel': "E, C",
                'ToolTip': QT_TRANSLATE_NOOP("EM_FCSolver","Creates a FasterCap / FastCap Solver object")}

    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FCSolver"))
        FreeCADGui.addModule("EM")
        FreeCADGui.doCommand('obj=EM.makeFCSolver()')
        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_FCSolver',_CommandFCSolver())
