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


"""Transient FasterCap / FastCap surface resolution and panelization.

The expensive pipeline is invoked explicitly by the panelize command. It never
creates one document object per panel and never runs from FeaturePython execute.
"""

# Panelization pipeline notes:
# - Exact interaction curves split faces before material semantics are assigned.
# - Resolved 3D patches are globally fragmented into topology-connected islands;
#   every island is passed to Netgen once so adjacent faces share mesh nodes.
# - Each patch is classified on both sides of its oriented surface normal.
# - Coincident surfaces are resolved by electromagnetic, not merely geometric,
#   equivalence; protected split edges preserve real material transitions.
# - FasterCap 3D, FastCap 3D, and 2D use distinct discretization constraints.
# - Dielectric references come from validated panel sides and compatible panels
#   are grouped only after material-side resolution.
# - Validation covers duplicates, degeneracy, planarity, crossings, orientation,
#   gaps, and conductor-region consistency before export.
# - The document-keyed cache is guarded by solver and source signatures.
# - Preview uses shared Coin graphs; panels never become document objects.
# - Diagnostics accumulate so one run exposes all actionable model problems.

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import FreeCAD
import Part

from EM_FCCommon import hideFCBase, syncFCBaseVisibility
from EM_FCGeometry import (
    FCBoundingBox, FCBoundingBoxIndex, FCDiagnostic, FCFaceGeometry,
    FCGeometryComponent, FCGeometryModel, FC_DIAGNOSTIC_ERROR,
    FC_DIAGNOSTIC_WARNING, FC_ENTITY_TYPES, FC_POINT_BOUNDARY,
    FC_POINT_INSIDE, extractFCGeometry)
from EM_FCSolver import EMFCSOLVER_UNITS, EMFCSOLVER_UNITS_VALS


FCPANEL_DEF_CURVATURE_TOLERANCE = 0.01
FCPANEL_PATHOLOGICAL_ASPECT = 1000.0
FCPANEL_FASTER_CAP_QUAD_ASPECT = 20.0
FCPANEL_MIN_TRIANGLE_ANGLE = 15.0
FCPANEL_TESSELLATION_REFINEMENTS = (1.0, 0.5, 0.25)

# Every 3D topology island is meshed by MeshPart.meshFromShape's Netgen overload.
# Keep these controls local to this module until the FC user interface exposes
# a reason to make them persistent solver or conductor properties.
FCPANEL_MESH_GROWTH_RATE = 0.3
FCPANEL_MESH_SEGMENTS_PER_EDGE = 0.5
FCPANEL_MESH_SECOND_ORDER = 0
FCPANEL_MESH_OPTIMIZE = 1
FCPANEL_MESH_ALLOW_QUADS = 0

FC_ELEMENT_TRIANGLE = "T"
FC_ELEMENT_QUAD = "Q"
FC_ELEMENT_SEGMENT = "S"

_PANELIZATION_CACHE: Dict[int, "FCPanelization"] = {}


class FCPanelizationError(RuntimeError):
    """Raised when a valid transient panelization cannot be produced."""


@dataclass
class FCSurfacePatch:
    """One split and electromagnetically resolved boundary patch."""

    shape: Any
    entity: Any
    component: FCGeometryComponent
    source_face: FCFaceGeometry
    index: int
    bbox: FCBoundingBox
    center: Any = None
    normal: Any = None
    inner_permittivity: Optional[float] = None
    outer_permittivity: Optional[float] = None
    surrounding_permittivity: Optional[float] = None
    removed: bool = False
    problem_codes: List[str] = field(default_factory=list)


@dataclass
class FCMeshingIsland:
    """One connected, shared-topology shape submitted to Netgen as a unit."""

    shape: Any
    patches: List[FCSurfacePatch]
    index: int
    bbox: FCBoundingBox


@dataclass
class FCPanel:
    """Transient T, Q, or S solver element."""

    kind: str
    points: Tuple[Tuple[float, float, float], ...]
    entity: Any
    patch: FCSurfacePatch
    index: int
    inner_permittivity: Optional[float] = None
    outer_permittivity: Optional[float] = None
    surrounding_permittivity: Optional[float] = None
    reference_point: Optional[Tuple[float, float, float]] = None
    dielectric_group: Optional[int] = None
    problem_codes: List[str] = field(default_factory=list)

    @property
    def problematic(self):
        return bool(self.problem_codes)


@dataclass
class FCDielectricPanelGroup:
    """Panels sharing one FastCap-compatible dielectric reference point."""

    entity: Any
    panels: List[FCPanel]
    inner_permittivity: float
    outer_permittivity: float
    reference_point: Tuple[float, float, float]
    reference_side: str = "outer"
    index: int = 0


@dataclass
class FCPanelization:
    """Complete transient preview/export model for one document."""

    context: Any
    geometry: FCGeometryModel
    patches: List[FCSurfacePatch]
    panels: List[FCPanel]
    dielectric_groups: List[FCDielectricPanelGroup]
    diagnostics: List[FCDiagnostic]
    signature: Tuple[Any, ...]
    created_at: float = field(default_factory=time.time)

    @property
    def has_errors(self):
        return any(item.severity == FC_DIAGNOSTIC_ERROR
                   for item in self.diagnostics)

    def panels_for(self, fc_object):
        return [panel for panel in self.panels
                if panel.entity.fc_object is fc_object]

    def diagnostics_for(self, fc_object):
        return [item for item in self.diagnostics
                if item.fc_object is fc_object]


def _type_of(obj):
    return getattr(getattr(obj, "Proxy", None), "Type", None)


def _diag(severity, code, message, patch=None, fc_object=None,
          component_index=None, face_index=None, details=None):
    if patch is not None:
        fc_object = patch.entity.fc_object
        component_index = patch.component.index
        face_index = patch.source_face.face_index
        if code not in patch.problem_codes:
            patch.problem_codes.append(code)
    return FCDiagnostic(
        severity, code, message, fc_object, component_index,
        getattr(patch.source_face, "source_object", None)
        if patch is not None else None,
        getattr(patch.source_face, "source_subname", "")
        if patch is not None else "",
        face_index, details or {})


def _shape_hash(shape):
    try:
        return int(shape.hashCode())
    except TypeError:
        return int(shape.hashCode(2147483647))
    except (AttributeError, RuntimeError, ValueError):
        return id(shape)


def _same_shape(first, second):
    try:
        return bool(first.isSame(second))
    except (AttributeError, RuntimeError, TypeError):
        return first is second


def _reverse_shape(shape):
    try:
        return shape.reversed()
    except AttributeError:
        result = shape.copy()
        result.reverse()
        return result


def _bbox_volume(bbox):
    return max(0.0, bbox.xmax - bbox.xmin) * max(
        0.0, bbox.ymax - bbox.ymin) * max(0.0, bbox.zmax - bbox.zmin)


def _bbox_contains_box(outer, inner, tolerance):
    return (
        outer.xmin - tolerance <= inner.xmin and
        outer.ymin - tolerance <= inner.ymin and
        outer.zmin - tolerance <= inner.zmin and
        outer.xmax + tolerance >= inner.xmax and
        outer.ymax + tolerance >= inner.ymax and
        outer.zmax + tolerance >= inner.zmax)


def _vector_tuple(vector):
    return (float(vector.x), float(vector.y), float(vector.z))


def _tuple_vector(point):
    return FreeCAD.Vector(point[0], point[1], point[2])


def _distance(first, second):
    return (first - second).Length


def _permittivity_equal(first, second):
    return math.isclose(float(first), float(second),
                        rel_tol=1.0e-10, abs_tol=1.0e-12)


def _solver_length_to_mm(value, units):
    try:
        metres_per_unit = EMFCSOLVER_UNITS_VALS[
            EMFCSOLVER_UNITS.index(units)]
    except ValueError:
        return float(value)
    return float(value) * metres_per_unit * 1000.0


def _dot(first, second):
    return first.dot(second)


def _unique_shapes(shapes):
    buckets = {}
    result = []
    for shape in shapes:
        key = _shape_hash(shape)
        if any(_same_shape(shape, old)
               for old in buckets.setdefault(key, [])):
            continue
        buckets[key].append(shape)
        result.append(shape)
    return result


def _source_signature(fc_object):
    base_items = []
    try:
        from EM_FCCommon import normalizeFCBase, _fc_subshape
        for source, subnames in normalizeFCBase(fc_object.Base):
            for subname in subnames:
                shape = _fc_subshape(source, subname)
                bbox = getattr(shape, "BoundBox", None)
                bbox_values = None
                if bbox is not None:
                    bbox_values = tuple(round(float(value), 12) for value in (
                        bbox.XMin, bbox.YMin, bbox.ZMin,
                        bbox.XMax, bbox.YMax, bbox.ZMax))
                base_items.append((
                    getattr(source, "Name", id(source)), subname,
                    _shape_hash(shape), bbox_values))
    except (AttributeError, RuntimeError, TypeError, ValueError):
        base_items.append(("invalid",))
    values = [
        getattr(fc_object, "DefaultPermittivity", None),
        getattr(fc_object, "InnerPermittivity", None),
        getattr(fc_object, "OuterPermittivity", None),
        str(getattr(fc_object, "Orientation", "")),
        getattr(fc_object, "PanelCurvatureTolerance",
                FCPANEL_DEF_CURVATURE_TOLERANCE)]
    return (getattr(fc_object, "Name", id(fc_object)),
            _type_of(fc_object), tuple(base_items), tuple(values))


# The cache signature combines solver settings, object material controls, and
# source shape identities so presentation-only changes do not invalidate it.
def getFCPanelizationSignature(document, solver=None):
    """Return a cheap signature used to reject stale previews and exports."""
    if solver is None:
        solvers = [obj for obj in getattr(document, "Objects", [])
                   if _type_of(obj) == "FCSolver"]
        solver = solvers[0] if len(solvers) == 1 else None
    solver_values = None if solver is None else (
        getattr(solver, "Name", id(solver)),
        str(getattr(solver, "Dimension", "")),
        str(getattr(solver, "TargetSolver", "")),
        str(getattr(solver, "Units", "")),
        float(getattr(solver, "SpacePermittivity", 0.0)),
        float(getattr(solver, "GeometryTolerance", 0.0)),
        float(getattr(solver, "MaxPanelSize", 0.0)),
        getattr(getattr(solver, "ReferenceConductor", None), "Name", None))
    objects = tuple(_source_signature(obj)
                    for obj in getattr(document, "Objects", [])
                    if _type_of(obj) in FC_ENTITY_TYPES)
    return solver_values, objects


def _set_status(fc_object, panelized, count=0, errors=0):
    was_touched = False
    try:
        was_touched = bool(fc_object.isTouched())
    except (AttributeError, RuntimeError, TypeError):
        pass
    try:
        fc_object.Panelized = bool(panelized)
        fc_object.PanelCount = int(count)
        fc_object.PanelErrorCount = int(errors)
        # Output/status properties touch FeaturePython objects. Do not leave a
        # recompute request when this function was the only source of it.
        if not was_touched and hasattr(fc_object, "purgeTouched"):
            fc_object.purgeTouched()
    except (AttributeError, RuntimeError, TypeError):
        pass


def _update_preview(fc_object, panelization):
    view = getattr(fc_object, "ViewObject", None)
    proxy = getattr(view, "Proxy", None)
    if proxy is not None and hasattr(proxy, "setPanelizationPreview"):
        proxy.setPanelizationPreview(panelization)


