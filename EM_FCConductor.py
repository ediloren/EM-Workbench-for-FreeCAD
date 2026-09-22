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


__title__="FreeCAD E.M. Workbench FasterCap / FastCap Conductor Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
EMFCCONDUCTOR_DEF_COLOR = (1.0, 0.67, 0.0)
EMFCCONDUCTOR_DEF_LINECOLOR = (0.2, 0.12, 0.0)
EMFCCONDUCTOR_DEF_CURVATURE_TOLERANCE = 0.01

import os

import FreeCAD
import Part

# Architecture notes:
# - This module owns the persistent wrapper for one logical equipotential
#   conductor; it does not own or copy the linked source CAD objects.
# - Before panelization the live, visible Base objects provide all CAD display;
#   the wrapper Shape stays empty and its tree children expose those sources.
# - Oriented, split solver faces exist only in the transient geometry model.
# - Panelization is explicit, never part of normal document recomputation.
# - GUI Coin data belongs to the view provider and is rebuilt after restore.

from EM_FCCommon import (getFCBaseFromSelection, getFCBaseObjects,
                         getFCBaseOwners, getFCObjectsFromSelection,
                         hasFCObjectReference, mergeFCBase, normalizeFCBase,
                         syncFCBaseVisibility)
from EM_FCSolver import getFCSolver, getFCSpacePermittivity

if FreeCAD.GuiUp:
    import FreeCADGui
    from DraftTools import translate
    from PySide.QtCore import QT_TRANSLATE_NOOP
    from EM_FCPreview import (
        attachFCPanelPreview, ensureFCPreviewProperties,
        onFCPanelPreviewChanged, setFCPanelizationPreview)
else:
    # \cond
    def translate(ctxt, txt):
        return txt
    def QT_TRANSLATE_NOOP(ctxt, txt):
        return txt
    # \endcond

__dir__ = os.path.dirname(__file__)
iconPath = os.path.join(__dir__, 'Resources')


# Create the wrapper only after validating all references, avoiding a partially
# initialized document object when selection contains no usable boundary.
def makeFCConductor(base=None, defaultPermittivity=None,
                    hideBase=False, name='FCConductor'):
    '''Create one logical FasterCap / FastCap equipotential conductor.

       'base' is a list of source objects/subobjects suitable for an
            App::PropertyLinkSubList. Disconnected or touching sources remain
            parts of the same logical conductor.
       'defaultPermittivity' is the fallback surrounding relative
            permittivity. If omitted, it is copied from the document FCSolver.
       'hideBase' is retained for call compatibility but ignored: live Base
            objects remain visible until an explicit panelization is created.
    '''
    if FreeCAD.ActiveDocument is None:
        FreeCAD.Console.PrintWarning(
            translate("EM", "No active document available. Cannot create FCConductor.\n"))
        return None

    if hasFCObjectReference(base):
        FreeCAD.Console.PrintWarning(translate(
            "EM", "FC objects cannot be nested and were ignored.\n"))
    normalized_base = normalizeFCBase(base)
    if not normalized_base:
        FreeCAD.Console.PrintWarning(translate(
            "EM", "Select at least one face, shell, solid, compsolid, or compound to create an FCConductor.\n"))
        return None

    owners = getFCBaseOwners(
        FreeCAD.ActiveDocument, normalized_base, "FCConductor")
    if owners:
        owner_names = ", ".join(
            getattr(owner, "Name", "FCConductor") for owner in owners)
        FreeCAD.Console.PrintWarning(translate(
            "EM",
            "Selected geometry is already assigned to %s; no duplicate "
            "FCConductor was created. Select that conductor together with "
            "new geometry to extend it.\n") % owner_names)
        return None

    # A new FC object needs document-wide settings.  Create the default
    # FCSolver in the same GUI transaction when none exists yet.
    getFCSolver(FreeCAD.ActiveDocument, createIfNotExisting=True)
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    _FCConductor(obj)
    if FreeCAD.GuiUp:
        _ViewProviderFCConductor(obj.ViewObject)

    obj.Base = normalized_base
    permittivity = (getFCSpacePermittivity(obj.Document)
                    if defaultPermittivity is None
                    else defaultPermittivity)
    obj.DefaultPermittivity = permittivity
    if FreeCAD.GuiUp:
        syncFCBaseVisibility(obj)
    return obj


