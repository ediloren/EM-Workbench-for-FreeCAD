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

# Solver-object architecture notes:
# - One FCSolver is the authority for dimension, target, units, background
#   material, and tolerances throughout a document.
# - It stores settings only; extraction and panelization are explicit operations.
# - Enumeration order is persistent data as well as a set of GUI choices.
# - FasterCap and FastCap switches remain separate because similarly named
#   controls do not necessarily have interchangeable meanings.
# - GeometryTolerance never authorizes healing or topology modification.
# - Property creation is idempotent and doubles as document migration.

# defines
EMFCSOLVER_DIMENSIONS = ["3D", "2D"]
EMFCSOLVER_DEFDIMENSION = "3D"
EMFCSOLVER_SOLVERS = ["FasterCap", "FastCap"]
EMFCSOLVER_DEFSOLVER = "FasterCap"
EMFCSOLVER_UNITS = ["km", "m", "cm", "mm", "um", "nm", "in", "mils"]
EMFCSOLVER_UNITS_VALS = [1e3, 1, 1e-2, 1e-3, 1e-6, 1e-9, 2.54e-2, 2.54e-5]
EMFCSOLVER_DEFUNITS = "mm"
EMFCSOLVER_DEF_SPACE_PERMITTIVITY = 1.0
EMFCSOLVER_DEF_GEOMETRY_TOLERANCE = 1.0e-7
EMFCSOLVER_DEF_MAX_PANEL_SIZE = 1.0
# FasterCap defaults, from CAutoRefGlobalVars::Reset()
EMFCSOLVER_DEF_AUTO_MAX_ERR = 0.01
EMFCSOLVER_DEF_MESH_EPS = 0.1
EMFCSOLVER_DEF_MESH_CURV_COEFF = 3.0
EMFCSOLVER_DEF_GMRES_TOL = 0.01
# FastCap defaults. A partitioning depth of zero means automatic selection.
EMFCSOLVER_DEF_EXPANSION_ORDER = 2
EMFCSOLVER_DEF_PARTITIONING_DEPTH = 0
EMFCSOLVER_DEF_PERMITTIVITY_FACTOR = 1.0
EMFCSOLVER_DEF_ITERATION_TOL = 0.01
EMFCSOLVER_DEF_FILENAME = "fastercap_input_file.lst"

import os

import FreeCAD

if FreeCAD.GuiUp:
    import FreeCADGui
    from DraftTools import translate
    from PySide.QtCore import QT_TRANSLATE_NOOP
else:
    # \cond
    def translate(ctxt, txt):
        return txt
    def QT_TRANSLATE_NOOP(ctxt, txt):
        return txt
    # \endcond

__dir__ = os.path.dirname(__file__)
iconPath = os.path.join(__dir__, 'Resources')


# Proxy.Type is used because every solver is backed by a generic FeaturePython
# document object rather than a dedicated C++ TypeId.
def getFCSolver(document=None, createIfNotExisting=False):
    '''Return the first FCSolver in a document, optionally creating one.'''
    if document is None:
        document = FreeCAD.ActiveDocument
    if document is None:
        return None
    solvers = [obj for obj in document.Objects
               if getattr(getattr(obj, "Proxy", None), "Type", None) ==
               "FCSolver"]
    if solvers:
        return solvers[0]
    if createIfNotExisting and document is FreeCAD.ActiveDocument:
        return makeFCSolver()
    return None


def getFCSpacePermittivity(document=None):
    '''Return the document background permittivity or the vacuum default.'''
    solver = getFCSolver(document)
    if solver is None or not hasattr(solver, "SpacePermittivity"):
        return EMFCSOLVER_DEF_SPACE_PERMITTIVITY
    return float(solver.SpacePermittivity)