# Clearing removes transient data, resets read-only status properties, empties
# custom Coin nodes, and returns Base visibility to the FC object's control.
# This also keeps a failed replacement attempt visually consistent.
def clearFCPanelization(document=None, objects=None):
    """Discard transient panels and restore parent-controlled CAD sources."""
    if document is None:
        document = FreeCAD.ActiveDocument
    if document is None:
        return
    _PANELIZATION_CACHE.pop(id(document), None)
    selected = (list(objects) if objects is not None else
                [obj for obj in getattr(document, "Objects", [])
                 if _type_of(obj) in FC_ENTITY_TYPES])
    for obj in selected:
        _set_status(obj, False)
        _update_preview(obj, None)
        syncFCBaseVisibility(obj)


def invalidateFCPanelizationForObject(fc_object):
    """Retain an existing snapshot; edits are reported when it is exported."""
    return


def getFCPanelization(document=None, require_current=False):
    """Return the cached snapshot, optionally requiring a matching model."""
    if document is None:
        document = FreeCAD.ActiveDocument
    result = _PANELIZATION_CACHE.get(id(document)) if document else None
    if (result is not None and require_current and
            result.signature != getFCPanelizationSignature(
                document, result.context.solver)):
        return None
    return result


def _share_topological_edge(first, second):
    buckets = {}
    for edge in first.Edges:
        buckets.setdefault(_shape_hash(edge), []).append(edge)
    for edge in second.Edges:
        if any(_same_shape(edge, candidate)
               for candidate in buckets.get(_shape_hash(edge), ())):
            return True
    return False


def _append_splitters(splitters, record, edges):
    splitters.setdefault(id(record), [record, []])[1].extend(edges)


# Exact-interaction discovery ---------------------------------------------
# Common faces record area overlap; section edges record crossings or contacts.
# Both retain the participating source faces for later diagnostics.
def _common_faces(first, second, tolerance, diagnostics, records,
                  first_component, second_component):
    try:
        common = first.shape.common(second.shape, tolerance)
        return [face for face in getattr(common, "Faces", [])
                if float(getattr(face, "Area", 0.0)) > tolerance * tolerance]
    except (AttributeError, RuntimeError, TypeError, ValueError) as error:
        diagnostics.append(_diag(
            FC_DIAGNOSTIC_ERROR, "surface_common_failed",
            "OCC could not test a candidate surface overlap: %s" % error,
            fc_object=first_component.entity.fc_object,
            component_index=first.component_index,
            face_index=first.face_index,
            details={"other_object":
                     getattr(second_component.entity.fc_object, "Name", None)}))
        records.add(id(first))
        records.add(id(second))
        return []


def _section_edges(first, second, tolerance, diagnostics, records,
                   first_component, second_component):
    try:
        return list(getattr(
            first.shape.section(second.shape, tolerance), "Edges", []))
    except (AttributeError, RuntimeError, TypeError, ValueError) as error:
        diagnostics.append(_diag(
            FC_DIAGNOSTIC_ERROR, "surface_section_failed",
            "OCC could not section candidate surfaces: %s" % error,
            fc_object=first_component.entity.fc_object,
            component_index=first.component_index,
            face_index=first.face_index,
            details={"other_object":
                     getattr(second_component.entity.fc_object, "Name", None)}))
        records.add(id(first))
        records.add(id(second))
        return []


# Bounding boxes have already provided plausible pairs; exact OCC operations
# here determine whether and how their surfaces actually interact.
def _face_pair_records(first_component, second_component, tolerance):
    if first_component is second_component:
        return first_component.face_index.candidate_pairs(
            tolerance=tolerance)
    return first_component.candidate_face_pairs(
        second_component, tolerance)


# Inspect entity pairs and self-components, collecting splitters symmetrically
# so every participating source face receives the same intersection boundary.
def _collect_surface_interactions(model):
    """Accumulate section/overlap splitters without splitting any face yet."""
    tolerance = model.context.geometry_tolerance
    diagnostics = []
    splitters = {}
    coincidences = []
    failed_records = set()
    component_pairs = model.candidate_component_pairs()
    work = [(component, component)
            for entity in model.entities for component in entity.components]
    work.extend(component_pairs)

    seen_component_pairs = set()
    for first_component, second_component in work:
        component_key = tuple(sorted((id(first_component),
                                      id(second_component))))
        if component_key in seen_component_pairs:
            continue
        seen_component_pairs.add(component_key)
        face_pairs = _face_pair_records(
            first_component, second_component, tolerance)
        if not face_pairs:
            continue

        for first, second in face_pairs:
            if first is second:
                continue
            conformal_edge = _share_topological_edge(
                first.shape, second.shape)
            common_faces = _common_faces(
                first, second, tolerance, diagnostics, failed_records,
                first_component, second_component)
            if common_faces:
                common_area = sum(float(face.Area) for face in common_faces)
                coincidences.append((first, second, common_area))
                common_edges = [edge for face in common_faces
                                for edge in face.Edges]
                area_tolerance = tolerance * tolerance
                if common_area < float(first.shape.Area) - area_tolerance:
                    _append_splitters(splitters, first, common_edges)
                if common_area < float(second.shape.Area) - area_tolerance:
                    _append_splitters(splitters, second, common_edges)
                # The common boundary completely describes a coplanar
                # overlap. A section call would only duplicate these edges.
                continue

            # Existing shared topology already meets conformally and is not a
            # splitter; passing boundary edges to SplitAPI is both costly and
            # numerically fragile.
            if conformal_edge:
                continue
            # A shell-wide section cannot be routed back to individual faces
            # by bounding boxes: a curve may touch a face's box at a point
            # while lying entirely outside that trimmed face. Such unrelated
            # edges can make SplitAPI return an unchanged face, leaving a
            # conductor-covered dielectric region classified by one sample.
            # Section the actual face pair so each splitter belongs to both.
            edges = _section_edges(
                first, second, tolerance, diagnostics, failed_records,
                first_component, second_component)
            if edges:
                _append_splitters(splitters, first, edges)
                _append_splitters(splitters, second, edges)

    for _identity, value in splitters.items():
        value[1][:] = _unique_shapes(value[1])
    return splitters, coincidences, failed_records, diagnostics


def _flatten_shapes(value):
    result = []
    if value is None:
        return result
    if hasattr(value, "ShapeType"):
        return [value]
    if isinstance(value, (tuple, list)):
        for item in value:
            result.extend(_flatten_shapes(item))
    return result


# Split a copied face with all collected edges in one operation, then reject
# negligible fragments using the model tolerance.
def _split_face_once(face, splitter_edges, tolerance):
    if not splitter_edges:
        return [face], None
    primary = []
    try:
        from BOPTools import SplitAPI
        result = SplitAPI.slice(face, splitter_edges, "Split", tolerance)
        primary = list(getattr(result, "Faces", []))
        if len(primary) > 1:
            return primary, None
    except (ImportError, AttributeError, RuntimeError, TypeError, ValueError):
        pass

    # A one-face result can be the original, unsplit face. Give the alternate
    # OCC splitter a chance before accepting that apparent success.
    try:
        result = Part.makeSplitShape(
            face, [(edge, face) for edge in splitter_edges])
        pieces = [piece for candidate in _flatten_shapes(result)
                  for piece in (getattr(candidate, "Faces", []) if
                                getattr(candidate, "ShapeType", "") != "Face"
                                else [candidate])]
        if len(pieces) > len(primary):
            return pieces, None
    except (AttributeError, RuntimeError, TypeError, ValueError) as error:
        if primary:
            return primary, None
        return [face], error
    if primary:
        return primary, None
    if pieces:
        return pieces, None
    return [face], RuntimeError("OCC returned no split faces")


def _evaluated_face_point(face, candidate, tolerance):
    """Project a candidate to the surface and accept only trimmed-face points."""
    try:
        u, v = face.Surface.parameter(candidate)
        point = face.valueAt(u, v)
        if not face.isInside(point, tolerance, True):
            return None
        normal = face.normalAt(u, v)
        if normal.Length <= 1.0e-15:
            return None
        normal.normalize()
        return point, normal
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None


# A face's area centroid may project into a hole or outside a concave trimmed
# region. Return a point verified against the face rather than its raw surface.
def _face_center_normal(face):
    bbox = face.BoundBox
    diagonal = math.sqrt(
        bbox.XLength * bbox.XLength +
        bbox.YLength * bbox.YLength +
        bbox.ZLength * bbox.ZLength)
    tolerance = max(diagonal * 1.0e-10, 1.0e-12)

    try:
        candidate = _evaluated_face_point(
            face, face.CenterOfMass, tolerance)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        candidate = None
    if candidate is not None:
        return candidate

    # An auxiliary OCC triangulation respects trimming wires, so a facet center
    # supplies a reliable interior seed when the geometric centroid is in a
    # hole. Its triangles are never used as solver panels.
    try:
        vertices, triangles = face.tessellate(
            max(diagonal * 0.1, tolerance * 10.0))
        for first, second, third in triangles:
            raw = (
                vertices[first] + vertices[second] +
                vertices[third]) / 3.0
            candidate = _evaluated_face_point(face, raw, tolerance)
            if candidate is not None:
                return candidate
    except (AttributeError, IndexError, RuntimeError, TypeError, ValueError):
        pass

    # Last fallback samples the trimmed parameter range without assuming that
    # its midpoint belongs to a non-convex face.
    umin, umax, vmin, vmax = face.ParameterRange
    fractions = (0.5, 0.25, 0.75, 0.125, 0.375, 0.625, 0.875)
    for fu in fractions:
        for fv in fractions:
            u = umin + (umax - umin) * fu
            v = vmin + (vmax - vmin) * fv
            point = face.valueAt(u, v)
            candidate = _evaluated_face_point(face, point, tolerance)
            if candidate is not None:
                return candidate
    raise ValueError("could not locate a point inside the trimmed face")


# OCC splitting may choose a fresh orientation; restore agreement with the
# already normalized source face before side semantics are computed.
def _align_patch_face(piece, source):
    try:
        center, normal = _face_center_normal(piece)
        u, v = source.Surface.parameter(center)
        source_normal = source.normalAt(u, v)
        source_normal.normalize()
        return _reverse_shape(piece) if _dot(normal, source_normal) < 0.0 else piece
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return piece


# Convert every source face into one or more provenance-preserving patches.
# Failed splits remain diagnosable instead of disappearing from the model.
def _build_split_patches(model, splitters, failed_records):
    diagnostics = []
    patches = []
    tolerance = model.context.geometry_tolerance
    for entity in model.entities:
        for component in entity.components:
            for source in component.faces:
                edges = splitters.get(id(source), (None, []))[1]
                pieces, error = _split_face_once(
                    source.shape, edges, tolerance)
                if error is not None:
                    diagnostics.append(_diag(
                        FC_DIAGNOSTIC_ERROR, "surface_split_failed",
                        "Could not split a source face once with its accumulated edges: %s"
                        % error, fc_object=entity.fc_object,
                        component_index=component.index,
                        face_index=source.face_index))
                for piece in pieces:
                    piece = _align_patch_face(piece, source.shape)
                    try:
                        if float(piece.Area) <= tolerance * tolerance:
                            diagnostics.append(_diag(
                                FC_DIAGNOSTIC_WARNING, "sliver_patch",
                                "A numerical zero-area split artifact was discarded",
                                fc_object=entity.fc_object,
                                component_index=component.index,
                                face_index=source.face_index))
                            continue
                        bbox = FCBoundingBox.from_shape(piece)
                    except (AttributeError, RuntimeError, TypeError, ValueError):
                        continue
                    patch = FCSurfacePatch(
                        piece, entity, component, source, len(patches), bbox)
                    if id(source) in failed_records:
                        patch.problem_codes.append("surface_operation_failed")
                    for item in component.diagnostics:
                        if (item.severity == FC_DIAGNOSTIC_ERROR and
                                item.code not in patch.problem_codes):
                            patch.problem_codes.append(item.code)
                    try:
                        patch.center, patch.normal = _face_center_normal(piece)
                    except (AttributeError, RuntimeError, TypeError,
                            ValueError) as normal_error:
                        diagnostics.append(_diag(
                            FC_DIAGNOSTIC_ERROR, "unresolved_orientation",
                            "Could not establish a patch normal: %s" %
                            normal_error, patch))
                    patches.append(patch)
    return patches, diagnostics


