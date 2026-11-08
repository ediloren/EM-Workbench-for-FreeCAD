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


__title__="FreeCAD E.M. Workbench FasterCap / FastCap Coin scene-graph preview helpers"
__author__ = "FastFieldSolvers - Enrico Di Lorenzo"
__url__ = "http://www.fastfieldsolvers.com"


"""Coin scene-graph preview helpers for transient FC solver panels."""

# Preview design notes:
# - Valid and problematic panels occupy separate branches for independent color.
# - Each object shares coordinate and index arrays instead of creating a Coin
#   node or persistent FreeCAD object per panel.
# - Dielectric arrows derive their direction from the exact reference points
#   used by export, while their display length follows the normal arrow scale.
# - Visibility combines object visibility, user switches, and cached-data state.
# - Runtime scene nodes are reconstructed by attach and are never serialized.

import math
import FreeCAD

if FreeCAD.GuiUp:
    from pivy import coin
else:
    coin = None


FCPREVIEW_BAD_COLOR = (1.0, 0.0, 0.0)
FCPREVIEW_DIELECTRIC_ARROW_COLOR = (1.0, 0.2, 0.1)

# Reference arrows identify the resolved OUTPERM side without obscuring a dense
# tessellation. Their count remains proportional to the panel count.
FCPREVIEW_DIELECTRIC_REFERENCE_FRACTION = 0.20


# Both construction and view attachment call this helper, so property creation
# is idempotent without requiring duplicate initialization paths.
def ensureFCPreviewProperties(vobj, dielectric=False):
    """Add individually toggleable preview properties to an FC view object."""
    if "ShowPanelization" not in vobj.PropertiesList:
        vobj.addProperty(
            "App::PropertyBool", "ShowPanelization", "Panelization",
            "Show the last explicitly generated transient panelization")
        vobj.ShowPanelization = True
    if "BadPanelColor" not in vobj.PropertiesList:
        vobj.addProperty(
            "App::PropertyColor", "BadPanelColor", "Panelization",
            "Color of panels associated with validation errors or warnings")
        vobj.BadPanelColor = FCPREVIEW_BAD_COLOR
    if dielectric and "ShowReferencePoints" not in vobj.PropertiesList:
        vobj.addProperty(
            "App::PropertyBool", "ShowReferencePoints", "Panelization",
            "Show sampled OUTPERM direction arrows on the panelization")
        vobj.ShowReferencePoints = True


def _material(color, transparency=0.15):
    material = coin.SoMaterial()
    material.diffuseColor.setValue(color[0], color[1], color[2])
    material.transparency.setValue(transparency)
    return material


# A branch shares coordinates between filled faces and boundary lines while
# retaining the standard Part face/edge colors as independent Coin state.
def _geometry_node(face_color, line_color, transparency):
    separator = coin.SoSeparator()
    face_material = _material(face_color, transparency)
    line_material = _material(line_color, transparency)
    coordinates = coin.SoCoordinate3()
    faces = coin.SoIndexedFaceSet()
    lines = coin.SoIndexedLineSet()
    style = coin.SoDrawStyle()
    style.lineWidth = 1.5
    separator.addChild(face_material)
    separator.addChild(coordinates)
    separator.addChild(faces)
    separator.addChild(line_material)
    separator.addChild(style)
    separator.addChild(lines)
    return {
        "separator": separator, "face_material": face_material,
        "line_material": line_material,
        "coordinates": coordinates, "faces": faces, "lines": lines}


def _part_transparency(vobj):
    """Convert FreeCAD's integer 0..100 transparency to Coin's 0..1."""
    return max(0.0, min(1.0, float(vobj.Transparency) / 100.0))


def _shape_appearance(vobj):
    """Return the face color and transparency edited by Shape Appearance."""
    color = tuple(vobj.ShapeColor)
    transparency = _part_transparency(vobj)
    try:
        appearances = list(vobj.ShapeAppearance)
        if appearances:
            material = appearances[0]
            color = tuple(material.DiffuseColor)
            transparency = max(
                0.0, min(1.0, float(material.Transparency)))
    except (AttributeError, TypeError, ValueError):
        # Older Part view providers expose only the scalar legacy properties.
        pass
    return color, transparency


def _line_color(vobj):
    """Read the line appearance used by current and older Part view providers."""
    try:
        return tuple(vobj.LineMaterial.DiffuseColor)
    except (AttributeError, TypeError, ValueError):
        return tuple(vobj.LineColor)