# Refuse a second settings object before allocation: downstream extraction must
# never choose between conflicting global units or dimensions.
def makeFCSolver(solver=None, units=None, autoMaxErr=None, meshEps=None,
                 meshCurvCoeff=None, gmresTol=None, expansionOrder=None,
                 partitioningDepth=None, permittivityFactor=None,
                 iterationTol=None, folder=None, filename=None,
                 dimension=None, spacePermittivity=None,
                 referenceConductor=None, name='FCSolver',
                 geometryTolerance=None, maxPanelSize=None):
    '''Create the persistent global FasterCap / FastCap settings object.

       'dimension' selects a 2D or 3D model and 'solver' selects FasterCap or
            FastCap. 'spacePermittivity' is the background relative
            permittivity used as a fallback by newly created FC objects.
       'referenceConductor' identifies the global zero-potential conductor in
            2D and is hidden from the property editor while Dimension is 3D.
       'geometryTolerance' controls numerical comparisons only; it does not
            remove or close physical gaps or features.
       'maxPanelSize' is the FastCap maximum panel edge dimension in Units.
       Remaining arguments store solver command-line settings for later use.
    '''
    if FreeCAD.ActiveDocument is None:
        FreeCAD.Console.PrintWarning(
            translate("EM", "No active document available. Cannot create FCSolver.\n"))
        return None

    existing = getFCSolver(FreeCAD.ActiveDocument)
    if existing is not None:
        FreeCAD.Console.PrintWarning(translate(
            "EM", "Only one FCSolver is allowed per document; returning the existing object.\n"))
        return existing

    # The solver owns document-wide settings but no TopoShape.  An application
    # feature therefore provides all required persistence without presenting it
    # as a geometric Part object.
    obj = FreeCAD.ActiveDocument.addObject("App::FeaturePython", name)
    obj.Label = translate("EM", name)
    _FCSolver(obj)
    if FreeCAD.GuiUp:
        _ViewProviderFCSolver(obj.ViewObject)

    obj.Dimension = (dimension if dimension in EMFCSOLVER_DIMENSIONS
                     else EMFCSOLVER_DEFDIMENSION)
    obj.TargetSolver = (solver if solver in EMFCSOLVER_SOLVERS
                        else EMFCSOLVER_DEFSOLVER)
    obj.Units = units if units in EMFCSOLVER_UNITS else EMFCSOLVER_DEFUNITS
    obj.SpacePermittivity = (
        EMFCSOLVER_DEF_SPACE_PERMITTIVITY
        if spacePermittivity is None else spacePermittivity)
    obj.GeometryTolerance = (
        EMFCSOLVER_DEF_GEOMETRY_TOLERANCE
        if geometryTolerance is None else geometryTolerance)
    obj.MaxPanelSize = (
        EMFCSOLVER_DEF_MAX_PANEL_SIZE
        if maxPanelSize is None else maxPanelSize)
    if referenceConductor is not None:
        obj.ReferenceConductor = referenceConductor
    obj.AutoMaxError = (EMFCSOLVER_DEF_AUTO_MAX_ERR
                        if autoMaxErr is None else autoMaxErr)
    obj.MeshRefinement = (EMFCSOLVER_DEF_MESH_EPS
                          if meshEps is None else meshEps)
    obj.MeshCurvature = (EMFCSOLVER_DEF_MESH_CURV_COEFF
                         if meshCurvCoeff is None else meshCurvCoeff)
    obj.GmresTolerance = (EMFCSOLVER_DEF_GMRES_TOL
                          if gmresTol is None else gmresTol)
    obj.ExpansionOrder = (EMFCSOLVER_DEF_EXPANSION_ORDER
                          if expansionOrder is None else expansionOrder)
    obj.PartitioningDepth = (EMFCSOLVER_DEF_PARTITIONING_DEPTH
                             if partitioningDepth is None
                             else partitioningDepth)
    obj.PermittivityFactor = (EMFCSOLVER_DEF_PERMITTIVITY_FACTOR
                              if permittivityFactor is None
                              else permittivityFactor)
    obj.IterationTolerance = (EMFCSOLVER_DEF_ITERATION_TOL
                              if iterationTol is None else iterationTol)
    obj.Filename = filename or EMFCSOLVER_DEF_FILENAME
    obj.Folder = folder or FreeCAD.ConfigGet("UserHomePath")
    obj.Proxy._syncReferenceEditor(obj)
    return obj