# Material resolution -----------------------------------------------------
# Classify a probe against candidate dielectric solids, selecting the innermost
# containing region and falling back to the document background.
def _point_material(point, dielectric_solids, background, tolerance,
                    diagnostics, patch):
    inside = []
    boundary = []
    for classifier, entity in dielectric_solids:
        if not classifier.bbox.contains_point(point, tolerance):
            continue
        state = classifier.classify_point(point, tolerance)
        item = (float(entity.inner_permittivity), classifier, entity)
        if state == FC_POINT_INSIDE:
            inside.append(item)
        elif state == FC_POINT_BOUNDARY:
            boundary.append(item)
    candidates = inside or boundary
    if not candidates:
        return float(background), []
    values = {round(item[0], 12) for item in candidates}
    chosen = min(candidates, key=lambda item: _bbox_volume(item[1].bbox))
    if len(values) > 1:
        # Nested dielectric volumes are valid: the smallest containing region
        # is the local material. Partial overlaps with different values are
        # ambiguous and remain an explicit error.
        incompatible = [
            item for item in candidates if item is not chosen and
            not _bbox_contains_box(
                item[1].bbox, chosen[1].bbox, tolerance)]
        if incompatible:
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_ERROR, "incompatible_dielectric_volumes",
                "Partially overlapping dielectric volumes assign different permittivities",
                patch, details={
                    "materials": sorted(values),
                    "objects": [getattr(item[2].fc_object, "Name", None)
                                for item in candidates]}))
    return chosen[0], candidates


def _inside_entity_conductor(point, entity, tolerance):
    for classifier in entity.classifier_solids:
        state = classifier.classify_point(point, tolerance)
        if state in (FC_POINT_INSIDE, FC_POINT_BOUNDARY):
            return True
    return False


# Probe both normal sides of each patch, then assign conductor surroundings or
# ordered dielectric permittivities according to object orientation.
def _resolve_patch_semantics(model, patches):
    diagnostics = []
    tolerance = model.context.geometry_tolerance
    background = model.context.space_permittivity
    conductor_entities = [
        entity for entity in model.entities
        if entity.kind == "FCConductor" and entity.classifier_solids]
    dielectric_solids = [
        (classifier, entity)
        for entity in model.entities if entity.kind == "FCDielectric"
        for classifier in entity.classifier_solids]

    for patch in patches:
        if patch.normal is None:
            continue
        distance = max(
            tolerance * 10.0, patch.bbox.diagonal * 1.0e-6, 1.0e-9)
        plus = patch.center + patch.normal * distance
        minus = patch.center - patch.normal * distance
        plus_perm, plus_sources = _point_material(
            plus, dielectric_solids, background, tolerance,
            diagnostics, patch)
        minus_perm, minus_sources = _point_material(
            minus, dielectric_solids, background, tolerance,
            diagnostics, patch)

        if patch.entity.kind == "FCConductor":
            if patch.entity.classifier_solids:
                if (_inside_entity_conductor(plus, patch.entity, tolerance) and
                        _inside_entity_conductor(
                            minus, patch.entity, tolerance)):
                    patch.removed = True
                    continue
                patch.surrounding_permittivity = plus_perm
            elif plus_sources or minus_sources:
                if not _permittivity_equal(plus_perm, minus_perm):
                    diagnostics.append(_diag(
                        FC_DIAGNOSTIC_ERROR,
                        "unsupported_conductor_dielectric_coincidence",
                        "A zero-thickness conductor lies on a dielectric discontinuity; FastCap B elements are unsupported",
                        patch, details={
                            "side_permittivities":
                            (minus_perm, plus_perm)}))
                patch.surrounding_permittivity = (
                    plus_perm if plus_sources else minus_perm)
            else:
                patch.surrounding_permittivity = float(
                    patch.entity.default_permittivity)
            continue

        # Surface fragmentation isolates the footprint where a solid conductor
        # crosses a dielectric boundary. If probes on both sides of one such
        # dielectric fragment lie in the same logical conductor, the interface
        # is buried in metal and must not generate an overlapping solver panel.
        if any(
                _inside_entity_conductor(plus, conductor, tolerance) and
                _inside_entity_conductor(minus, conductor, tolerance)
                for conductor in conductor_entities):
            patch.removed = True
            continue

        own_solid = patch.source_face.classifier_solid is not None
        patch.outer_permittivity = (
            plus_perm if plus_sources else
            float(patch.entity.outer_permittivity))
        patch.inner_permittivity = (
            minus_perm if (minus_sources or own_solid) else
            float(patch.entity.inner_permittivity))
        if _permittivity_equal(
                patch.inner_permittivity, patch.outer_permittivity):
            patch.removed = True
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_WARNING, "redundant_dielectric_interface",
                "A dielectric patch has equal material on both sides and was removed",
                patch))
    return diagnostics


def _patch_semantics_key(patch):
    return (
        patch.entity.kind,
        None if patch.surrounding_permittivity is None else
        round(patch.surrounding_permittivity, 12),
        None if patch.inner_permittivity is None else
        round(patch.inner_permittivity, 12),
        None if patch.outer_permittivity is None else
        round(patch.outer_permittivity, 12))


def _coplanar_same_support(first, second, tolerance):
    if first.normal is None or second.normal is None:
        return False
    if first.normal.cross(second.normal).Length > 1.0e-8:
        return False
    return abs(_dot(second.center - first.center, first.normal)) <= tolerance


# Merge only same-support coplanar patches with identical semantics, and never
# cross a protected edge introduced by a meaningful surface interaction.
def _merge_redundant_coplanar_patches(patches, protected_sources,
                                       tolerance):
    """Merge only un-split coplanar neighbors with identical EM semantics."""
    diagnostics = []
    candidates = [
        patch for patch in patches
        if (not patch.removed and id(patch.source_face) not in
            protected_sources and _is_planar(patch.shape, tolerance))]
    index = FCBoundingBoxIndex(candidates)
    parent = {id(patch): patch for patch in candidates}

    def root(patch):
        while parent[id(patch)] is not patch:
            parent[id(patch)] = parent[id(parent[id(patch)])]
            patch = parent[id(patch)]
        return patch

    for first, second in index.candidate_pairs(tolerance=tolerance):
        if (first.entity is not second.entity or
                _patch_semantics_key(first) !=
                _patch_semantics_key(second) or
                not _coplanar_same_support(first, second, tolerance) or
                not _share_topological_edge(first.shape, second.shape)):
            continue
        first_root, second_root = root(first), root(second)
        if first_root is not second_root:
            parent[id(second_root)] = first_root

    groups = {}
    for patch in candidates:
        groups.setdefault(id(root(patch)), []).append(patch)
    for group in groups.values():
        if len(group) < 2:
            continue
        shapes = [patch.shape for patch in group]
        try:
            fused = shapes[0].multiFuse(shapes[1:]).removeSplitter()
            faces = list(getattr(fused, "Faces", []))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            continue
        if len(faces) != 1:
            continue
        source_area = sum(float(patch.shape.Area) for patch in group)
        if abs(float(faces[0].Area) - source_area) > max(
                tolerance * tolerance, source_area * 1.0e-9):
            continue
        keeper = group[0]
        keeper.shape = _align_patch_face(faces[0], keeper.shape)
        keeper.bbox = FCBoundingBox.from_shape(keeper.shape)
        try:
            keeper.center, keeper.normal = _face_center_normal(
                keeper.shape)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            continue
        for redundant in group[1:]:
            redundant.removed = True
        diagnostics.append(_diag(
            FC_DIAGNOSTIC_WARNING, "coplanar_subdivision_merged",
            "%d redundant coplanar patches with identical electromagnetic semantics were merged"
            % len(group), keeper))
    return diagnostics


# Decide whether equivalent coincident interfaces collapse, both survive, or
# form an invalid conflict based on entity kind and resolved side materials.
def _coincident_patch_action(first, second, common_area, tolerance,
                             diagnostics):
    if common_area <= tolerance * tolerance:
        return
    first_kind, second_kind = first.entity.kind, second.entity.kind
    if first_kind == second_kind == "FCConductor":
        if first.entity.fc_object is second.entity.fc_object:
            second.removed = True
            return
        diagnostics.append(_diag(
            FC_DIAGNOSTIC_ERROR, "different_conductors_overlap",
            "Different conductors occupy coincident surface area", first,
            details={"other_object":
                     getattr(second.entity.fc_object, "Name", None),
                     "area": common_area}))
        second.problem_codes.append("different_conductors_overlap")
        return

    if first_kind == second_kind == "FCDielectric":
        first_pair = (first.inner_permittivity, first.outer_permittivity)
        second_pair = (second.inner_permittivity, second.outer_permittivity)
        compatible = (
            all(value is not None for value in first_pair + second_pair) and
            (all(_permittivity_equal(a, b)
                 for a, b in zip(first_pair, second_pair)) or
             (_permittivity_equal(first_pair[0], second_pair[1]) and
              _permittivity_equal(first_pair[1], second_pair[0]))))
        if compatible:
            second.removed = True
        else:
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_ERROR, "incompatible_dielectric_definitions",
                "Coincident dielectric interfaces define incompatible materials",
                first, details={
                    "other_object":
                    getattr(second.entity.fc_object, "Name", None),
                    "area": common_area}))
            second.problem_codes.append(
                "incompatible_dielectric_definitions")
        return

    conductor = first if first_kind == "FCConductor" else second
    dielectric = second if conductor is first else first
    zero_thickness = conductor.source_face.classifier_solid is None
    discontinuity = (
        dielectric.inner_permittivity is not None and
        dielectric.outer_permittivity is not None and
        not _permittivity_equal(
            dielectric.inner_permittivity,
            dielectric.outer_permittivity))
    if zero_thickness and discontinuity:
        diagnostics.append(_diag(
            FC_DIAGNOSTIC_ERROR,
            "unsupported_conductor_dielectric_coincidence",
            "A zero-thickness conductor is coincident with a dielectric discontinuity; the required B element is unsupported",
            conductor, details={
                "dielectric_object":
                getattr(dielectric.entity.fc_object, "Name", None),
                "area": common_area}))
        dielectric.problem_codes.append(
            "unsupported_conductor_dielectric_coincidence")
    else:
        # A solid conductor replaces the material on its interior side, so a
        # coincident dielectric interface carries no independent unknown.
        dielectric.removed = True


def _patch_boundary_deviation(edge, patch):
    """Maximum sampled distance from an intersection edge to a face rim.

    OCC edge-to-edge distToShape can stall on toroidal B-spline intersections.
    Vertex-to-edge distances are fast for the same geometry. Testing points
    along the edge also avoids mistaking one endpoint contact for an edge that
    lies entirely on the patch boundary (the old minimum-distance test did).
    """
    try:
        boundary_edges = list(patch.shape.Edges)
        if not boundary_edges:
            return float("inf")
        samples = edge.discretize(Number=7)
        return max(
            min(float(Part.Vertex(point).distToShape(boundary)[0])
                for boundary in boundary_edges)
            for point in samples)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return float("inf")