def makeFCConductorFromSelection(selection=None, **kwargs):
    '''Create one FCConductor from the complete extended GUI selection.'''
    if selection is None:
        selection = FreeCADGui.Selection.getSelectionEx() if FreeCAD.GuiUp else []
    return makeFCConductor(getFCBaseFromSelection(selection), **kwargs)


# Appending merges subelement names per source and treats a whole-object link as
# superseding individual faces from that same object.
def addToFCConductor(conductor, base, hideBase=False):
    """Append source references to an existing logical conductor."""
    if isinstance(conductor, str) and FreeCAD.ActiveDocument is not None:
        conductor = FreeCAD.ActiveDocument.getObject(conductor)
    if getattr(getattr(conductor, "Proxy", None), "Type", None) != "FCConductor":
        FreeCAD.Console.PrintWarning(translate(
            "EM", "Select exactly one existing FCConductor to extend.\n"))
        return None
    if hasFCObjectReference(base):
        FreeCAD.Console.PrintWarning(translate(
            "EM", "FC objects cannot be nested and were ignored.\n"))
    additions = normalizeFCBase(base)
    if not additions:
        FreeCAD.Console.PrintWarning(translate(
            "EM", "Select additional faces, shells, solids, compsolids, or compounds.\n"))
        return None
    owners = getFCBaseOwners(
        conductor.Document, additions, "FCConductor", exclude=conductor)
    if owners:
        owner_names = ", ".join(
            getattr(owner, "Name", "FCConductor") for owner in owners)
        FreeCAD.Console.PrintWarning(translate(
            "EM",
            "Selected geometry is already assigned to %s and cannot also be "
            "added to this conductor.\n") % owner_names)
        return None
    # Before panelization additions follow the FC object's visibility.  An
    # existing panel snapshot and its independently visible sources stay fixed.
    conductor.Base = mergeFCBase(conductor.Base, additions)
    if FreeCAD.GuiUp and not conductor.Panelized:
        syncFCBaseVisibility(conductor)
    return conductor


def addToFCConductorFromSelection(conductor, selection=None, **kwargs):
    """Append selected geometry to an existing FCConductor."""
    if selection is None:
        selection = FreeCADGui.Selection.getSelectionEx() if FreeCAD.GuiUp else []
    return addToFCConductor(
        conductor, getFCBaseFromSelection(selection), **kwargs)


# The proxy owns persistent properties and the cheap recompute contract.
class _FCConductor:
    '''The persistent EM FasterCap / FastCap conductor object.'''
    def __init__(self, obj):
        self.Type = "FCConductor"
        self.Object = obj
        self._guardingBase = False
        self._ensureProperties(obj)
        obj.Proxy = self

    def _ensureProperties(self, obj):
        if "Base" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyLinkSubList", "Base", "EM",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Source solids, shells, faces, or open surfaces forming one equipotential conductor"))
        if "DefaultPermittivity" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyFloatConstraint", "DefaultPermittivity",
                "FasterCap",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Fallback surrounding relative permittivity; generated boundary portions may override it"))
            obj.DefaultPermittivity = (1.0, 1e-12, 1e+12, 0.1)
        if "PanelCurvatureTolerance" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyFloatConstraint", "PanelCurvatureTolerance",
                "Panelization",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Approximate maximum relative curved-surface panel "
                    "deviation (sagitta divided by minimum principal radius)"))
            obj.PanelCurvatureTolerance = (
                EMFCCONDUCTOR_DEF_CURVATURE_TOLERANCE,
                1e-6, 0.5, 0.001)
        for name, description in (
                ("Panelized", "Whether a current transient panelization exists"),
                ("PanelCount", "Number of generated transient panels"),
                ("PanelErrorCount", "Number of panelization errors")):
            if name not in obj.PropertiesList:
                property_type = ("App::PropertyBool" if name == "Panelized"
                                 else "App::PropertyInteger")
                obj.addProperty(
                    property_type, name, "Panelization",
                    QT_TRANSLATE_NOOP("App::Property", description))
                setattr(obj, name, False if name == "Panelized" else 0)
            obj.setEditorMode(name, 1)
            if hasattr(obj, "setPropertyStatus"):
                try:
                    obj.setPropertyStatus(name, "Output")
                    obj.setPropertyStatus(name, "NoRecompute")
                except (AttributeError, RuntimeError, TypeError):
                    pass

    def _removeNestedBase(self, obj):
        if (getattr(self, "_guardingBase", False) or
                not hasFCObjectReference(obj.Base)):
            return
        self._guardingBase = True
        try:
            obj.Base = normalizeFCBase(obj.Base)
        finally:
            self._guardingBase = False
        FreeCAD.Console.PrintWarning(translate(
            "EM", "Removed nested FC object references from FCConductor Base.\n"))

    def execute(self, obj):
        """Keep solver extraction and display copies out of recomputation."""
        self._removeNestedBase(obj)
        # Part::FeaturePython supplies the standard view-provider root needed
        # by the Coin panel preview, but owns no duplicate Base topology.
        obj.Shape = Part.Shape()

    def onChanged(self, obj, prop):
        if not hasattr(self, "Object"):
            self.Object = obj
        if prop == "Base":
            self._removeNestedBase(obj)
            if FreeCAD.GuiUp and not getattr(obj, "Panelized", False):
                syncFCBaseVisibility(obj)

    def onDocumentRestored(self, obj):
        self.Object = obj
        self._guardingBase = False
        self._ensureProperties(obj)
        obj.Panelized = False
        obj.PanelCount = 0
        obj.PanelErrorCount = 0
        self._removeNestedBase(obj)
        obj.Shape = Part.Shape()
        if FreeCAD.GuiUp:
            # Generated panels are transient and are not restored from the
            # document, so sources resume following the FC object's visibility.
            syncFCBaseVisibility(obj)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        self.Type = state or "FCConductor"