# The proxy also migrates restored documents by adding only missing properties.
class _FCSolver:
    '''The persistent global EM FasterCap / FastCap settings object.'''
    def __init__(self, obj):
        self.Type = "FCSolver"
        self.Object = obj
        self._validatingReference = False
        self._ensureProperties(obj)
        obj.Proxy = self
        self._syncReferenceEditor(obj)

    def _ensureProperties(self, obj):
        from EM_FCDefeaturing import ensureDefeaturingProperties
        ensureDefeaturingProperties(obj, solver=True)
        if "Dimension" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyEnumeration", "Dimension", "EM",
                QT_TRANSLATE_NOOP("App::Property", "Capacitance model dimension"))
            obj.Dimension = EMFCSOLVER_DIMENSIONS
            obj.Dimension = EMFCSOLVER_DEFDIMENSION
        if "TargetSolver" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyEnumeration", "TargetSolver", "EM",
                QT_TRANSLATE_NOOP("App::Property", "Capacitance solver used for the simulation"))
            obj.TargetSolver = EMFCSOLVER_SOLVERS
            legacy_solver = str(getattr(obj, "Solver", EMFCSOLVER_DEFSOLVER))
            obj.TargetSolver = (legacy_solver if legacy_solver in EMFCSOLVER_SOLVERS
                                else EMFCSOLVER_DEFSOLVER)
        if "Units" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyEnumeration", "Units", "EM",
                QT_TRANSLATE_NOOP("App::Property", "Measurement units used by generated solver geometry"))
            obj.Units = EMFCSOLVER_UNITS
            obj.Units = EMFCSOLVER_DEFUNITS
        if "SpacePermittivity" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyFloatConstraint", "SpacePermittivity", "EM",
                QT_TRANSLATE_NOOP("App::Property", "Background relative permittivity of the model space"))
            obj.SpacePermittivity = (
                EMFCSOLVER_DEF_SPACE_PERMITTIVITY, 1e-12, 1e+12, 0.1)
        if "GeometryTolerance" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyFloatConstraint", "GeometryTolerance", "EM",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Numerical tolerance for transient geometry candidate filtering and classification"))
            obj.GeometryTolerance = (
                EMFCSOLVER_DEF_GEOMETRY_TOLERANCE,
                1e-12, 1e+6, EMFCSOLVER_DEF_GEOMETRY_TOLERANCE)
        if "MaxPanelSize" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyFloatConstraint", "MaxPanelSize", "FastCap",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Maximum FastCap panel edge dimension in the selected Units"))
            obj.MaxPanelSize = (
                EMFCSOLVER_DEF_MAX_PANEL_SIZE, 1e-12, 1e+12, 0.1)
        if "ReferenceConductor" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyLink", "ReferenceConductor", "2D",
                QT_TRANSLATE_NOOP("App::Property", "Zero-potential reference FCConductor for a 2D model"))

        self._ensureSolverProperties(obj)
        if "Solver" in obj.PropertiesList:
            # Preserve early development documents while exposing the renamed
            # TargetSolver property required by the persistent model.
            obj.setEditorMode("Solver", 2)

    # Table-driven creation keeps target-specific option metadata and defaults
    # together while preserving existing values during restoration.
    def _ensureSolverProperties(self, obj):
        definitions = [
            ("App::PropertyFloatConstraint", "AutoMaxError", "FasterCap",
             "Maximum relative error for FasterCap automatic refinement (-a)",
             (EMFCSOLVER_DEF_AUTO_MAX_ERR, 1e-12, 1.0, 1e-4)),
            ("App::PropertyFloatConstraint", "MeshRefinement", "FasterCap",
             "FasterCap mesh relative refinement value (-m)",
             (EMFCSOLVER_DEF_MESH_EPS, 1e-12, 1e+12, 0.01)),
            ("App::PropertyFloatConstraint", "MeshCurvature", "FasterCap",
             "FasterCap mesh curvature coefficient (-mc)",
             (EMFCSOLVER_DEF_MESH_CURV_COEFF, 0.0, 1e+12, 0.1)),
            ("App::PropertyFloatConstraint", "GmresTolerance", "FasterCap",
             "FasterCap GMRES iteration tolerance (-t)",
             (EMFCSOLVER_DEF_GMRES_TOL, 1e-12, 1.0, 1e-4)),
            ("App::PropertyIntegerConstraint", "ExpansionOrder", "FastCap",
             "FastCap multipole expansion order (-o)",
             (EMFCSOLVER_DEF_EXPANSION_ORDER, 1, 100, 1)),
            ("App::PropertyIntegerConstraint", "PartitioningDepth", "FastCap",
             "FastCap partitioning depth (-d); zero selects automatic mode",
             (EMFCSOLVER_DEF_PARTITIONING_DEPTH, 0, 100, 1)),
            ("App::PropertyFloatConstraint", "PermittivityFactor", "FastCap",
             "FastCap permittivity factor (-p)",
             (EMFCSOLVER_DEF_PERMITTIVITY_FACTOR, 0.0, 1e+12, 0.1)),
            ("App::PropertyFloatConstraint", "IterationTolerance", "FastCap",
             "FastCap iterative loop tolerance (-t)",
             (EMFCSOLVER_DEF_ITERATION_TOL, 1e-12, 1.0, 1e-4))]
        for property_type, name, group, description, initial in definitions:
            if name not in obj.PropertiesList:
                obj.addProperty(property_type, name, group,
                                QT_TRANSLATE_NOOP("App::Property", description))
                setattr(obj, name, initial)
        if "Folder" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyPath", "Folder", "EM",
                QT_TRANSLATE_NOOP("App::Property", "Folder for FasterCap or FastCap export files"))
            obj.Folder = FreeCAD.ConfigGet("UserHomePath")
        if "Filename" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyString", "Filename", "EM",
                QT_TRANSLATE_NOOP("App::Property", "FasterCap or FastCap list filename"))
            obj.Filename = EMFCSOLVER_DEF_FILENAME

    def _syncReferenceEditor(self, obj):
        if hasattr(obj, "setEditorMode") and hasattr(obj, "Dimension"):
            obj.setEditorMode("ReferenceConductor",
                              0 if obj.Dimension == "2D" else 2)

    def execute(self, obj):
        '''Keep editor state synchronized without processing geometry.'''
        self._syncReferenceEditor(obj)

    def onChanged(self, obj, prop):
        if not hasattr(self, "Object"):
            self.Object = obj
        if prop == "Dimension":
            self._syncReferenceEditor(obj)
        elif (prop == "ReferenceConductor" and
              not getattr(self, "_validatingReference", False)):
            reference = obj.ReferenceConductor
            if (reference is not None and
                    getattr(getattr(reference, "Proxy", None), "Type", None) !=
                    "FCConductor"):
                self._validatingReference = True
                obj.ReferenceConductor = None
                self._validatingReference = False
                FreeCAD.Console.PrintWarning(translate(
                    "EM", "ReferenceConductor must link to an FCConductor.\n"))

    def onDocumentRestored(self, obj):
        self.Object = obj
        self._validatingReference = False
        self._ensureProperties(obj)
        self._syncReferenceEditor(obj)

    def serialize(self, fid, headOrTail):
        '''Serialize the solver header for callers using the legacy interface.'''
        if headOrTail == "head":
            fid.write("* FasterCap / FastCap input file created using FreeCAD's ElectroMagnetic Workbench\n")
            fid.write("* Geometry units: " + self.Object.Units + "\n")
            fid.write("* Dimension: " + self.Object.Dimension + "\n\n")

    # Translate persistent properties only at the process boundary; the document
    # remains independent of executable availability and platform paths.
    def getCommandLineOptions(self):
        '''Return command-line settings represented by this object.'''
        if self.Object.TargetSolver == "FasterCap":
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

    def __setstate__(self, state):
        self.Type = state or "FCSolver"