# Near-but-disjoint boundaries often indicate an accidental CAD sliver; report
# them without healing because even a small physical gap can be intentional.
def _diagnose_tiny_gaps(patches, tolerance):
    """Warn about near-contact geometry without moving or deleting it."""
    diagnostics = []
    active = [patch for patch in patches if not patch.removed]
    index = FCBoundingBoxIndex(active)
    for first, second in index.candidate_pairs(
            tolerance=tolerance * 10.0):
        if first.bbox.overlaps(second.bbox, tolerance):
            continue
        try:
            distance = float(first.shape.distToShape(second.shape)[0])
        except (AttributeError, RuntimeError, TypeError, ValueError):
            continue
        if tolerance < distance < tolerance * 10.0:
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_WARNING, "suspicious_tiny_gap",
                "A physical gap close to GeometryTolerance was preserved",
                first, details={
                    "distance": distance,
                    "other_object":
                    getattr(second.entity.fc_object, "Name", None)}))
            if "suspicious_tiny_gap" not in second.problem_codes:
                second.problem_codes.append("suspicious_tiny_gap")
    return diagnostics


# Apply coincident-surface actions before discretization so duplicate solver
# elements cannot be hidden by later panel-level validation.
def _resolve_coincident_and_validate_surfaces(patches, tolerance):
    diagnostics = []
    active = [patch for patch in patches if not patch.removed]
    index = FCBoundingBoxIndex(active)
    for first, second in index.candidate_pairs(tolerance=tolerance):
        if first.removed or second.removed:
            continue
        try:
            common = first.shape.common(second.shape, tolerance)
            common_faces = [face for face in getattr(common, "Faces", [])
                            if float(face.Area) > tolerance * tolerance]
        except (AttributeError, RuntimeError, TypeError, ValueError) as error:
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_ERROR, "surface_validation_failed",
                "OCC could not validate resolved patches: %s" % error,
                first))
            second.problem_codes.append("surface_validation_failed")
            continue
        if common_faces:
            area = sum(float(face.Area) for face in common_faces)
            area_tolerance = max(
                tolerance * tolerance, area * 1.0e-9)
            complete_overlap = (
                abs(float(first.shape.Area) - area) <= area_tolerance and
                abs(float(second.shape.Area) - area) <= area_tolerance)
            if not complete_overlap:
                diagnostics.append(_diag(
                    FC_DIAGNOSTIC_ERROR, "positive_area_overlap",
                    "Resolved patches retain a partial positive-area overlap",
                    first, details={
                        "other_object":
                        getattr(second.entity.fc_object, "Name", None),
                        "area": area}))
                second.problem_codes.append("positive_area_overlap")
                continue
            _coincident_patch_action(
                first, second, area, tolerance, diagnostics)
            continue
        try:
            sections = list(
                getattr(first.shape.section(
                    second.shape, tolerance), "Edges", []))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            sections = []
        crossing = []
        for edge in sections:
            # OCC section curves may carry a looser approximation tolerance
            # than the document's geometric comparison tolerance.
            edge_tolerance = max(
                tolerance, float(getattr(edge, "Tolerance", tolerance)))
            if (_patch_boundary_deviation(edge, first) > edge_tolerance or
                    _patch_boundary_deviation(edge, second) > edge_tolerance):
                crossing.append(edge)
        if crossing:
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_ERROR, "remaining_surface_crossing",
                "Resolved surfaces still cross away from conformal boundaries",
                first, details={
                    "other_object":
                    getattr(second.entity.fc_object, "Name", None),
                    "edge_count": len(crossing)}))
            second.problem_codes.append("remaining_surface_crossing")
    return diagnostics


# Shared-topology preparation ---------------------------------------------
# A geometric touch is enough to put patches in the same Boolean/meshing
# island.  The subsequent OCC operation, rather than coordinate rounding,
# establishes the common edge and vertex identities required by Netgen.
def _patches_touch(first, second, tolerance):
    if not first.bbox.overlaps(second.bbox, tolerance):
        return False
    if (_share_topological_edge(first.shape, second.shape) or
            _share_topological_vertex(first.shape, second.shape)):
        return True
    try:
        # A whole-face distance can stall on toroidal B-spline boundaries.
        # Section detects edge and point contacts without solving that
        # expensive global minimum-distance problem. A coincident face may
        # have no section vertices, so retain a Boolean common fallback.
        section = first.shape.section(second.shape, tolerance)
        if section.Edges or section.Vertexes:
            return True
        common = first.shape.common(second.shape, tolerance)
        return bool(common.Faces or common.Edges or common.Vertexes)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return False


def _share_topological_vertex(first, second):
    buckets = {}
    for vertex in first.Vertexes:
        buckets.setdefault(_shape_hash(vertex), []).append(vertex)
    for vertex in second.Vertexes:
        if any(_same_shape(vertex, candidate)
               for candidate in buckets.get(_shape_hash(vertex), ())):
            return True
    return False


def _connected_patch_groups(patches, tolerance):
    """Return geometry-connected groups without joining disjoint FC objects."""
    parent = list(range(len(patches)))
    position = {id(patch): index for index, patch in enumerate(patches)}

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    index = FCBoundingBoxIndex(patches)
    for first, second in index.candidate_pairs(tolerance=tolerance):
        if not _patches_touch(first, second, tolerance):
            continue
        first_root = root(position[id(first)])
        second_root = root(position[id(second)])
        if first_root != second_root:
            parent[second_root] = first_root

    groups = {}
    for item_index, patch in enumerate(patches):
        groups.setdefault(root(item_index), []).append(patch)
    return list(groups.values())


def _fragment_face_record(source, face, index):
    """Copy one Boolean fragment while retaining its EM and CAD provenance."""
    aligned = _align_patch_face(face, source.shape)
    result = FCSurfacePatch(
        aligned, source.entity, source.component, source.source_face, index,
        FCBoundingBox.from_shape(aligned),
        inner_permittivity=source.inner_permittivity,
        outer_permittivity=source.outer_permittivity,
        surrounding_permittivity=source.surrounding_permittivity,
        problem_codes=list(source.problem_codes))
    result.center, result.normal = _face_center_normal(aligned)
    return result


def _mapped_faces(mapped):
    """Flatten one generalFuse history entry to unique positive-area faces."""
    faces = []
    for shape in _flatten_shapes(mapped):
        if getattr(shape, "ShapeType", "") == "Face":
            faces.append(shape)
        else:
            faces.extend(getattr(shape, "Faces", []))
    return _unique_shapes(faces)


def _group_needs_fragmentation(group, tolerance):
    """Detect contacts that are geometric but not yet shared OCC topology."""
    index = FCBoundingBoxIndex(group)
    for first, second in index.candidate_pairs(tolerance=tolerance):
        # A shared vertex does not imply that a touching intersection edge is
        # shared; the whole group must be imprinted before meshing.
        if (_patches_touch(first, second, tolerance) and
                not _share_topological_edge(first.shape, second.shape)):
            return True
    return False


# General Fuse is an arrangement operation, not a material union: it imprints
# every intersection on every participant and its history maps the resulting
# faces back to each input patch.  This supports open surfaces and preserves
# conductor/dielectric interfaces that an indiscriminate solid fuse would erase.
def _fragment_patch_group(group, tolerance, diagnostics):
    if len(group) < 2 or not _group_needs_fragmentation(group, tolerance):
        return list(group)

    try:
        _result, history = group[0].shape.generalFuse(
            [patch.shape for patch in group[1:]], tolerance)
        history = list(history)
        if len(history) != len(group):
            raise RuntimeError(
                "OCC returned %d history entries for %d input faces" %
                (len(history), len(group)))
    except (AttributeError, ImportError, RuntimeError, TypeError,
            ValueError) as error:
        diagnostics.append(_diag(
            FC_DIAGNOSTIC_ERROR, "surface_fragmentation_failed",
            "Could not construct shared topology for an interacting surface "
            "island: %s" % error, group[0], details={
                "patch_count": len(group)}))
        return list(group)

    fragments = []
    area_tolerance = tolerance * tolerance
    for source, mapped in zip(group, history):
        source_fragments = []
        for face in _mapped_faces(mapped):
            try:
                if float(face.Area) <= area_tolerance:
                    continue
                source_fragments.append(_fragment_face_record(
                    source, face, len(fragments) + len(source_fragments)))
            except (AttributeError, RuntimeError, TypeError, ValueError):
                continue

        source_area = float(getattr(source.shape, "Area", 0.0))
        mapped_area = sum(float(item.shape.Area)
                          for item in source_fragments)
        allowed = max(area_tolerance, source_area * 1.0e-8)
        if (not source_fragments or
                abs(mapped_area - source_area) > allowed):
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_ERROR, "surface_fragmentation_incomplete",
                "Shared-topology fragmentation did not preserve the complete "
                "source patch", source, details={
                    "source_area": source_area,
                    "fragment_area": mapped_area}))
            return list(group)
        fragments.extend(source_fragments)

    # A face may legitimately appear in more than one history list only for a
    # coincident input.  Such inputs should already have been resolved; keeping
    # both would create overlapping panels, so report it explicitly.
    owners = {}
    conflicts = []
    for fragment in fragments:
        key = _shape_hash(fragment.shape)
        for previous in owners.setdefault(key, []):
            if (_same_shape(fragment.shape, previous.shape) and
                    fragment.entity is not previous.entity):
                conflicts.append((fragment, previous))
        owners[key].append(fragment)
    if conflicts:
        objects = sorted({
            (getattr(item.entity.fc_object, "Name", None) or
             "<unnamed>")
            for pair in conflicts for item in pair})
        diagnostics.append(_diag(
            FC_DIAGNOSTIC_ERROR, "ambiguous_fragment_ownership",
            "Boolean fragments remain owned by more than one resolved FC "
            "surface", conflicts[0][0], details={
                "fragment_count": len(conflicts),
                "objects": objects}))
    return fragments


def _island_shape(patches):
    """Build an open/closed shell when valid, otherwise a shared-face compound."""
    faces = [patch.shape for patch in patches]
    try:
        shell = Part.makeShell(faces)
        if (len(getattr(shell, "Faces", [])) == len(faces) and
                shell.isValid()):
            return shell
    except (AttributeError, RuntimeError, TypeError, ValueError):
        pass
    return Part.makeCompound(faces)


def _patch_bbox_union(patches):
    bbox = patches[0].bbox
    for patch in patches[1:]:
        bbox = bbox.union(patch.bbox)
    return bbox


def _prepare_meshing_islands(patches, tolerance, diagnostics):
    """Fragment interacting 3D patches and assemble one Netgen shape per island."""
    inactive = [patch for patch in patches if patch.removed]
    active = [patch for patch in patches if not patch.removed]
    resolved = []
    islands = []
    for group in _connected_patch_groups(active, tolerance):
        fragments = _fragment_patch_group(group, tolerance, diagnostics)
        try:
            shape = _island_shape(fragments)
            bbox = _patch_bbox_union(fragments)
        except (AttributeError, RuntimeError, TypeError, ValueError) as error:
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_ERROR, "meshing_island_failed",
                "Could not assemble a shared-topology meshing island: %s" %
                error, fragments[0]))
            shape = Part.makeCompound(
                [patch.shape for patch in fragments])
            bbox = _patch_bbox_union(fragments)
        islands.append(FCMeshingIsland(
            shape, fragments, len(islands), bbox))
        resolved.extend(fragments)

    result = inactive + resolved
    for index, patch in enumerate(result):
        patch.index = index
    return result, islands

