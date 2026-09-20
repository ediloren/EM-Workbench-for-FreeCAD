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
#***************************************************************************


"""Coin scene-graph preview helpers for transient FC solver panels."""

# Preview design notes:
# - Valid and problematic panels occupy separate branches for independent color.
# - Each object shares coordinate and index arrays instead of creating a Coin
#   node or persistent FreeCAD object per panel.
# - Dielectric markers show the exact reference points later used by export.
# - Visibility combines object visibility, user switches, and cached-data state.
# - Runtime scene nodes are reconstructed by attach and are never serialized.

import FreeCAD

if FreeCAD.GuiUp:
    from pivy import coin
else:
    coin = None


FCPREVIEW_BAD_COLOR = (1.0, 0.0, 0.0)
FCPREVIEW_REFERENCE_COLOR = (0.9, 0.1, 0.9)


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
            "Show actual generated dielectric reference points and arrows")
        vobj.ShowReferencePoints = True
    if dielectric and "ReferencePointColor" not in vobj.PropertiesList:
        vobj.addProperty(
            "App::PropertyColor", "ReferencePointColor", "Panelization",
            "Color of dielectric reference-point preview aids")
        vobj.ReferencePointColor = FCPREVIEW_REFERENCE_COLOR


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


# Attach two panel branches and, for dielectrics, one reference-marker branch to
# the standard root supplied by the FeaturePython view provider.
def attachFCPanelPreview(view_provider, vobj, dielectric=False):
    """Attach empty transient panel/reference nodes below an FC view root."""
    if coin is None:
        return
    ensureFCPreviewProperties(vobj, dielectric)
    panel_switch = coin.SoSwitch()
    face_color, transparency = _shape_appearance(vobj)
    good = _geometry_node(
        face_color, tuple(vobj.LineColor), transparency)
    bad_color = tuple(vobj.BadPanelColor)
    bad = _geometry_node(bad_color, bad_color, transparency)
    panel_switch.addChild(good["separator"])
    panel_switch.addChild(bad["separator"])
    panel_switch.whichChild = coin.SO_SWITCH_NONE
    vobj.RootNode.addChild(panel_switch)

    references_switch = None
    reference_coordinates = None
    reference_points = None
    reference_lines = None
    reference_material = None
    if dielectric:
        references_switch = coin.SoSwitch()
        separator = coin.SoSeparator()
        reference_material = _material(
            tuple(vobj.ReferencePointColor), 0.0)
        style = coin.SoDrawStyle()
        style.pointSize = 7.0
        style.lineWidth = 2.0
        reference_coordinates = coin.SoCoordinate3()
        reference_points = coin.SoPointSet()
        reference_lines = coin.SoLineSet()
        separator.addChild(reference_material)
        separator.addChild(style)
        separator.addChild(reference_coordinates)
        separator.addChild(reference_points)
        separator.addChild(reference_lines)
        references_switch.addChild(separator)
        references_switch.whichChild = coin.SO_SWITCH_NONE
        vobj.RootNode.addChild(references_switch)

    view_provider._fcPanelPreview = {
        "switch": panel_switch, "good": good, "bad": bad,
        "references_switch": references_switch,
        "reference_coordinates": reference_coordinates,
        "reference_points": reference_points,
        "reference_lines": reference_lines,
        "reference_material": reference_material,
        "has_data": False, "dielectric": dielectric, "selected": False}


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


# Reference arrows use the cached solver point and panel center so the preview
# verifies the exact side choice that export will encode.
def _set_references(state, panelization, fc_object):
    coordinates = state["reference_coordinates"]
    points_node = state["reference_points"]
    lines_node = state["reference_lines"]
    if coordinates is None:
        return
    coordinates.point.setNum(0)
    points_node.numPoints = 0
    lines_node.numVertices.setNum(0)
    if panelization is None:
        return
    points = []
    line_counts = []
    seen_groups = set()
    per_panel = (
        panelization.context.target_solver == "FasterCap" and
        panelization.context.dimension == "3D")
    if per_panel:
        for panel in panelization.panels_for(fc_object):
            if panel.reference_point is None:
                continue
            start = _panel_center(panel)
            points.extend((start, panel.reference_point))
            line_counts.append(2)
    else:
        for group in panelization.dielectric_groups:
            if (group.entity.fc_object is not fc_object or
                    group.index in seen_groups):
                continue
            seen_groups.add(group.index)
            points.append(group.reference_point)
            line_counts.append(1)
    if points:
        coordinates.point.setValues(0, len(points), points)
        points_node.numPoints = len(points)
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
    visible = bool(
        state["has_data"] and view_provider.VObject.Visibility and
        view_provider.VObject.ShowPanelization)
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
    state["has_data"] = bool(panels)
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
    elif prop == "BadPanelColor":
        color = tuple(vobj.BadPanelColor)
        _set_color(state["bad"]["face_material"], color)
        _set_color(state["bad"]["line_material"], color)
    elif prop == "ReferencePointColor":
        _set_color(state["reference_material"],
                   tuple(vobj.ReferencePointColor))
    elif prop == "Transparency":
        transparency = _part_transparency(vobj)
        for branch in (state["good"], state["bad"]):
            _set_transparency(branch["face_material"], transparency)
            _set_transparency(branch["line_material"], transparency)
    if prop in ("Visibility", "ShowPanelization", "ShowReferencePoints"):
        syncFCPanelPreviewVisibility(view_provider)