# There is no solver geometry to render; this provider supplies persistence and
# the tree-view icon only.
class _ViewProviderFCSolver:
    '''View provider for the non-geometric global solver settings object.'''
    def __init__(self, vobj):
        vobj.Proxy = self
        self.Object = vobj.Object
        self._keepVisible(vobj)

    def attach(self, vobj):
        self.Object = vobj.Object
        self._keepVisible(vobj)

    def _keepVisible(self, vobj):
        # This settings object has no 3D representation.  Hide the inherited
        # visibility property and undo tree-shortcut toggles so its icon never
        # appears disabled even though there is no geometry to display.
        vobj.setEditorMode("Visibility", 2)
        if not vobj.Visibility:
            vobj.Visibility = True

    def updateData(self, fp, prop):
        return

    def onChanged(self, vp, prop):
        if prop == "Visibility" and not vp.Visibility:
            self._keepVisible(vp)

    def getIcon(self):
        return os.path.join(iconPath, 'EM_FCSolver.svg')

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class _CommandFCSolver:
    '''The EM FasterCap / FastCap solver command definition.'''
    def GetResources(self):
        return {
            'Pixmap': os.path.join(iconPath, 'EM_FCSolver.svg'),
            'MenuText': QT_TRANSLATE_NOOP(
                "EM_FCSolver", "FasterCap / FastCap Solver"),
            'Accel': "E, F",
            'ToolTip': QT_TRANSLATE_NOOP(
                "EM_FCSolver",
                "Creates the global FasterCap / FastCap Solver settings object")}

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        existing = getFCSolver()
        if existing is not None:
            FreeCAD.Console.PrintWarning(translate(
                "EM", "An FCSolver already exists in the active document.\n"))
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.Selection.addSelection(existing)
            return
        FreeCAD.ActiveDocument.openTransaction(translate("EM", "Create FCSolver"))
        FreeCADGui.addModule("EM")
        FreeCADGui.doCommand('obj=EM.makeFCSolver()')
        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()


if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_FCSolver', _CommandFCSolver())
