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

import os

import FreeCAD

from EM_FCCommon import (getFCBaseFromSelection, getFCBaseObjects,
                         getFCObjectsFromSelection, hasFCObjectReference, hideFCBase,
                         makeFCBoundaryShape, mergeFCBase, normalizeFCBase)
from EM_FCSolver import getFCSpacePermittivity

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


def makeFCConductor(base=None, defaultPermittivity=None,
                    hideBase=True, name='FCConductor'):
    '''Create one logical FasterCap / FastCap equipotential conductor.

       'base' is a list of source objects/subobjects suitable for an
            App::PropertyLinkSubList. Disconnected or touching sources remain
            parts of the same logical conductor.
       'defaultPermittivity' is the fallback surrounding relative
            permittivity. If omitted, it is copied from the document FCSolver.
       'hideBase' hides referenced CAD objects after creation without changing
            their geometry or display properties.
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
    if FreeCAD.GuiUp and hideBase:
        hideFCBase(obj.Base)
    return obj


def makeFCConductorFromSelection(selection=None, **kwargs):
    '''Create one FCConductor from the complete extended GUI selection.'''
    if selection is None:
        selection = FreeCADGui.Selection.getSelectionEx() if FreeCAD.GuiUp else []
    return makeFCConductor(getFCBaseFromSelection(selection), **kwargs)


def addToFCConductor(conductor, base, hideBase=True):
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
    conductor.Base = mergeFCBase(conductor.Base, additions)
    if FreeCAD.GuiUp and hideBase:
        hideFCBase(additions)
    return conductor


def addToFCConductorFromSelection(conductor, selection=None, **kwargs):
    """Append selected geometry to an existing FCConductor."""
    if selection is None:
        selection = FreeCADGui.Selection.getSelectionEx() if FreeCAD.GuiUp else []
    return addToFCConductor(
        conductor, getFCBaseFromSelection(selection), **kwargs)


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
        '''Refresh only the lightweight boundary display representation.'''
        self._removeNestedBase(obj)
        obj.Shape = makeFCBoundaryShape(obj.Base)

    def onChanged(self, obj, prop):
        if not hasattr(self, "Object"):
            self.Object = obj
        if prop == "Base":
            self._removeNestedBase(obj)

    def onDocumentRestored(self, obj):
        self.Object = obj
        self._guardingBase = False
        self._ensureProperties(obj)
        self._removeNestedBase(obj)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        self.Type = state or "FCConductor"


class _ViewProviderFCConductor:
    '''View provider for an independently styled conductor boundary.'''
    def __init__(self, vobj):
        vobj.ShapeColor = EMFCCONDUCTOR_DEF_COLOR
        vobj.LineColor = EMFCCONDUCTOR_DEF_LINECOLOR
        vobj.Proxy = self
        self.Object = vobj.Object

    def attach(self, vobj):
        self.Object = vobj.Object

    def updateData(self, fp, prop):
        return

    def getDefaultDisplayMode(self):
        return "Flat Lines"

    def onChanged(self, vp, prop):
        return

    def claimChildren(self):
        return getFCBaseObjects(self.Object.Base) if hasattr(self, "Object") else []

    def getIcon(self):
        return os.path.join(iconPath, 'EM_FCConductor.svg')

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


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