def _is_planar(face, tolerance):
    try:
        return bool(face.isPlanar(tolerance))
    except TypeError:
        try:
            return bool(face.isPlanar())
        except (AttributeError, RuntimeError):
            pass
    except (AttributeError, RuntimeError):
        pass
    return "Plane" in type(getattr(face, "Surface", None)).__name__


# FastCap quads must be sufficiently planar, convex, and well conditioned; bad
# four-corner candidates fall back to triangles.
def _good_planar_quad(points, tolerance):
    """Accept only ordered, strictly convex four-vertex panel loops."""
    if len(points) != 4:
        return False
    normal = (points[1] - points[0]).cross(points[2] - points[0])
    if normal.Length <= tolerance * tolerance:
        return False
    axis = max(range(3), key=lambda index: abs(
        (normal.x, normal.y, normal.z)[index]))
    projected = [tuple(value for index, value in enumerate(
        (point.x, point.y, point.z)) if index != axis) for point in points]
    turns = []
    for index in range(4):
        first = projected[index]
        second = projected[(index + 1) % 4]
        third = projected[(index + 2) % 4]
        turn = ((second[0] - first[0]) * (third[1] - second[1]) -
                (second[1] - first[1]) * (third[0] - second[0]))
        if abs(turn) <= tolerance * tolerance:
            return False
        turns.append(turn)
    return all(turn > 0.0 for turn in turns) or all(
        turn < 0.0 for turn in turns)


def _ordered_outer_points(face):
    try:
        vertices = list(face.OuterWire.OrderedVertexes)
    except (AttributeError, RuntimeError, TypeError):
        vertices = list(getattr(face, "Vertexes", []))
    return [vertex.Point for vertex in vertices]


def _collapse_polygon(points, tolerance):
    result = []
    for point in points:
        if not result or _distance(point, result[-1]) > tolerance:
            result.append(point)
    if len(result) > 1 and _distance(result[0], result[-1]) <= tolerance:
        result.pop()
    changed = True
    while changed and len(result) > 3:
        changed = False
        for index in range(len(result)):
            previous = result[index - 1]
            current = result[index]
            following = result[(index + 1) % len(result)]
            first = current - previous
            second = following - current
            if (first.Length <= tolerance or second.Length <= tolerance or
                    first.cross(second).Length <=
                    tolerance * max(first.Length, second.Length)):
                result.pop(index)
                changed = True
                break
    return result


def _panel_edge_lengths(points):
    vectors = [_tuple_vector(point) for point in points]
    return [_distance(vectors[index], vectors[(index + 1) % len(vectors)])
            for index in range(len(vectors))]


# Recursively split the longest edge until no panel edge exceeds the requested
# maximum, preserving source orientation in the emitted triangles.
def _subdivide_triangle(points, maximum):
    pending = [tuple(points)]
    result = []
    while pending:
        triangle = pending.pop()
        lengths = _panel_edge_lengths(triangle)
        longest = max(lengths)
        if maximum <= 0.0 or longest <= maximum:
            result.append(triangle)
            continue
        edge_index = lengths.index(longest)
        a = _tuple_vector(triangle[edge_index])
        b = _tuple_vector(triangle[(edge_index + 1) % 3])
        c = triangle[(edge_index + 2) % 3]
        midpoint = _vector_tuple((a + b) * 0.5)
        pending.append((triangle[edge_index], midpoint, c))
        pending.append((midpoint, triangle[(edge_index + 1) % 3], c))
    return result


def _orient_panel_points(points, normal):
    if len(points) < 3 or normal is None:
        return tuple(points)
    vectors = [_tuple_vector(point) for point in points]
    winding = (vectors[1] - vectors[0]).cross(vectors[2] - vectors[0])
    if winding.Length > 1.0e-15 and _dot(winding, normal) < 0.0:
        return tuple(reversed(points))
    return tuple(points)


def _interpolate_quad(points, u, v):
    p0, p1, p2, p3 = [_tuple_vector(point) for point in points]
    value = (p0 * ((1.0 - u) * (1.0 - v)) +
             p1 * (u * (1.0 - v)) +
             p2 * (u * v) +
             p3 * ((1.0 - u) * v))
    return _vector_tuple(value)


# Bilinear subdivision controls both edge length and aspect ratio, producing a
# regular grid whose winding follows the original four-corner patch.
def _subdivide_quad(points, maximum, aspect_limit):
    lengths = _panel_edge_lengths(points)
    u_length = max(lengths[0], lengths[2])
    v_length = max(lengths[1], lengths[3])
    if maximum > 0.0:
        u_count = max(1, int(math.ceil(u_length / maximum)))
        v_count = max(1, int(math.ceil(v_length / maximum)))
    else:
        minimum = min(u_length, v_length)
        if minimum <= 1.0e-15:
            return [tuple(points)]
        ratio = max(u_length, v_length) / minimum
        split_count = min(64, max(1, int(math.ceil(
            ratio / aspect_limit))))
        u_count = split_count if u_length > v_length else 1
        v_count = split_count if v_length > u_length else 1
    result = []
    for ui in range(u_count):
        for vi in range(v_count):
            u0, u1 = ui / u_count, (ui + 1) / u_count
            v0, v1 = vi / v_count, (vi + 1) / v_count
            result.append((
                _interpolate_quad(points, u0, v0),
                _interpolate_quad(points, u1, v0),
                _interpolate_quad(points, u1, v1),
                _interpolate_quad(points, u0, v1)))
    return result


# Return the smallest interior angle; zero also represents a degenerate triangle.
def _triangle_minimum_angle(points):
    if len(points) != 3:
        return 0.0
    vectors = [_tuple_vector(point) for point in points]
    angles = []
    for index in range(3):
        first = vectors[index - 1] - vectors[index]
        second = vectors[(index + 1) % 3] - vectors[index]
        denominator = first.Length * second.Length
        if denominator <= 1.0e-300:
            return 0.0
        cosine = max(-1.0, min(1.0, _dot(first, second) / denominator))
        angles.append(math.degrees(math.acos(cosine)))
    return min(angles)


def _indexed_triangles(vertices, facets):
    # Mesh.Topology can expose point coordinates either as FreeCAD vectors or
    # as tuples.  Normalize both representations before quality processing.
    points = []
    for vertex in vertices:
        try:
            points.append((float(vertex.x), float(vertex.y), float(vertex.z)))
        except AttributeError:
            points.append(tuple(float(value) for value in vertex[:3]))
    triangles = []
    for facet in facets:
        if len(facet) != 3:
            continue
        try:
            triangles.append(tuple(points[int(index)] for index in facet))
        except (IndexError, TypeError, ValueError):
            continue
    return triangles


def _triangle_normal(points):
    vectors = [_tuple_vector(point) for point in points]
    return (vectors[1] - vectors[0]).cross(vectors[2] - vectors[0])


def _diagonals_cross(first, second, third, fourth, normal, tolerance):
    # A legal edge flip requires the old and proposed diagonals to cross in the
    # dominant projection; this excludes concave and folded triangle pairs.
    axis = max(range(3), key=lambda index: abs(
        (normal.x, normal.y, normal.z)[index]))

    def project(point):
        return tuple(value for index, value in enumerate(point)
                     if index != axis)

    def orient(a, b, c):
        return ((b[0] - a[0]) * (c[1] - a[1]) -
                (b[1] - a[1]) * (c[0] - a[0]))

    a, b, c, d = [project(point) for point in
                  (first, second, third, fourth)]
    epsilon = max(tolerance * tolerance, 1.0e-24)
    return (orient(a, b, c) * orient(a, b, d) < -epsilon * epsilon and
            orient(c, d, a) * orient(c, d, b) < -epsilon * epsilon)


def _improve_triangle_mesh(triangles, tolerance):
    # Local max-min edge flips are the Delaunay operation needed here: they keep
    # every vertex and boundary edge fixed while replacing a poor internal
    # diagonal when the alternate one increases the smaller triangle angle.
    result = [tuple(triangle) for triangle in triangles]
    for _iteration in range(12):
        edge_users = {}
        for triangle_index, triangle in enumerate(result):
            for edge_index in range(3):
                edge = tuple(sorted((triangle[edge_index],
                                     triangle[(edge_index + 1) % 3])))
                edge_users.setdefault(edge, []).append(triangle_index)
        changed = False
        touched = set()
        for edge, users in edge_users.items():
            if len(users) != 2 or any(index in touched for index in users):
                continue
            first_index, second_index = users
            first, second = result[first_index], result[second_index]
            opposite_first = next((point for point in first
                                   if point not in edge), None)
            opposite_second = next((point for point in second
                                    if point not in edge), None)
            if (opposite_first is None or opposite_second is None or
                    opposite_first == opposite_second):
                continue
            first_normal = _triangle_normal(first)
            second_normal = _triangle_normal(second)
            if (first_normal.Length <= tolerance * tolerance or
                    second_normal.Length <= tolerance * tolerance):
                continue
            first_normal.normalize()
            second_normal.normalize()
            if _dot(first_normal, second_normal) < 0.5:
                continue
            reference_normal = first_normal + second_normal
            if reference_normal.Length <= 1.0e-15 or not _diagonals_cross(
                    edge[0], edge[1], opposite_first, opposite_second,
                    reference_normal, tolerance):
                continue
            reference_normal.normalize()
            candidate_first = _orient_panel_points(
                (opposite_first, opposite_second, edge[0]), reference_normal)
            candidate_second = _orient_panel_points(
                (opposite_second, opposite_first, edge[1]), reference_normal)
            current_quality = min(_triangle_minimum_angle(first),
                                  _triangle_minimum_angle(second))
            candidate_quality = min(
                _triangle_minimum_angle(candidate_first),
                _triangle_minimum_angle(candidate_second))
            if candidate_quality <= current_quality + 1.0e-9:
                continue
            result[first_index] = candidate_first
            result[second_index] = candidate_second
            touched.update(users)
            changed = True
        if not changed:
            break
    return result


def _tessellation_quality(triangles):
    return (min((_triangle_minimum_angle(triangle)
                 for triangle in triangles), default=-1.0),
            -len(triangles))


# Interpret the FC curvature tolerance as the dimensionless ratio between the
# permitted sagitta and the smallest principal radius of the curved surface.
# For N segments per radius, the small-angle chord approximation is
#
#     sagitta ~= Rmin / (8 * N**2).
#
# Since relative_deviation = sagitta / Rmin, Rmin cancels and gives
# N ~= sqrt(1 / (8 * relative_deviation)).  Consequently no sampling of the
# face curvature is needed merely to convert the relative control to Netgen's
# SegPerRadius input.  This remains an approximation: trims, curvature changes,
# and the mesher's other quality controls can all alter the final deviation.
def _segments_per_radius(relative_deviation):
    relative_deviation = max(float(relative_deviation), 1.0e-15)
    return math.sqrt(1.0 / (8.0 * relative_deviation))


# Map a mesh sample back to a trimmed CAD face. Mesh.Topology stores vertices
# at single precision, so its points can lie slightly beyond a trim despite
# Netgen having placed them on that edge. Allow a few float32 ulps as well as
# the model tolerance. A triangle centroid lies on the planar chord, so it
# must still be projected to the curved support surface.
def _projected_patch_distance(point, patch, tolerance):
    try:
        u, v = patch.shape.Surface.parameter(point)
        projected = patch.shape.valueAt(u, v)
        coordinate_scale = max(abs(point.x), abs(point.y), abs(point.z))
        mesh_tolerance = max(
            tolerance * 10.0, coordinate_scale * 8.0 * 2.0 ** -23)
        if not patch.shape.isInside(
                projected, mesh_tolerance, True):
            # A rounded vertex can be on the actual CAD rim even when its
            # nearest support-surface projection falls outside the trim.
            # Limit exact point-to-edge checks to nearby edge bounding boxes.
            vertex = Part.Vertex(point)
            for boundary in patch.shape.Edges:
                bbox = boundary.BoundBox
                if not (
                        bbox.XMin - mesh_tolerance <= point.x <= bbox.XMax + mesh_tolerance and
                        bbox.YMin - mesh_tolerance <= point.y <= bbox.YMax + mesh_tolerance and
                        bbox.ZMin - mesh_tolerance <= point.z <= bbox.ZMax + mesh_tolerance):
                    continue
                distance = float(vertex.distToShape(boundary)[0])
                if distance <= mesh_tolerance:
                    return distance
            return None
        return _distance(point, projected)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None


