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


__title__="FreeCAD E.M. Workbench FasterCap / FastCap Dielectric Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
EMFCDIELECTRIC_DEF_INNER_PERMITTIVITY = 2.0
EMFCDIELECTRIC_ORIENTATIONS = ["Forward", "Reversed"]
EMFCDIELECTRIC_DEF_COLOR = (0.25, 0.55, 1.0)
EMFCDIELECTRIC_DEF_LINECOLOR = (0.05, 0.15, 0.35)
EMFCDIELECTRIC_DEF_TRANSPARENCY = 65
EMFCDIELECTRIC_DEF_ARROWCOLOR = (1.0, 0.2, 0.1)
EMFCDIELECTRIC_DEF_ARROWSCALE = 8.0
EMFCDIELECTRIC_MAX_ARROWS = 24

import math
import os

import FreeCAD

from EM_FCCommon import (getFCBaseFromSelection, getFCBaseObjects,
                         getFCObjectsFromSelection, hasFCObjectReference, hideFCBase,
                         makeFCBoundaryShape, mergeFCBase, normalizeFCBase)
from EM_FCSolver import getFCSpacePermittivity

if FreeCAD.GuiUp:
    import FreeCADGui
    from DraftTools import translate
    from pivy import coin
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


def makeFCDielectric(base=None, innerPermittivity=None,
                     outerPermittivity=None, orientation="Forward",
                     hideBase=True, name='FCDielectric'):
    '''Create one logical FasterCap / FastCap dielectric interface.

       A solid source defines a convenient closed interface through its
       boundary shell. Shells and open faces remain zero-thickness interfaces.
       Orientation arrows point toward OuterPermittivity; Reversed flips the
       overall direction relative to the current source-face normals.
    '''
    if FreeCAD.ActiveDocument is None:
        FreeCAD.Console.PrintWarning(
            translate("EM", "No active document available. Cannot create FCDielectric.\n"))
        return None

    if hasFCObjectReference(base):
        FreeCAD.Console.PrintWarning(translate(
            "EM", "FC objects cannot be nested and were ignored.\n"))
    normalized_base = normalizeFCBase(base)
    if not normalized_base:
        FreeCAD.Console.PrintWarning(translate(
            "EM", "Select at least one face, shell, solid, compsolid, or compound to create an FCDielectric.\n"))
        return None

    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    _FCDielectric(obj)
    if FreeCAD.GuiUp:
        _ViewProviderFCDielectric(obj.ViewObject)

    obj.Base = normalized_base
    obj.InnerPermittivity = (
        EMFCDIELECTRIC_DEF_INNER_PERMITTIVITY
        if innerPermittivity is None else innerPermittivity)
    obj.OuterPermittivity = (
        getFCSpacePermittivity(obj.Document)
        if outerPermittivity is None else outerPermittivity)
    if orientation in EMFCDIELECTRIC_ORIENTATIONS:
        obj.Orientation = orientation
    if FreeCAD.GuiUp and hideBase:
        hideFCBase(obj.Base)
    return obj


def makeFCDielectricFromSelection(selection=None, **kwargs):
    '''Create one FCDielectric from the complete extended GUI selection.'''
    if selection is None:
        selection = FreeCADGui.Selection.getSelectionEx() if FreeCAD.GuiUp else []
    return makeFCDielectric(getFCBaseFromSelection(selection), **kwargs)


def addToFCDielectric(dielectric, base, hideBase=True):
    """Append source references to an existing dielectric interface."""
    if isinstance(dielectric, str) and FreeCAD.ActiveDocument is not None:
        dielectric = FreeCAD.ActiveDocument.getObject(dielectric)
    if getattr(getattr(dielectric, "Proxy", None), "Type", None) != "FCDielectric":
        FreeCAD.Console.PrintWarning(translate(
            "EM", "Select exactly one existing FCDielectric to extend.\n"))
        return None
    if hasFCObjectReference(base):
        FreeCAD.Console.PrintWarning(translate(
            "EM", "FC objects cannot be nested and were ignored.\n"))
    additions = normalizeFCBase(base)
    if not additions:
        FreeCAD.Console.PrintWarning(translate(
            "EM", "Select additional faces, shells, solids, compsolids, or compounds.\n"))
        return None
    dielectric.Base = mergeFCBase(dielectric.Base, additions)
    if FreeCAD.GuiUp and hideBase:
        hideFCBase(additions)
    return dielectric


def addToFCDielectricFromSelection(dielectric, selection=None, **kwargs):
    """Append selected geometry to an existing FCDielectric."""
    if selection is None:
        selection = FreeCADGui.Selection.getSelectionEx() if FreeCAD.GuiUp else []
    return addToFCDielectric(
        dielectric, getFCBaseFromSelection(selection), **kwargs)