def syncFCPreviewDimension(vobj, dimension=None):
    """Use body colors for default 2D lines, retaining custom line colors."""
    obj = getattr(vobj, "Object", None)
    kind = getattr(getattr(obj, "Proxy", None), "Type", None)
    if kind not in ("FCConductor", "FCDielectric"):
        return
    if dimension is None:
        from .EM_FCSolver import getFCSolver
        dimension = getattr(getFCSolver(obj.Document), "Dimension", "3D")
    if kind == "FCConductor":
        from .EM_FCConductor import EMFCCONDUCTOR_DEF_COLOR as body
        from .EM_FCConductor import EMFCCONDUCTOR_DEF_LINECOLOR as edge
    else:
        from .EM_FCDielectric import EMFCDIELECTRIC_DEF_COLOR as body
        from .EM_FCDielectric import EMFCDIELECTRIC_DEF_LINECOLOR as edge
    previous, desired = (edge, body) if dimension == "2D" else (body, edge)
    # Translate only a recognized default, not an arbitrary user-selected color.
    # In 2D the line represents the body; in 3D it is the darker panel outline.
    if all(abs(a-b) < 1e-6 for a, b in zip(_line_color(vobj)[:3], previous)):
        vobj.LineColor = desired


# Attach two panel branches and, for dielectrics, one reference-marker branch to
# the standard root supplied by the FeaturePython view provider.
def attachFCPanelPreview(view_provider, vobj, dielectric=False):
    """Attach empty transient panel/reference nodes below an FC view root."""
    if coin is None:
        return
    ensureFCPreviewProperties(vobj, dielectric)
    syncFCPreviewDimension(vobj)
    panel_switch = coin.SoSwitch()
    face_color, transparency = _shape_appearance(vobj)
    good = _geometry_node(
        face_color, _line_color(vobj), transparency)
    bad_color = tuple(vobj.BadPanelColor)
    # Keep diagnostic geometry in its own branch so editing the object's
    # ordinary color does not replace the error highlight color.
    bad = _geometry_node(bad_color, bad_color, transparency)
    panel_switch.addChild(good["separator"])
    panel_switch.addChild(bad["separator"])
    panel_switch.whichChild = coin.SO_SWITCH_NONE
    vobj.RootNode.addChild(panel_switch)

    references_switch = None
    reference_coordinates = None
    reference_lines = None
    reference_material = None
    if dielectric:
        references_switch = coin.SoSwitch()
        separator = coin.SoSeparator()
        reference_material = _material(
            tuple(getattr(vobj, "ArrowColor",
                          FCPREVIEW_DIELECTRIC_ARROW_COLOR)), 0.0)
        style = coin.SoDrawStyle()
        style.lineWidth = 2.0
        reference_coordinates = coin.SoCoordinate3()
        reference_lines = coin.SoLineSet()
        separator.addChild(reference_material)
        separator.addChild(style)
        separator.addChild(reference_coordinates)
        separator.addChild(reference_lines)
        references_switch.addChild(separator)
        references_switch.whichChild = coin.SO_SWITCH_NONE
        vobj.RootNode.addChild(references_switch)

    view_provider._fcPanelPreview = {
        "switch": panel_switch, "good": good, "bad": bad,
        "references_switch": references_switch,
        "reference_coordinates": reference_coordinates,
        "reference_lines": reference_lines,
        "reference_material": reference_material,
        "panelization": None, "has_data": False,
        "dielectric": dielectric, "selected": False}


def _set_color(material, color):
    if material is not None:
        material.diffuseColor.setValue(color[0], color[1], color[2])


def _set_transparency(material, transparency):
    if material is not None:
        material.transparency.setValue(transparency)


# Rebuild compact indexed geometry: -1 terminates each independent face or line
# in Coin arrays, allowing triangles and quads to coexist in one node.
def _set_panel_geometry(node, panels):
    points = []
    face_indices = []
    line_indices = []
    for panel in panels:
        offset = len(points)
        points.extend(panel.points)
        indices = list(range(offset, offset + len(panel.points))) + [-1]
        if panel.kind == "S":
            # A segment is already the complete element, not a degenerate face.
            line_indices.extend(indices)
        else:
            face_indices.extend(indices)
            line_indices.extend(
                list(range(offset, offset + len(panel.points))) +
                [offset, -1])
    node["coordinates"].point.setNum(0)
    node["faces"].coordIndex.setNum(0)
    node["lines"].coordIndex.setNum(0)
    if points:
        node["coordinates"].point.setValues(0, len(points), points)
    if face_indices:
        node["faces"].coordIndex.setValues(
            0, len(face_indices), face_indices)
    if line_indices:
        node["lines"].coordIndex.setValues(
            0, len(line_indices), line_indices)


def _panel_center(panel):
    count = float(len(panel.points))
    return tuple(sum(point[axis] for point in panel.points) / count
                 for axis in range(3))