def _triangle_patch_score(triangle, patch, tolerance, center_distance=None):
    vectors = [_tuple_vector(point) for point in triangle]
    center = sum(vectors[1:], vectors[0]) * (1.0 / 3.0)
    edge_scale = max(_panel_edge_lengths(triangle), default=0.0)
    if not patch.bbox.contains_point(
            center, max(tolerance * 10.0, edge_scale)):
        return None
    if center_distance is None:
        center_distance = _projected_patch_distance(
            center, patch, tolerance)
    if center_distance is None:
        return None
    distances = [
        _projected_patch_distance(point, patch, tolerance)
        for point in vectors]
    if any(distance is None for distance in distances):
        return None
    distances.append(center_distance)
    return max(distances), sum(distances)


def _assign_island_triangles(island, triangles, tolerance):
    """Assign complete triangles to one fragmented CAD patch."""
    assigned = []
    for triangle in triangles:
        vectors = [_tuple_vector(point) for point in triangle]
        center = sum(vectors[1:], vectors[0]) * (1.0 / 3.0)
        edge_scale = max(_panel_edge_lengths(triangle), default=0.0)
        ranked = []
        for patch in island.patches:
            if not patch.bbox.contains_point(
                    center, max(tolerance * 10.0, edge_scale)):
                continue
            distance = _projected_patch_distance(
                center, patch, tolerance)
            if distance is not None:
                ranked.append((distance, patch))
        if not ranked:
            return [], (
                "a Netgen triangle could not be attributed to any complete "
                "fragmented CAD face")
        if len(ranked) == 1:
            # A conforming mesh cannot cross this face boundary without a
            # missing shared seam, which the island validator checks below.
            # One valid projected centroid identifies this face directly.
            assigned.append((ranked[0][1], triangle))
            continue
        ranked.sort(key=lambda item: item[0])
        # Ambiguous centroids need vertex checks before choosing a patch.
        for distance, patch in ranked:
            if _triangle_patch_score(
                    triangle, patch, tolerance, distance) is not None:
                assigned.append((patch, triangle))
                break
        else:
            return [], (
                "a Netgen triangle could not be attributed to any complete "
                "fragmented CAD face")

    # Edge flips may improve triangles inside one CAD face, but must never see
    # triangles from the other side of a material or topology boundary.
    groups = {}
    for patch, triangle in assigned:
        groups.setdefault(id(patch), [patch, []])[1].append(triangle)
    improved = []
    for patch, patch_triangles in groups.values():
        improved.extend(
            (patch, triangle) for triangle in
            _improve_triangle_mesh(patch_triangles, tolerance))
    return improved, None


def _assigned_quality(assigned):
    return _tessellation_quality(
        [triangle for _patch, triangle in assigned])


def _assigned_maximum_edge(assigned):
    return max((
        max(_panel_edge_lengths(triangle), default=0.0)
        for _patch, triangle in assigned), default=0.0)


def _assigned_meets_maximum(assigned, target_solver, maximum, tolerance):
    if target_solver != "FastCap" or maximum <= 0.0:
        return True
    return _assigned_maximum_edge(assigned) <= (
        maximum + max(tolerance, maximum * 1.0e-9))


# Mesh a complete open or closed topology island with one Netgen computation.
# The strictest curvature request in the island controls its shared edges.  For
# FastCap, MaxLength is supplied to Netgen itself: independent post-subdivision
# would create nonmatching nodes along seams even if every child triangle were
# individually valid.
def _tessellate_island(island, target_solver, maximum, tolerance,
                       diagnostics):
    relative_tolerance = min(
        float(getattr(
            patch.entity.fc_object, "PanelCurvatureTolerance",
            FCPANEL_DEF_CURVATURE_TOLERANCE))
        for patch in island.patches)
    candidates = []
    failures = []
    for factor in FCPANEL_TESSELLATION_REFINEMENTS:
        try:
            import MeshPart
            relative_deviation = relative_tolerance * factor
            segments_per_radius = _segments_per_radius(
                relative_deviation)

            # GrowthRate limits adjacent size changes. SegPerEdge is Netgen's
            # edge-density preference. SegPerRadius=N follows approximately
            # sagitta/Rmin = 1/(8*N**2), using the relative FC tolerance.
            # FC panels are linear triangles, so second order and quads remain
            # disabled; Optimize enables Netgen's compiled quality pass.
            arguments = {
                "Shape": island.shape,
                "GrowthRate": FCPANEL_MESH_GROWTH_RATE,
                "SegPerEdge": FCPANEL_MESH_SEGMENTS_PER_EDGE,
                "SegPerRadius": segments_per_radius,
                "SecondOrder": FCPANEL_MESH_SECOND_ORDER,
                "Optimize": FCPANEL_MESH_OPTIMIZE,
                "AllowQuad": FCPANEL_MESH_ALLOW_QUADS,
            }
            if target_solver == "FastCap" and maximum > 0.0:
                # Netgen treats MaxLength as a sizing target rather than a
                # strict postcondition. Tighten it on later trials and measure
                # the emitted edges before accepting the island mesh.
                arguments["MaxLength"] = maximum * factor
            mesh = MeshPart.meshFromShape(**arguments)
            vertices, facets = mesh.Topology
            triangles = _indexed_triangles(vertices, facets)
            if not triangles:
                failures.append("Netgen returned no triangular facets")
                continue
            assigned, assignment_error = _assign_island_triangles(
                island, triangles, tolerance)
            if assignment_error is not None:
                failures.append(assignment_error)
                continue
            candidates.append(assigned)
            if (_assigned_quality(assigned)[0] >=
                    FCPANEL_MIN_TRIANGLE_ANGLE and
                    _assigned_meets_maximum(
                        assigned, target_solver, maximum, tolerance)):
                return assigned
        except (ImportError, AttributeError, RuntimeError, TypeError,
                ValueError) as error:
            failures.append(str(error))

    if candidates:
        compliant = [
            assigned for assigned in candidates
            if _assigned_meets_maximum(
                assigned, target_solver, maximum, tolerance)]
        pool = compliant or candidates
        best = max(pool, key=_assigned_quality)
        if not compliant and target_solver == "FastCap" and maximum > 0.0:
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_ERROR, "maximum_panel_size_exceeded",
                "Netgen could not satisfy FastCap MaxPanelSize on topology "
                "island %d" % island.index, island.patches[0], details={
                    "requested": maximum,
                    "actual": _assigned_maximum_edge(best)}))
        # Exact trim corners may make the requested 15-degree minimum
        # impossible. Preserve complete coverage and let the existing panel
        # validator identify every remaining acute triangle.
        return best

    detail = ": %s" % failures[-1] if failures else ""
    diagnostics.append(_diag(
        FC_DIAGNOSTIC_ERROR, "island_tessellation_failed",
        "MeshPart/Netgen returned no attributable panels for topology island "
        "%d%s" % (island.index, detail), island.patches[0],
        details={"patch_count": len(island.patches)}))
    return []


def _surface_normal_for_panel(face, points, fallback):
    # A single patch normal is insufficient on a curved or periodic face. Map
    # each panel center back to the supporting surface and use its local normal.
    vectors = [_tuple_vector(point) for point in points]
    center = sum(vectors[1:], vectors[0]) * (1.0 / len(vectors))
    try:
        u, v = face.Surface.parameter(center)
        normal = face.normalAt(u, v)
        if normal.Length > 1.0e-15:
            normal.normalize()
            return normal
    except (AttributeError, RuntimeError, TypeError, ValueError):
        pass
    return fallback


def _cad_edge_groups(patches):
    """Map shared OCC edge identities to their incident fragmented patches."""
    buckets = {}
    groups = []
    for patch in patches:
        seen = set()
        for edge in patch.shape.Edges:
            key = _shape_hash(edge)
            group = None
            for candidate in buckets.setdefault(key, []):
                if _same_shape(candidate[0], edge):
                    group = candidate
                    break
            if group is None:
                group = [edge, []]
                buckets[key].append(group)
                groups.append(group)
            if id(group) not in seen:
                group[1].append(patch)
                seen.add(id(group))
    return groups


def _point_on_edge_shape(point, edge_shape, tolerance):
    try:
        return float(Part.Vertex(
            _tuple_vector(point)).distToShape(edge_shape)[0]) <= tolerance
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return False


def _mesh_edge_key(first, second):
    return tuple(sorted((tuple(first), tuple(second))))


# Validate the discrete topology, not just individual triangle quality. Closed
# islands may have no one-sided mesh edge. On open islands, every one-sided
# edge must terminate on an original external CAD boundary. Each shared CAD
# edge must also be represented by at least one mesh edge used across patches.
def _validate_island_mesh(island, assigned, tolerance, diagnostics):
    edge_users = {}
    for patch, triangle in assigned:
        for index in range(3):
            first = triangle[index]
            second = triangle[(index + 1) % 3]
            edge_users.setdefault(
                _mesh_edge_key(first, second), []).append(
                    (patch, first, second))

    cad_groups = _cad_edge_groups(island.patches)
    try:
        closed = bool(island.shape.isClosed())
    except (AttributeError, RuntimeError, TypeError):
        closed = False
    external_edges = [] if closed else [
        edge for edge, users in cad_groups if len(users) == 1]
    external_shape = (
        Part.makeCompound(external_edges) if external_edges else None)
    edge_tolerance = max(
        tolerance * 10.0, island.bbox.diagonal * 1.0e-10, 1.0e-12)

    boundary_failures = []
    for users in edge_users.values():
        if len(users) != 1:
            continue
        _patch, first, second = users[0]
        allowed = (
            external_shape is not None and
            _point_on_edge_shape(
                first, external_shape, edge_tolerance) and
            _point_on_edge_shape(
                second, external_shape, edge_tolerance))
        if not allowed:
            boundary_failures.append((first, second))
    if boundary_failures:
        diagnostics.append(_diag(
            FC_DIAGNOSTIC_ERROR, "nonconforming_mesh_seam",
            "The island mesh contains one-sided edges away from an allowed "
            "open CAD boundary", island.patches[0], details={
                "edge_count": len(boundary_failures),
                "island": island.index}))

    cross_patch_edges = []
    for users in edge_users.values():
        if len({id(item[0]) for item in users}) > 1:
            cross_patch_edges.append((users[0][1], users[0][2]))
    missing = 0
    for edge, users in cad_groups:
        if len(users) < 2:
            continue
        try:
            if float(edge.Length) <= tolerance:
                continue
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass
        if not any(
                _point_on_edge_shape(
                    first, edge, edge_tolerance) and
                _point_on_edge_shape(
                    second, edge, edge_tolerance)
                for first, second in cross_patch_edges):
            missing += 1
    if missing:
        diagnostics.append(_diag(
            FC_DIAGNOSTIC_ERROR, "missing_mesh_seam",
            "Netgen did not preserve one or more shared CAD edges as "
            "cross-patch mesh edges", island.patches[0], details={
                "edge_count": missing, "island": island.index}))