# The view provider owns only display state, child disclosure, and panel preview.
class _ViewProviderFCConductor:
    """View provider for child disclosure and frozen panel snapshots."""
    def __init__(self, vobj):
        vobj.ShapeColor = EMFCCONDUCTOR_DEF_COLOR
        vobj.LineColor = EMFCCONDUCTOR_DEF_LINECOLOR
        ensureFCPreviewProperties(vobj, dielectric=False)
        vobj.Proxy = self
        self.VObject = vobj
        self.Object = vobj.Object

    def attach(self, vobj):
        self.VObject = vobj
        self.Object = vobj.Object
        ensureFCPreviewProperties(vobj, dielectric=False)
        attachFCPanelPreview(self, vobj, dielectric=False)

    def setPanelizationPreview(self, panelization):
        setFCPanelizationPreview(self, panelization)

    def updateData(self, fp, prop):
        return

    def getDefaultDisplayMode(self):
        return "Flat Lines"

    def onChanged(self, vp, prop):
        if (prop == "Visibility" and
                not getattr(self.Object, "Panelized", False)):
            syncFCBaseVisibility(self.Object)
        onFCPanelPreviewChanged(self, prop)

    def claimChildren(self):
        return getFCBaseObjects(self.Object.Base) if hasattr(self, "Object") else []

    def getIcon(self):
        return os.path.join(iconPath, 'EM_FCConductor.svg')

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


# The command appends when exactly one conductor is selected; otherwise it
# creates a new conductor from all usable extended-selection entries.
class _CommandFCConductor:
    '''The EM FasterCap / FastCap conductor command definition.'''
    def GetResources(self):
        return {
            'Pixmap': os.path.join(iconPath, 'EM_FCConductor.svg'),
            'MenuText': QT_TRANSLATE_NOOP("EM_FCConductor", "FCConductor"),
            'Accel': "E, C",
            'ToolTip': QT_TRANSLATE_NOOP(
                "EM_FCConductor",
                "Creates or extends one equipotential FCConductor from selected geometry")}

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        selection = FreeCADGui.Selection.getSelectionEx()
        targets = getFCObjectsFromSelection(selection, "FCConductor")
        if len(targets) > 1:
            FreeCAD.Console.PrintWarning(translate(
                "EM", "Select only one FCConductor to extend.\n"))
            return
        if not getFCBaseFromSelection(selection):
            FreeCAD.Console.PrintWarning(translate(
                "EM", "Select at least one face, shell, solid, compsolid, or compound.\n"))
            return

        extending = bool(targets)
        transaction = "Add FCConductor geometry" if extending else "Create FCConductor"
        FreeCAD.ActiveDocument.openTransaction(translate("EM", transaction))
        FreeCADGui.addModule("EM")
        if extending:
            FreeCADGui.doCommand(
                "obj=EM.addToFCConductorFromSelection(%r)" % targets[0].Name)
        else:
            FreeCADGui.doCommand(
                "obj=EM.makeFCConductorFromSelection(FreeCADGui.Selection.getSelectionEx())")
        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()
        if extending:
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.Selection.addSelection(targets[0])


if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_FCConductor', _CommandFCConductor())