class _FCDielectric:
    '''The persistent EM FasterCap / FastCap dielectric-interface object.'''
    def __init__(self, obj):
        self.Type = "FCDielectric"
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
                    "Source solids, shells, or faces defining this dielectric interface"))
        if "InnerPermittivity" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyFloatConstraint", "InnerPermittivity",
                "FasterCap",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Relative permittivity on the side opposite the orientation arrows"))
            obj.InnerPermittivity = (
                EMFCDIELECTRIC_DEF_INNER_PERMITTIVITY,
                1e-12, 1e+12, 0.1)
        if "OuterPermittivity" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyFloatConstraint", "OuterPermittivity",
                "FasterCap",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Default relative permittivity on the arrow side; resolved interfaces may override it"))
            obj.OuterPermittivity = (1.0, 1e-12, 1e+12, 0.1)
        if "Orientation" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyEnumeration", "Orientation", "FasterCap",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Forward arrows follow source-face normals; Reversed arrows point oppositely"))
            obj.Orientation = EMFCDIELECTRIC_ORIENTATIONS
            obj.Orientation = "Forward"

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
            "EM", "Removed nested FC object references from FCDielectric Base.\n"))

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
        self.Type = state or "FCDielectric"


class _ViewProviderFCDielectric:
    '''View provider with selection-only OuterPermittivity direction arrows.'''
    def __init__(self, vobj):
        vobj.ShapeColor = EMFCDIELECTRIC_DEF_COLOR
        vobj.LineColor = EMFCDIELECTRIC_DEF_LINECOLOR
        vobj.Transparency = EMFCDIELECTRIC_DEF_TRANSPARENCY
        self._ensureProperties(vobj)
        vobj.Proxy = self
        self.VObject = vobj
        self.Object = vobj.Object

    def _ensureProperties(self, vobj):
        if "ArrowColor" not in vobj.PropertiesList:
            vobj.addProperty(
                "App::PropertyColor", "ArrowColor", "Orientation",
                QT_TRANSLATE_NOOP(
                    "App::Property", "Color of selected-interface orientation arrows"))
            vobj.ArrowColor = EMFCDIELECTRIC_DEF_ARROWCOLOR
        if "ArrowScale" not in vobj.PropertiesList:
            vobj.addProperty(
                "App::PropertyFloatConstraint", "ArrowScale", "Orientation",
                QT_TRANSLATE_NOOP(
                    "App::Property", "Arrow length as a percentage of the interface bounding box"))
            vobj.ArrowScale = (
                EMFCDIELECTRIC_DEF_ARROWSCALE, 0.1, 100.0, 0.5)

    def attach(self, vobj):
        self.VObject = vobj
        self.Object = vobj.Object
        self._ensureProperties(vobj)

        # arrows are transient Coin lines and never enter the FreeCAD document
        self.arrowSwitch = coin.SoSwitch()
        self.arrowCoordinates = coin.SoCoordinate3()
        self.arrowLines = coin.SoLineSet()
        self.arrowStyle = coin.SoDrawStyle()
        self.arrowStyle.lineWidth = 2.0
        self.arrowColor = coin.SoBaseColor()
        separator = coin.SoSeparator()
        separator.addChild(self.arrowStyle)
        separator.addChild(self.arrowColor)
        separator.addChild(self.arrowCoordinates)
        separator.addChild(self.arrowLines)
        self.arrowSwitch.addChild(separator)
        self.arrowSwitch.whichChild = coin.SO_SWITCH_NONE
        vobj.RootNode.addChild(self.arrowSwitch)
        self._observerRegistered = True
        FreeCADGui.Selection.addObserver(self)
        self._updateArrowColor()
        self._rebuildArrows()

    def _updateArrowColor(self):
        color = self.VObject.ArrowColor
        self.arrowColor.rgb.setValue(color[0], color[1], color[2])

    def _sampleFaces(self):
        faces = list(getattr(self.Object.Shape, "Faces", []))
        if len(faces) <= EMFCDIELECTRIC_MAX_ARROWS:
            return faces
        step = float(len(faces)) / EMFCDIELECTRIC_MAX_ARROWS
        return [faces[int(index * step)]
                for index in range(EMFCDIELECTRIC_MAX_ARROWS)]

    def _rebuildArrows(self):
        if not hasattr(self, "arrowCoordinates"):
            return
        points = []
        counts = []
        shape = getattr(self.Object, "Shape", None)
        bbox = getattr(shape, "BoundBox", None)
        if bbox is not None:
            diagonal = math.sqrt(
                bbox.XLength * bbox.XLength +
                bbox.YLength * bbox.YLength +
                bbox.ZLength * bbox.ZLength)
        else:
            diagonal = 0.0
        length = diagonal * float(self.VObject.ArrowScale) / 100.0
        if length <= 1e-12:
            length = 1.0

        reverse = str(self.Object.Orientation) == "Reversed"
        # Phase 1 previews the copied BRep normals. A later geometry stage can
        # normalize connected faces before applying this overall direction.
        for face in self._sampleFaces():
            try:
                umin, umax, vmin, vmax = face.ParameterRange
                normal = face.normalAt(
                    (umin + umax) * 0.5, (vmin + vmax) * 0.5)
                if normal.Length <= 1e-12:
                    continue
                normal.normalize()
                if reverse:
                    normal = FreeCAD.Vector(-normal.x, -normal.y, -normal.z)
                center = face.CenterOfMass
                start = center + normal * (length * 0.05)
                tip = center + normal * length
                side = normal.cross(FreeCAD.Vector(0.0, 0.0, 1.0))
                if side.Length <= 1e-9:
                    side = normal.cross(FreeCAD.Vector(1.0, 0.0, 0.0))
                side.normalize()
                head = tip - normal * (length * 0.28)
                wing = side * (length * 0.16)
                wing_one = head + wing
                wing_two = head - wing
                points.extend([
                    (start.x, start.y, start.z), (tip.x, tip.y, tip.z),
                    (tip.x, tip.y, tip.z),
                    (wing_one.x, wing_one.y, wing_one.z),
                    (tip.x, tip.y, tip.z),
                    (wing_two.x, wing_two.y, wing_two.z)])
                counts.extend([2, 2, 2])
            except (AttributeError, RuntimeError, ValueError):
                continue

        self.arrowCoordinates.point.setNum(0)
        self.arrowLines.numVertices.setNum(0)
        if points:
            self.arrowCoordinates.point.setValues(0, len(points), points)
            self.arrowLines.numVertices.setValues(0, len(counts), counts)

    def _showArrows(self, show):
        if hasattr(self, "arrowSwitch"):
            self.arrowSwitch.whichChild = (
                coin.SO_SWITCH_ALL if show else coin.SO_SWITCH_NONE)

    def _syncSelection(self):
        try:
            selected = FreeCADGui.Selection.getSelection(
                self.Object.Document.Name)
            self._showArrows(self.Object in selected)
        except (AttributeError, RuntimeError):
            self._showArrows(False)

    # FreeCAD selection-observer callbacks keep arrows visible only while the
    # logical dielectric object is selected.
    def addSelection(self, document, obj, subelement, position):
        if (document == self.Object.Document.Name and
                obj == self.Object.Name):
            self._showArrows(True)

    def removeSelection(self, document, obj, subelement):
        if (document == self.Object.Document.Name and
                obj == self.Object.Name):
            self._syncSelection()

    def setSelection(self, document):
        if document == self.Object.Document.Name:
            self._syncSelection()

    def clearSelection(self, document):
        if not document or document == self.Object.Document.Name:
            self._showArrows(False)

    def updateData(self, fp, prop):
        if prop in ("Shape", "Orientation"):
            self._rebuildArrows()

    def onChanged(self, vp, prop):
        if prop == "ArrowColor" and hasattr(self, "arrowColor"):
            self._updateArrowColor()
        elif prop == "ArrowScale":
            self._rebuildArrows()

    def claimChildren(self):
        return getFCBaseObjects(self.Object.Base) if hasattr(self, "Object") else []

    def getDefaultDisplayMode(self):
        return "Flat Lines"

    def getIcon(self):
        return os.path.join(iconPath, 'EM_FCDielectric.svg')

    def onDelete(self, vobj, subelements):
        if getattr(self, "_observerRegistered", False):
            FreeCADGui.Selection.removeObserver(self)
            self._observerRegistered = False
        return True

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class _CommandFCDielectric:
    '''The EM FasterCap / FastCap dielectric command definition.'''
    def GetResources(self):
        return {
            'Pixmap': os.path.join(iconPath, 'EM_FCDielectric.svg'),
            'MenuText': QT_TRANSLATE_NOOP("EM_FCDielectric", "FCDielectric"),
            'Accel': "E, D",
            'ToolTip': QT_TRANSLATE_NOOP(
                "EM_FCDielectric",
                "Creates or extends one dielectric interface from selected geometry")}

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        selection = FreeCADGui.Selection.getSelectionEx()
        targets = getFCObjectsFromSelection(selection, "FCDielectric")
        if len(targets) > 1:
            FreeCAD.Console.PrintWarning(translate(
                "EM", "Select only one FCDielectric to extend.\n"))
            return
        if not getFCBaseFromSelection(selection):
            FreeCAD.Console.PrintWarning(translate(
                "EM", "Select at least one face, shell, solid, compsolid, or compound.\n"))
            return

        extending = bool(targets)
        transaction = "Add FCDielectric geometry" if extending else "Create FCDielectric"
        FreeCAD.ActiveDocument.openTransaction(translate("EM", transaction))
        FreeCADGui.addModule("EM")
        if extending:
            FreeCADGui.doCommand(
                "obj=EM.addToFCDielectricFromSelection(%r)" % targets[0].Name)
        else:
            FreeCADGui.doCommand(
                "obj=EM.makeFCDielectricFromSelection(FreeCADGui.Selection.getSelectionEx())")
        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()
        if extending:
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.Selection.addSelection(targets[0])


if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_FCDielectric', _CommandFCDielectric())