def _panelize_island_3d(island, target_solver, maximum, tolerance,
                        diagnostics):
    assigned = _tessellate_island(
        island, target_solver, maximum, tolerance, diagnostics)
    if not assigned:
        diagnostics.append(_diag(
            FC_DIAGNOSTIC_ERROR, "empty_island_panelization",
            "A non-empty topology island produced no solver panels",
            island.patches[0], details={"island": island.index}))
        return []

    _validate_island_mesh(
        island, assigned, tolerance, diagnostics)
    result = []
    for patch, triangle in assigned:
        normal = _surface_normal_for_panel(
            patch.shape, triangle, patch.normal)
        result.append((
            patch, FC_ELEMENT_TRIANGLE,
            _orient_panel_points(triangle, normal)))
    return result
def _edge_points_2d(edge, relative_tolerance, bbox):
    try:
        curve_name = type(edge.Curve).__name__
    except (AttributeError, RuntimeError):
        curve_name = ""
    if "Line" in curve_name:
        vertices = list(edge.Vertexes)
        return [vertices[0].Point, vertices[-1].Point]
    deflection = max(
        bbox.diagonal * relative_tolerance,
        bbox.diagonal * 1.0e-9, 1.0e-12)
    try:
        return list(edge.discretize(Deflection=deflection))
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return [vertex.Point for vertex in edge.Vertexes]


# The 2D formulation emits oriented boundary segments rather than area panels.
def _panelize_2d(patches, target_solver, maximum, diagnostics):
    if target_solver != "FasterCap":
        diagnostics.append(_diag(
            FC_DIAGNOSTIC_ERROR, "fastcap_2d_unsupported",
            "FastCap does not support the FasterCap 2D S-segment format"))
    raw = []
    seen = set()
    for patch in patches:
        relative = float(getattr(
            patch.entity.fc_object, "PanelCurvatureTolerance",
            FCPANEL_DEF_CURVATURE_TOLERANCE))
        for edge in patch.shape.Edges:
            points = _edge_points_2d(edge, relative, patch.bbox)
            for first, second in zip(points, points[1:]):
                length = _distance(first, second)
                count = (max(1, int(math.ceil(length / maximum)))
                         if target_solver == "FastCap" and maximum > 0.0
                         else 1)
                for index in range(count):
                    start = first + (second - first) * (index / count)
                    end = first + (second - first) * ((index + 1) / count)
                    point_pair = (_vector_tuple(start), _vector_tuple(end))
                    scale = max(patch.bbox.diagonal, 1.0)
                    digits = max(0, int(-math.log10(
                        max(scale * 1.0e-12, 1.0e-15))))
                    key = tuple(sorted(tuple(round(value, digits)
                                             for value in point[:2])
                                       for point in point_pair))
                    entity_key = (id(patch.entity), key)
                    if entity_key in seen:
                        continue
                    seen.add(entity_key)
                    raw.append((patch, FC_ELEMENT_SEGMENT, point_pair))
    return raw


def _segment_normal(panel):
    first, second = [_tuple_vector(point) for point in panel.points]
    tangent = second - first
    z_sign = 1.0
    if panel.patch.normal is not None and panel.patch.normal.z < 0.0:
        z_sign = -1.0
    normal = FreeCAD.Vector(
        tangent.y * z_sign, -tangent.x * z_sign, 0.0)
    if normal.Length <= 1.0e-15:
        return None
    normal.normalize()
    return normal


def _panel_normal(panel):
    points = [_tuple_vector(point) for point in panel.points]
    if len(points) < 3:
        return None
    normal = (points[1] - points[0]).cross(points[2] - points[0])
    if normal.Length <= 1.0e-15:
        return None
    normal.normalize()
    return normal


def _panel_center(panel):
    vectors = [_tuple_vector(point) for point in panel.points]
    result = FreeCAD.Vector(0.0, 0.0, 0.0)
    for vector in vectors:
        result = result + vector
    return result * (1.0 / len(vectors))


# Search progressively offset points on both sides and retain the side whose
# classified material matches the resolved dielectric boundary condition.
def _reference_for_panel(panel, tolerance):
    if panel.kind == FC_ELEMENT_SEGMENT:
        first, second = [_tuple_vector(point) for point in panel.points]
        tangent = second - first
        normal = _segment_normal(panel)
        if normal is None:
            return None
        center = (first + second) * 0.5
        return _vector_tuple(
            center + normal * max(tolerance * 10.0,
                                  tangent.Length * 0.05))
    normal = _panel_normal(panel)
    if normal is None:
        return None
    center = _panel_center(panel)
    length = max(_panel_edge_lengths(panel.points))
    return _vector_tuple(
        center + normal * max(tolerance * 10.0, length * 0.05))


def _point_on_panel_side(point, panel, side, tolerance):
    reference = _tuple_vector(point)
    if panel.kind == FC_ELEMENT_SEGMENT:
        first, second = [_tuple_vector(item) for item in panel.points]
        normal = _segment_normal(panel)
        if normal is None:
            return False
        center = (first + second) * 0.5
    else:
        normal = _panel_normal(panel)
        if normal is None:
            return False
        center = _panel_center(panel)
    signed = _dot(reference - center, normal)
    return signed > tolerance if side == "outer" else signed < -tolerance


# Group panels only after each has a usable reference, the same material pair,
# and the same reference side required by list-file D records.
def _make_dielectric_groups(panelization):
    tolerance = panelization.context.geometry_tolerance
    diagnostics = []
    panels = [panel for panel in panelization.panels
              if panel.entity.kind == "FCDielectric"]
    by_semantics = {}
    for panel in panels:
        key = (id(panel.entity), round(panel.outer_permittivity, 12),
               round(panel.inner_permittivity, 12))
        by_semantics.setdefault(key, []).append(panel)

    groups = []
    for items in by_semantics.values():
        pending = list(items)
        while pending:
            seed = pending.pop(0)
            candidates = [seed.reference_point]
            candidates.extend(panel.reference_point for panel in pending)
            candidates = [item for item in candidates if item is not None]
            best_point = None
            best_members = []
            for candidate in candidates:
                members = [panel for panel in [seed] + pending
                           if _point_on_panel_side(
                               candidate, panel, "outer", tolerance)]
                # A group grown from this seed must contain the seed. A point
                # covering more unrelated panels is not a valid replacement
                # for the seed's own OUTPERM-side reference.
                if seed not in members:
                    continue
                if len(members) > len(best_members):
                    best_point, best_members = candidate, members
            if best_point is None or seed not in best_members:
                diagnostics.append(_diag(
                    FC_DIAGNOSTIC_ERROR,
                    "dielectric_reference_point_failed",
                    "No robust reference point could be found for a dielectric panel",
                    seed.patch))
                seed.problem_codes.append(
                    "dielectric_reference_point_failed")
                continue
            pending = [panel for panel in pending
                       if panel not in best_members]
            groups.append(FCDielectricPanelGroup(
                seed.entity, best_members, seed.inner_permittivity,
                seed.outer_permittivity, best_point, "outer"))

    for index, group in enumerate(groups):
        group.index = index
        for panel in group.panels:
            panel.dielectric_group = index
    panelization.dielectric_groups = groups
    panelization.diagnostics.extend(diagnostics)


def _triangle_area(points):
    vectors = [_tuple_vector(point) for point in points]
    return (vectors[1] - vectors[0]).cross(
        vectors[2] - vectors[0]).Length * 0.5


def _quad_planarity(points):
    vectors = [_tuple_vector(point) for point in points]
    normal = (vectors[1] - vectors[0]).cross(vectors[2] - vectors[0])
    if normal.Length <= 1.0e-300:
        return float("inf")
    normal.normalize()
    return abs(_dot(vectors[3] - vectors[0], normal))


def _project_points(points):
    vectors = [_tuple_vector(point) for point in points]
    normal = (vectors[1] - vectors[0]).cross(vectors[2] - vectors[0])
    axis = max(range(3), key=lambda index: abs(
        (normal.x, normal.y, normal.z)[index]))
    return [tuple(value for index, value in enumerate(point)
                  if index != axis) for point in points]


def _segments_cross_2d(a, b, c, d, tolerance):
    def orient(p, q, r):
        return ((q[0] - p[0]) * (r[1] - p[1]) -
                (q[1] - p[1]) * (r[0] - p[0]))
    return (orient(a, b, c) * orient(a, b, d) < -tolerance and
            orient(c, d, a) * orient(c, d, b) < -tolerance)


def _panel_key(panel, tolerance):
    digits = max(0, int(-math.log10(max(tolerance, 1.0e-15))))
    coordinate_count = 2 if panel.kind == FC_ELEMENT_SEGMENT else 3
    points = tuple(sorted(tuple(round(value, digits)
                                for value in point[:coordinate_count])
                          for point in panel.points))
    return panel.kind, points


# Panel-level validation --------------------------------------------------
# Check solver representability and pairwise conflicts on the final coordinates,
# after every split, merge, tessellation, and subdivision operation.
def _validate_panels(panelization):
    diagnostics = []
    tolerance = panelization.context.geometry_tolerance
    seen = {}
    for panel in panelization.panels:
        lengths = _panel_edge_lengths(panel.points)
        minimum = min(lengths) if lengths else 0.0
        maximum = max(lengths) if lengths else 0.0
        if minimum <= tolerance:
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_ERROR, "degenerate_panel",
                "A panel contains a zero-length edge", panel.patch))
            panel.problem_codes.append("degenerate_panel")
        if panel.kind == FC_ELEMENT_SEGMENT:
            first, second = panel.points
            projected_length = math.hypot(
                second[0] - first[0], second[1] - first[1])
            if projected_length <= tolerance:
                diagnostics.append(_diag(
                    FC_DIAGNOSTIC_ERROR, "degenerate_segment",
                    "A 2D segment collapses after projection to X/Y",
                    panel.patch))
                panel.problem_codes.append("degenerate_segment")
            if abs(second[2] - first[2]) > tolerance:
                diagnostics.append(_diag(
                    FC_DIAGNOSTIC_ERROR, "non_xy_2d_geometry",
                    "A 2D segment is not parallel to the solver X/Y plane",
                    panel.patch))
                panel.problem_codes.append("non_xy_2d_geometry")
        if panel.kind == FC_ELEMENT_TRIANGLE:
            area = _triangle_area(panel.points)
            if area <= tolerance * tolerance:
                diagnostics.append(_diag(
                    FC_DIAGNOSTIC_ERROR, "degenerate_triangle",
                    "A triangular panel has zero numerical area",
                    panel.patch))
                panel.problem_codes.append("degenerate_triangle")
            minimum_angle = _triangle_minimum_angle(panel.points)
            if (area > tolerance * tolerance and minimum_angle <
                    FCPANEL_MIN_TRIANGLE_ANGLE - 1.0e-9):
                diagnostics.append(_diag(
                    FC_DIAGNOSTIC_ERROR, "thin_triangle",
                    ("A triangular panel has a minimum angle of %.6g "
                     "degrees; the required minimum is %.6g degrees") %
                    (minimum_angle, FCPANEL_MIN_TRIANGLE_ANGLE),
                    panel.patch, details={"minimum_angle": minimum_angle}))
                panel.problem_codes.append("thin_triangle")
        elif panel.kind == FC_ELEMENT_QUAD:
            area = (_triangle_area(panel.points[:3]) +
                    _triangle_area((
                        panel.points[0], panel.points[2], panel.points[3])))
            if area <= tolerance * tolerance:
                diagnostics.append(_diag(
                    FC_DIAGNOSTIC_ERROR, "degenerate_quad",
                    "A quadrilateral panel has zero numerical area",
                    panel.patch))
                panel.problem_codes.append("degenerate_quad")
            if _quad_planarity(panel.points) > tolerance:
                diagnostics.append(_diag(
                    FC_DIAGNOSTIC_ERROR, "nonplanar_quad",
                    "A quadrilateral panel is not planar",
                    panel.patch))
                panel.problem_codes.append("nonplanar_quad")
            projected = _project_points(panel.points)
            if (_segments_cross_2d(
                    projected[0], projected[1],
                    projected[2], projected[3], tolerance) or
                    _segments_cross_2d(
                        projected[1], projected[2],
                        projected[3], projected[0], tolerance)):
                diagnostics.append(_diag(
                    FC_DIAGNOSTIC_ERROR, "self_intersecting_quad",
                    "A quadrilateral panel is self-intersecting",
                    panel.patch))
                panel.problem_codes.append("self_intersecting_quad")
        if minimum > 0.0 and maximum / minimum > FCPANEL_PATHOLOGICAL_ASPECT:
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_WARNING, "pathological_panel_aspect",
                "A panel has a pathological edge-length aspect ratio",
                panel.patch, details={"aspect": maximum / minimum}))
            panel.problem_codes.append("pathological_panel_aspect")
        if 0.0 < minimum < tolerance * 10.0:
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_WARNING, "suspicious_tiny_feature",
                "A panel preserves a physical feature close to GeometryTolerance",
                panel.patch, details={"minimum_edge": minimum}))

        key = _panel_key(panel, tolerance)
        previous = seen.get(key)
        if previous is not None:
            code = ("duplicate_panel" if previous.entity is panel.entity
                    else "overlapping_panels")
            severity = (FC_DIAGNOSTIC_WARNING
                        if code == "duplicate_panel"
                        else FC_DIAGNOSTIC_ERROR)
            diagnostics.append(_diag(
                severity, code,
                "Duplicate solver panels remain after surface cleanup",
                panel.patch, details={
                    "other_object":
                    getattr(previous.entity.fc_object, "Name", None)}))
            panel.problem_codes.append(code)
            previous.problem_codes.append(code)
        else:
            seen[key] = panel

        if panel.entity.kind == "FCConductor":
            if panel.surrounding_permittivity is None:
                diagnostics.append(_diag(
                    FC_DIAGNOSTIC_ERROR, "unresolved_permittivity",
                    "A conductor panel has no surrounding permittivity",
                    panel.patch))
                panel.problem_codes.append("unresolved_permittivity")
        elif (panel.inner_permittivity is None or
              panel.outer_permittivity is None):
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_ERROR, "unresolved_permittivity",
                "A dielectric panel has unresolved side permittivity",
                panel.patch))
            panel.problem_codes.append("unresolved_permittivity")
    panelization.diagnostics.extend(diagnostics)


