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


__title__="FreeCAD E.M. Workbench FasterCap / FastCap common helpers"
__author__ = "FastFieldSolvers - Enrico Di Lorenzo"
__url__ = "http://www.fastfieldsolvers.com"

FC_OBJECT_TYPES = ("FCConductor", "FCDielectric", "FCSolver")


# Persistent links are normalized here, while all solver-specific geometry work
# remains in later transient stages.  Keeping this layer narrow prevents an
# ordinary FeaturePython recompute from invoking expensive OpenCascade logic.
#
# FC object kinds share FreeCAD's generic FeaturePython TypeId, so the proxy
# tag is the stable discriminator used throughout selection and validation.
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
        two_d = any(getattr(getattr(obj, "Proxy", None), "Type", None) == "FCSolver"
                    and getattr(obj, "Dimension", "") == "2D"
                    for obj in source.Document.Objects)
        supported = ("Face", "Shell", "Solid", "Compound", "CompSolid")
        if two_d:
            supported += ("Wire", "Edge")
        subelements = tuple(getattr(selected, "SubElementNames", ()) or ())
        if subelements:
            subelements = tuple(
                name for name in subelements
                if name.rsplit(".", 1)[-1].startswith(
                    supported))
            if not subelements:
                continue
        elif getattr(source.Shape, "ShapeType", "") not in supported:
            continue
        base.append((source, subelements or ("",)))
    return normalizeFCBase(base)


def fcBaseReferencesOverlap(first, second):
    """Return whether two Base lists claim the same source subgeometry.

    A whole-object link overlaps every subelement link on that source.  For
    subelement-only links, at least one exact persistent subelement name must
    occur in both lists.  Geometric overlaps between different CAD sources are
    deliberately left to the panelization validator.
    """
    second_by_source = {}
    # Compare persistent assignments here, not geometric coincidence. Two
    # different CAD objects can overlap and still need the later Boolean checks.
    for source, subelements in normalizeFCBase(second):
        second_by_source.setdefault(id(source), set()).update(subelements)
    for source, subelements in normalizeFCBase(first):
        other = second_by_source.get(id(source))
        if not other:
            continue
        names = set(subelements)
        if "" in names or "" in other or names.intersection(other):
            return True
    return False


def getFCBaseOwners(document, base, object_type, exclude=None):
    """Return FC objects of one kind already claiming any proposed Base link."""
    return [
        obj for obj in getattr(document, "Objects", [])
        if obj is not exclude and
        getattr(getattr(obj, "Proxy", None), "Type", None) == object_type and
        fcBaseReferencesOverlap(getattr(obj, "Base", []), base)]


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
        # The empty subelement names the whole shape and supersedes its faces.
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
    """Hide the live CAD sources represented by a generated panel snapshot."""
    for source in getFCBaseObjects(base):
        view = getattr(source, "ViewObject", None)
        if view is not None:
            view.hide()


def showFCBase(base):
    """Show live CAD sources when no generated panel snapshot is displayed."""
    for source in getFCBaseObjects(base):
        view = getattr(source, "ViewObject", None)
        if view is not None:
            view.show()


def syncFCBaseVisibility(fc_object):
    """Make unpanelized Base objects follow their FC object's visibility."""
    view = getattr(fc_object, "ViewObject", None)
    if view is None:
        return
    if bool(getattr(view, "Visibility", True)):
        showFCBase(fc_object.Base)
    else:
        hideFCBase(fc_object.Base)


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
    # Older objects may not resolve subelements through getSubObject; retain
    # the direct Shape lookup without turning a missing link into an exception.
    try:
        return source.Shape.getElement(subelement)
    except (AttributeError, RuntimeError):
        return None


def getFCBaseShapes(base):
    """Resolve the current linked shapes without copying their topology."""
    shapes = []
    for source, subelements in normalizeFCBase(base):
        for subelement in subelements:
            shape = _fc_subshape(source, subelement)
            if shape is None or not hasattr(shape, "ShapeType"):
                continue
            try:
                if shape.isNull():
                    continue
            except AttributeError:
                pass
            shapes.append(shape)
    return shapes
