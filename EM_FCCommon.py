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


__title__="FreeCAD E.M. Workbench FasterCap / FastCap common helpers"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

import Part


FC_OBJECT_TYPES = ("FCConductor", "FCDielectric", "FCSolver")


def isFCObject(obj):
    """Return whether an object belongs to the persistent FC object model."""
    return (getattr(getattr(obj, "Proxy", None), "Type", None) in
            FC_OBJECT_TYPES)


def hasFCObjectReference(base):
    """Return whether raw Base data contains any nested FC object."""
    if base is None:
        return False
    entries = [base] if hasattr(base, "Name") else base
    for entry in entries:
        source = entry if hasattr(entry, "Name") else (
            entry[0] if isinstance(entry, (tuple, list)) and entry else None)
        if isFCObject(source):
            return True
    return False


def normalizeFCBase(base):
    '''Normalize source references for an App::PropertyLinkSubList.

       A whole object is represented by an empty subelement name. Existing
       (object, subelement-list) entries are retained without resolving them,
       so the links remain parametric and persistent in the document.
    '''
    if base is None:
        return []
    if hasattr(base, "Name"):
        return [] if isFCObject(base) else [(base, ("",))]

    normalized = []
    for entry in base:
        if hasattr(entry, "Name"):
            if not isFCObject(entry):
                normalized.append((entry, ("",)))
            continue
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            continue
        source, subelements = entry
        if not hasattr(source, "Name") or isFCObject(source):
            continue
        if isinstance(subelements, str):
            subelements = (subelements,)
        else:
            subelements = tuple(subelements)
        normalized.append((source, subelements or ("",)))
    return normalized


def getFCObjectsFromSelection(selection, object_type):
    """Return unique selected FC objects having the requested proxy type."""
    objects = []
    for selected in selection or []:
        source = getattr(selected, "Object", None)
        proxy_type = getattr(getattr(source, "Proxy", None), "Type", None)
        if proxy_type == object_type and source not in objects:
            objects.append(source)
    return objects


def getFCBaseFromSelection(selection):
    '''Convert FreeCAD extended selections to LinkSubList references.'''
    base = []
    for selected in selection or []:
        source = getattr(selected, "Object", None)
        if source is None or not hasattr(source, "Shape"):
            continue
        if isFCObject(source):
            continue
        subelements = tuple(getattr(selected, "SubElementNames", ()) or ())
        if subelements:
            subelements = tuple(
                name for name in subelements
                if name.rsplit(".", 1)[-1].startswith(
                    ("Face", "Shell", "Solid", "Compound", "CompSolid")))
            if not subelements:
                continue
        elif getattr(source.Shape, "ShapeType", "") not in (
                "Face", "Shell", "Solid", "Compound", "CompSolid"):
            continue
        base.append((source, subelements or ("",)))
    return normalizeFCBase(base)


def mergeFCBase(base, additions):
    """Merge LinkSubList references without duplicating sources or subelements."""
    merged = []
    positions = {}
    for source, subelements in normalizeFCBase(base) + normalizeFCBase(additions):
        key = id(source)
        names = list(dict.fromkeys(subelements))
        if key not in positions:
            positions[key] = len(merged)
            merged.append([source, names])
            continue
        current = merged[positions[key]][1]
        if "" in current or "" in names:
            merged[positions[key]][1] = [""]
        else:
            current.extend(name for name in names if name not in current)
    return [(source, tuple(subelements)) for source, subelements in merged]


def getFCBaseObjects(base):
    '''Return each source document object once, preserving reference order.'''
    objects = []
    seen = set()
    for source, _subelements in normalizeFCBase(base):
        identity = getattr(source, "Name", id(source))
        if identity not in seen:
            seen.add(identity)
            objects.append(source)
    return objects


def hideFCBase(base):
    '''Hide source CAD objects after creating their independent FC wrapper.'''
    for source in getFCBaseObjects(base):
        view = getattr(source, "ViewObject", None)
        if view is not None:
            view.hide()


def _fc_subshape(source, subelement):
    '''Resolve one persistent subelement reference to its current shape.'''
    if not subelement:
        return getattr(source, "Shape", None)
    try:
        shape = source.getSubObject(subelement)
        if shape is not None and hasattr(shape, "ShapeType"):
            return shape
    except (AttributeError, RuntimeError):
        pass
    try:
        return source.Shape.getElement(subelement)
    except (AttributeError, RuntimeError):
        return None


def _fc_boundary_parts(shape):
    '''Return surface topology without Boolean operations or thickening.'''
    if shape is None or not hasattr(shape, "ShapeType"):
        return []
    try:
        if shape.isNull():
            return []
    except AttributeError:
        pass

    shape_type = shape.ShapeType
    if shape_type == "Solid":
        # A solid remains available through Base; only its boundary is copied
        # into the FC object's independent display representation.
        return [shell.copy() for shell in shape.Shells]
    if shape_type in ("Shell", "Face"):
        return [shape.copy()]
    if shape_type in ("Compound", "CompSolid"):
        parts = []
        for child in shape.childShapes():
            parts.extend(_fc_boundary_parts(child))
        return parts
    return []


def makeFCBoundaryShape(base):
    '''Build a lightweight compound of referenced solid boundaries/surfaces.

       This is only the persistent object's display shape. It deliberately
       performs no intersection, fuse, section, cleanup, or panelization.
    '''
    parts = []
    for source, subelements in normalizeFCBase(base):
        for subelement in subelements:
            parts.extend(_fc_boundary_parts(
                _fc_subshape(source, subelement)))
    return Part.makeCompound(parts) if parts else Part.Shape()