# Sample retained conductor solids against dielectric regions to diagnose
# impossible or inconsistent material surroundings before export.
def _validate_conductor_regions(model, patches):
    """Detect volumetric overlap without constructing conductor Booleans."""
    tolerance = model.context.geometry_tolerance
    diagnostics = []
    solids = [
        (entity, classifier)
        for entity in model.entities if entity.kind == "FCConductor"
        for classifier in entity.classifier_solids]
    index = FCBoundingBoxIndex(
        solids, bbox_getter=lambda item: item[1].bbox)
    seen = set()
    for first, second in index.candidate_pairs(tolerance=tolerance):
        first_entity, first_solid = first
        second_entity, second_solid = second
        if first_entity is second_entity:
            continue
        key = tuple(sorted((id(first_entity), id(second_entity))))
        if key in seen:
            continue

        def samples(entity, solid):
            result = []
            try:
                result.append(solid.shape.CenterOfMass)
            except (AttributeError, RuntimeError):
                pass
            result.extend(
                vertex.Point for vertex in getattr(
                    solid.shape, "Vertexes", []))
            result.extend(
                patch.center for patch in patches
                if patch.entity is entity and patch.center is not None and
                solid.bbox.contains_point(patch.center, tolerance))
            return result

        overlap = False
        for point in samples(first_entity, first_solid):
            try:
                if second_solid.shape.isInside(
                        point, tolerance, False):
                    overlap = True
                    break
            except (AttributeError, RuntimeError, TypeError, ValueError):
                continue
        if not overlap:
            for point in samples(second_entity, second_solid):
                try:
                    if first_solid.shape.isInside(
                            point, tolerance, False):
                        overlap = True
                        break
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    continue
        if not overlap:
            # Sampling rejects most pairs cheaply. The localized common is a
            # final correctness check only for surviving solid bbox pairs.
            try:
                common = first_solid.shape.common(
                    second_solid.shape, tolerance)
                overlap = float(getattr(common, "Volume", 0.0)) > (
                    tolerance * tolerance * tolerance)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                overlap = False
        if not overlap:
            continue
        seen.add(key)
        first_patch = next(
            (patch for patch in patches
             if patch.entity is first_entity), None)
        second_patch = next(
            (patch for patch in patches
             if patch.entity is second_entity), None)
        first_name = getattr(
            first_entity.fc_object, "Name", "FCConductor")
        second_name = getattr(
            second_entity.fc_object, "Name", "FCConductor")
        diagnostics.append(_diag(
            FC_DIAGNOSTIC_ERROR, "different_conductors_overlap",
            "Conductors '%s' and '%s' occupy the same physical region; "
            "remove duplicate Base assignments or combine the geometry into "
            "one FCConductor" % (first_name, second_name),
            first_patch, fc_object=first_entity.fc_object,
            details={"other_object": second_name}))
        if second_patch is not None:
            second_patch.problem_codes.append(
                "different_conductors_overlap")
    return diagnostics


# Canonical coordinate keys catch duplicate elements even when they came from
# different patches or use opposite cyclic starting vertices.
def _remove_duplicate_solver_panels(panels, tolerance, diagnostics):
    """Remove exact same-entity duplicates without hiding conflicts."""
    result = []
    seen = {}
    for panel in panels:
        semantics = (
            panel.surrounding_permittivity,
            panel.inner_permittivity, panel.outer_permittivity)
        key = (id(panel.entity), _panel_key(panel, tolerance), semantics)
        if key in seen:
            diagnostics.append(_diag(
                FC_DIAGNOSTIC_WARNING, "duplicate_panel_removed",
                "An exact duplicate solver panel was removed",
                panel.patch))
            continue
        seen[key] = panel
        panel.index = len(result)
        result.append(panel)
    return result


# Dispatch dimension-specific discretization, attach references, and preserve
# the shared 3D island topology through panel construction.
def _make_panels(model, patches, diagnostics, meshing_islands=None):
    active = [patch for patch in patches if not patch.removed]
    target = model.context.target_solver
    maximum = _solver_length_to_mm(
        getattr(model.context.solver, "MaxPanelSize", 0.0),
        model.context.units)
    panels = []

    if model.context.dimension == "2D":
        raw = _panelize_2d(active, target, maximum, diagnostics)
        for patch, kind, points in raw:
            panel = FCPanel(kind, tuple(points), patch.entity, patch,
                            len(panels))
            panels.append(panel)
    else:
        for island in meshing_islands or ():
            for patch, kind, points in _panelize_island_3d(
                    island, target, maximum,
                    model.context.geometry_tolerance, diagnostics):
                panels.append(FCPanel(
                    kind, tuple(points), patch.entity, patch, len(panels)))

    for panel in panels:
        if panel.entity.kind == "FCConductor":
            panel.surrounding_permittivity = (
                panel.patch.surrounding_permittivity)
        else:
            panel.inner_permittivity = panel.patch.inner_permittivity
            panel.outer_permittivity = panel.patch.outer_permittivity
            panel.reference_point = _reference_for_panel(
                panel, model.context.geometry_tolerance)
            if panel.reference_point is None:
                diagnostics.append(_diag(
                    FC_DIAGNOSTIC_ERROR,
                    "dielectric_reference_point_failed",
                    "Could not construct an OUTPERM-side panel reference point",
                    panel.patch))
                panel.problem_codes.append(
                    "dielectric_reference_point_failed")
        # Patch diagnostics retain source-face provenance for the report, but
        # are intentionally not inherited by every panel of that patch.  A
        # split patch (or even a whole meshing island) can be a strict
        # superset of the defective area.  Only checks that identify concrete
        # solver panels append to FCPanel.problem_codes and therefore color
        # those individual panels with BadPanelColor in the preview.
    return panels


# Orchestrate the complete explicit pipeline and publish cache/preview state
# only after a coherent FCPanelization object has been assembled.
def createFCPanelization(document=None, solver=None):
    """Run the expensive Phase 3 pipeline and install transient previews."""
    if document is None:
        document = getattr(solver, "Document", None) or FreeCAD.ActiveDocument
    clearFCPanelization(document)
    geometry = extractFCGeometry(document, solver)
    if not geometry.entities:
        raise FCPanelizationError(
            "No FCConductor or FCDielectric objects were found")
    diagnostics = list(geometry.diagnostics)
    if not any(entity.kind == "FCConductor"
               for entity in geometry.entities):
        diagnostics.append(FCDiagnostic(
            FC_DIAGNOSTIC_ERROR, "missing_conductor",
            "At least one FCConductor is required for solver export"))

    splitters, _raw_coincidences, failed, interaction_diagnostics = (
        _collect_surface_interactions(geometry))
    diagnostics.extend(interaction_diagnostics)
    patches, split_diagnostics = _build_split_patches(
        geometry, splitters, failed)
    diagnostics.extend(split_diagnostics)
    diagnostics.extend(_resolve_patch_semantics(geometry, patches))
    diagnostics.extend(_merge_redundant_coplanar_patches(
        patches, set(splitters), geometry.context.geometry_tolerance))
    diagnostics.extend(_validate_conductor_regions(geometry, patches))
    diagnostics.extend(_resolve_coincident_and_validate_surfaces(
        patches, geometry.context.geometry_tolerance))
    diagnostics.extend(_diagnose_tiny_gaps(
        patches, geometry.context.geometry_tolerance))

    meshing_islands = []
    if geometry.context.dimension == "3D":
        patches, meshing_islands = _prepare_meshing_islands(
            patches, geometry.context.geometry_tolerance,
            diagnostics)

    panels = _make_panels(
        geometry, patches, diagnostics, meshing_islands)
    panels = _remove_duplicate_solver_panels(
        panels, geometry.context.geometry_tolerance, diagnostics)
    if not panels:
        diagnostics.append(FCDiagnostic(
            FC_DIAGNOSTIC_ERROR, "empty_panelization",
            "No valid conductor or dielectric panels were generated"))
    result = FCPanelization(
        geometry.context, geometry, patches, panels, [], diagnostics,
        getFCPanelizationSignature(document, geometry.context.solver))
    _make_dielectric_groups(result)
    _validate_panels(result)

    _PANELIZATION_CACHE[id(document)] = result
    for entity in geometry.entities:
        obj = entity.fc_object
        object_panels = result.panels_for(obj)
        errors = sum(
            item.severity == FC_DIAGNOSTIC_ERROR
            for item in result.diagnostics_for(obj))
        has_panels = bool(object_panels)
        _set_status(obj, has_panels, len(object_panels), errors)
        _update_preview(obj, result)
        if has_panels:
            # The generated Coin arrays are now the FC object's frozen view.
            # Later Base edits do not rebuild them or alter source visibility.
            hideFCBase(obj.Base)
        else:
            # Never hide the only usable geometry when this object's
            # panelization failed to produce any displayable panels.
            syncFCBaseVisibility(obj)
    return result