def _panel_spatial_key(panel, bounds):
    """Return a Morton key for the panel centre within the object bounds."""
    center = _panel_center(panel)
    coordinates = []
    for axis in range(3):
        minimum, maximum = bounds[axis]
        span = maximum - minimum
        normalized = 0.5 if span <= 1.0e-15 else (center[axis] - minimum) / span
        coordinates.append(int(max(0.0, min(1.0, normalized)) * 1023.0))
    key = 0
    for bit in range(10):
        for axis in range(3):
            key |= ((coordinates[axis] >> bit) & 1) << (bit * 3 + axis)
    return key


def _reference_arrow_panels(panels):
    """Choose an evenly distributed representative set of dielectric panels."""
    eligible = [panel for panel in panels if panel.reference_point is not None]
    if not eligible:
        return []
    if all(panel.kind == "S" for panel in eligible):
        # 2D contours are normally small enough to show every material-side aid.
        return eligible
    centers = [_panel_center(panel) for panel in eligible]
    minima = tuple(min(center[axis] for center in centers) for axis in range(3))
    maxima = tuple(max(center[axis] for center in centers) for axis in range(3))
    bounds = tuple(zip(minima, maxima))
    # Use a panel-count-relative sample with no fixed ceiling. Morton order is
    # a compact spatial ordering; equally spaced positions in it spread arrows
    # across the surface without the quadratic cost of farthest-point sampling.
    count = max(1, int(math.ceil(
        len(eligible) * FCPREVIEW_DIELECTRIC_REFERENCE_FRACTION)))

    ordered = sorted(
        enumerate(eligible),
        key=lambda item: (_panel_spatial_key(item[1], bounds), item[0]))
    return [ordered[(2 * index + 1) * len(ordered) // (2 * count)][1]
            for index in range(count)]
# Reference arrows use the direction from panel center to the cached solver
# point, so the preview verifies the exact OUTPERM side that export encodes.
# Their fixed object-relative display length matches the arrows shown on live
# Base faces and avoids tiny dots/segments when solver reference points are
# deliberately close to small panels.
def _set_references(state, panelization, fc_object):
    coordinates = state["reference_coordinates"]
    lines_node = state["reference_lines"]
    if coordinates is None:
        return
    coordinates.point.setNum(0)
    lines_node.numVertices.setNum(0)
    if panelization is None:
        return
    points = []
    line_counts = []
    object_panels = panelization.panels_for(fc_object)
    all_points = [point for panel in object_panels for point in panel.points]
    if all_points:
        minima = [min(point[axis] for point in all_points) for axis in range(3)]
        maxima = [max(point[axis] for point in all_points) for axis in range(3)]
        diagonal = math.sqrt(sum(
            (maxima[axis] - minima[axis]) ** 2 for axis in range(3)))
        length = diagonal * float(
            getattr(fc_object.ViewObject, "ArrowScale", 8.0)) / 100.0
    else:
        length = 0.0
    if length <= 1.0e-12:
        length = 1.0

    for panel in _reference_arrow_panels(object_panels):
        start = FreeCAD.Vector(*_panel_center(panel))
        reference = FreeCAD.Vector(*panel.reference_point)
        direction = reference - start
        if direction.Length <= 1.0e-12:
            continue
        direction.normalize()
        # Preserve the solver-side direction but replace its numerical offset
        # with a visible arrow length controlled by ArrowScale.
        tip = start + direction * length
        side = direction.cross(FreeCAD.Vector(0.0, 0.0, 1.0))
        if side.Length <= 1.0e-9:
            side = direction.cross(FreeCAD.Vector(1.0, 0.0, 0.0))
        if side.Length <= 1.0e-12:
            continue
        side.normalize()
        head = tip - direction * (length * 0.28)
        wing = side * (length * 0.16)
        wing_one = head + wing
        wing_two = head - wing
        points.extend([
            tuple(start), tuple(tip),
            tuple(tip), tuple(wing_one),
            tuple(tip), tuple(wing_two)])
        line_counts.extend((2, 2, 2))
    if points:
        coordinates.point.setValues(0, len(points), points)
        lines_node.numVertices.setValues(
            0, len(line_counts), line_counts)


# Coin switches explicitly follow the FC object's visibility in addition to
# the optional panel/reference controls and cached-data availability.  The
# dielectric reference-direction aids follow selection just like the source-
# face normal arrows shown before panelization.
def syncFCPanelPreviewVisibility(view_provider):
    """Apply FC-object and individual preview visibility toggles."""
    state = getattr(view_provider, "_fcPanelPreview", None)
    if state is None:
        return
    try:
        vobj = view_provider.VObject
        visible = bool(
            state["has_data"] and vobj is not None and
            vobj.Visibility and vobj.ShowPanelization)
    except (AttributeError, ReferenceError, RuntimeError):
        # FreeCAD can deliver a queued selection-clear notification after the
        # document object and its ViewObject have already been destroyed.
        # Coin nodes are transient and may safely be switched off without
        # touching the stale Python wrapper.
        state["selected"] = False
        state["has_data"] = False
        state["panelization"] = None
        try:
            state["switch"].whichChild = coin.SO_SWITCH_NONE
            references = state["references_switch"]
            if references is not None:
                references.whichChild = coin.SO_SWITCH_NONE
        except (AttributeError, ReferenceError, RuntimeError):
            pass
        return
    state["switch"].whichChild = (
        coin.SO_SWITCH_ALL if visible else coin.SO_SWITCH_NONE)
    references = state["references_switch"]
    if references is not None:
        show_references = bool(
            visible and state["selected"] and
            view_provider.VObject.ShowReferencePoints)
        references.whichChild = (
            coin.SO_SWITCH_ALL if show_references
            else coin.SO_SWITCH_NONE)


def setFCPanelPreviewSelected(view_provider, selected):
    """Show dielectric reference-direction aids only while selected."""
    state = getattr(view_provider, "_fcPanelPreview", None)
    if state is None:
        return
    state["selected"] = bool(selected)
    syncFCPanelPreviewVisibility(view_provider)


# Split panels by diagnostic state once; later color changes need update only the
# material node and do not repeat geometry conversion.
def setFCPanelizationPreview(view_provider, panelization):
    """Populate one FC object's preview nodes from transient panels."""
    state = getattr(view_provider, "_fcPanelPreview", None)
    if state is None:
        return
    fc_object = view_provider.Object
    panels = (panelization.panels_for(fc_object)
              if panelization is not None else [])
    good = [panel for panel in panels if not panel.problematic]
    bad = [panel for panel in panels if panel.problematic]
    _set_panel_geometry(state["good"], good)
    _set_panel_geometry(state["bad"], bad)
    # Use the snapshot dimension rather than the live solver setting: changing
    # settings alone does not replace the geometry currently being inspected.
    state["has_data"] = bool(panels)
    state["panelization"] = panelization
    state["two_d"] = (panelization is not None and
                      panelization.context.dimension == "2D")
    if panelization is not None:
        syncFCPreviewDimension(view_provider.VObject, panelization.context.dimension)
    _set_color(state["good"]["line_material"], _line_color(view_provider.VObject))
    transparency = _shape_appearance(view_provider.VObject)[1]
    # Dielectric face transparency is useful in 3D, but would wash out the only
    # geometry in a 2D preview. Keep both normal and diagnostic segments opaque.
    for branch in (state["good"], state["bad"]):
        _set_transparency(branch["line_material"],
                          0.0 if state["two_d"] else transparency)
    if state["dielectric"]:
        _set_references(state, panelization, fc_object)
    syncFCPanelPreviewVisibility(view_provider)


def onFCPanelPreviewChanged(view_provider, prop):
    """Update colors or visibility after a view-property edit."""
    state = getattr(view_provider, "_fcPanelPreview", None)
    if state is None:
        return
    vobj = view_provider.VObject
    if prop == "ShapeAppearance":
        color, transparency = _shape_appearance(vobj)
        _set_color(state["good"]["face_material"], color)
        for branch in (state["good"], state["bad"]):
            _set_transparency(branch["face_material"], transparency)
            _set_transparency(branch["line_material"], transparency)
    elif prop == "ShapeColor":
        _set_color(state["good"]["face_material"], tuple(vobj.ShapeColor))
    elif prop == "LineColor":
        _set_color(state["good"]["line_material"], tuple(vobj.LineColor))
    elif prop == "LineMaterial":
        # Newer Part view providers edit LineMaterial instead of only emitting
        # a legacy LineColor change; both controls must update the same preview.
        _set_color(state["good"]["line_material"], _line_color(vobj))
    elif prop == "BadPanelColor":
        color = tuple(vobj.BadPanelColor)
        _set_color(state["bad"]["face_material"], color)
        _set_color(state["bad"]["line_material"], color)
    elif prop == "ArrowColor":
        _set_color(state["reference_material"],
                   tuple(vobj.ArrowColor))
    elif prop == "ArrowScale" and state["dielectric"]:
        _set_references(state, state["panelization"], view_provider.Object)
    elif prop == "Transparency":
        transparency = _part_transparency(vobj)
        for branch in (state["good"], state["bad"]):
            _set_transparency(branch["face_material"], transparency)
            _set_transparency(branch["line_material"], transparency)
    if prop in ("Visibility", "ShowPanelization", "ShowReferencePoints"):
        syncFCPanelPreviewVisibility(view_provider)
    if state.get("two_d", False):
        # 2D segments represent the body itself, not translucent face rims.
        for branch in (state["good"], state["bad"]):
            _set_transparency(branch["line_material"], 0.0)
