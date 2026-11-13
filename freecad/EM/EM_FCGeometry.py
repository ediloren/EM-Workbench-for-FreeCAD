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

from __future__ import annotations


__title__="FreeCAD E.M. Workbench FasterCap / FastCap geometry functions"
__author__ = "FastFieldSolvers - Enrico Di Lorenzo"
__url__ = "http://www.fastfieldsolvers.com"


"""Transient boundary extraction and classification for FasterCap / FastCap.

This module never creates document objects. Its entry points are called
explicitly by later solver workflows, not by FeaturePython recompute.
"""

# Geometry pipeline notes:
# - Persistent links become copied transient shapes with full source provenance.
# - Interacting solids of one conductor are union-normalized transiently so
#   buried overlap faces never enter material resolution or island meshing.
# - Solids are retained for point classification while faces form components.
# - Duplicate faces are removed before edge-connected orientation propagation.
# - Solid classifiers normalize outward orientation where a source solid exists.
# - Sweep indexes reject impossible pairs before costly OpenCascade operations;
#   candidate filtering never replaces exact topology tests.
# - GeometryTolerance compares geometry but never heals or closes model gaps.
# - Diagnostics retain object, component, source, and face locations.
# - No document object is created by extraction; the model is disposable.

from dataclasses import dataclass, field
import heapq
import math
from typing import Any, Dict, List, Optional, Tuple

import FreeCAD
import Part

from .EM_FCCommon import _fc_subshape, normalizeFCBase
from .EM_FCSolver import (EMFCSOLVER_DIMENSIONS, EMFCSOLVER_SOLVERS,
                         EMFCSOLVER_DEF_GEOMETRY_TOLERANCE)


FC_DIAGNOSTIC_INFO = "info"
FC_DIAGNOSTIC_WARNING = "warning"
FC_DIAGNOSTIC_ERROR = "error"
FC_ENTITY_TYPES = ("FCConductor", "FCDielectric")
FC_POINT_INSIDE = "inside"
FC_POINT_BOUNDARY = "boundary"
FC_POINT_OUTSIDE = "outside"
FC_POINT_UNKNOWN = "unknown"


class FCGeometryConfigurationError(ValueError):
    """Raised when the global solver context is missing or ambiguous."""

    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = list(diagnostics or [])


@dataclass
class FCDiagnostic:
    """One structured extraction or orientation diagnostic."""

    severity: str
    code: str
    message: str
    fc_object: Any = None
    component_index: Optional[int] = None
    source_object: Any = None
    source_subname: str = ""
    face_index: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def object_name(self):
        return getattr(self.fc_object, "Name", None)

    @property
    def source_name(self):
        return getattr(self.source_object, "Name", None)


@dataclass(frozen=True)
class FCBoundingBox:
    """Immutable numeric bounding box independent of document lifetime."""

    xmin: float
    ymin: float
    zmin: float
    xmax: float
    ymax: float
    zmax: float

    @classmethod
    def from_bound_box(cls, bbox):
        return cls(float(bbox.XMin), float(bbox.YMin), float(bbox.ZMin),
                   float(bbox.XMax), float(bbox.YMax), float(bbox.ZMax))

    @classmethod
    def from_shape(cls, shape):
        return cls.from_bound_box(shape.BoundBox)

    @property
    def diagonal(self):
        return math.sqrt((self.xmax - self.xmin) ** 2 +
                         (self.ymax - self.ymin) ** 2 +
                         (self.zmax - self.zmin) ** 2)

    def overlaps(self, other, tolerance=0.0):
        tol = max(0.0, float(tolerance))
        return not (
            self.xmax + tol < other.xmin or other.xmax + tol < self.xmin or
            self.ymax + tol < other.ymin or other.ymax + tol < self.ymin or
            self.zmax + tol < other.zmin or other.zmax + tol < self.zmin)

    def contains_point(self, point, tolerance=0.0):
        tol = max(0.0, float(tolerance))
        return (self.xmin - tol <= point.x <= self.xmax + tol and
                self.ymin - tol <= point.y <= self.ymax + tol and
                self.zmin - tol <= point.z <= self.zmax + tol)

    def union(self, other):
        if other is None:
            return self
        return FCBoundingBox(
            min(self.xmin, other.xmin), min(self.ymin, other.ymin),
            min(self.zmin, other.zmin), max(self.xmax, other.xmax),
            max(self.ymax, other.ymax), max(self.zmax, other.zmax))


# Broad-phase acceleration -------------------------------------------------
# Entries are sorted on X; active candidates are then checked on all axes.
# This avoids an all-pairs OCC workload without discarding exact overlaps.
class FCBoundingBoxIndex:
    """Reusable sweep-and-prune index for transient geometry records."""

    def __init__(self, items=(), bbox_getter=None):
        self._bbox_getter = bbox_getter or (lambda item: item.bbox)
        entries = []
        for serial, item in enumerate(items):
            bbox = self._bbox_getter(item)
            if bbox is not None:
                entries.append((bbox.xmin, bbox.xmax, serial, item, bbox))
        self.entries = tuple(sorted(entries, key=lambda entry: entry[0]))

    def candidate_pairs(self, other=None, tolerance=0.0):
        if other is None or other is self:
            return self._self_candidates(tolerance)
        return self._cross_candidates(other, tolerance)

    def _self_candidates(self, tolerance):
        tol = max(0.0, float(tolerance))
        active = {}
        expiry = []
        candidates = []
        for xmin, xmax, serial, item, bbox in self.entries:
            # Expire boxes left of the sweep position, allowing for tolerance.
            # Test the remaining candidates in all three axes.
            while expiry and expiry[0][0] + tol < xmin:
                _old_xmax, old_serial = heapq.heappop(expiry)
                active.pop(old_serial, None)
            for other_item, other_bbox in active.values():
                if bbox.overlaps(other_bbox, tol):
                    candidates.append((other_item, item))
            active[serial] = (item, bbox)
            heapq.heappush(expiry, (xmax, serial))
        return candidates

    def _cross_candidates(self, other, tolerance):
        tol = max(0.0, float(tolerance))
        events = [(entry[0], 0, entry) for entry in self.entries]
        events.extend((entry[0], 1, entry) for entry in other.entries)
        events.sort(key=lambda event: (event[0], event[1], event[2][2]))
        # Keep the two populations separate: this query must not return pairs
        # within either input set, unlike the self-intersection sweep above.
        active = ({}, {})
        expiry = []
        candidates = []
        unique_serial = 0
        for xmin, group, entry in events:
            while expiry and expiry[0][0] + tol < xmin:
                _old_xmax, old_id, old_group = heapq.heappop(expiry)
                active[old_group].pop(old_id, None)
            _entry_xmin, xmax, _serial, item, bbox = entry
            for other_item, other_bbox in active[1 - group].values():
                if bbox.overlaps(other_bbox, tol):
                    candidates.append((item, other_item) if group == 0
                                      else (other_item, item))
            active[group][unique_serial] = (item, bbox)
            heapq.heappush(expiry, (xmax, unique_serial, group))
            unique_serial += 1
        return candidates


@dataclass
class FCSolverContext:
    """Validated global settings used by transient geometry extraction."""

    solver: Any
    document: Any
    dimension: str
    target_solver: str
    units: str
    space_permittivity: float
    geometry_tolerance: float
    reference_conductor: Any = None


@dataclass
class FCSourceReference:
    """Resolved persistent Base entry with its transient TopoShape."""

    source_object: Any
    source_subname: str
    shape: Any
    source_path: Tuple[int, ...] = ()


@dataclass
# Classification retains original solids separately from extracted faces so
# material-side probes can distinguish inside, boundary, and outside states.
class FCClassifierSolid:
    """Retained source solid and provenance for point classification."""

    shape: Any
    source_object: Any
    source_subname: str
    source_path: Tuple[int, ...]
    bbox: FCBoundingBox

    def classify_point(self, point, tolerance):
        """Classify a point without invoking OCC outside this solid's box."""
        if not self.bbox.contains_point(point, tolerance):
            return FC_POINT_OUTSIDE
        try:
            if self.shape.isInside(point, tolerance, False):
                return FC_POINT_INSIDE
            if self.shape.isInside(point, tolerance, True):
                return FC_POINT_BOUNDARY
            return FC_POINT_OUTSIDE
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return FC_POINT_UNKNOWN


@dataclass
class FCFaceGeometry:
    """One normalized transient boundary face with full source provenance."""

    shape: Any
    source_face: Any
    source_object: Any
    source_subname: str
    source_path: Tuple[int, ...]
    source_kind: str
    classifier_solid: Optional[FCClassifierSolid]
    component_index: int
    face_index: int
    orientation_flipped: bool
    bbox: FCBoundingBox
    inner_permittivity: Optional[float] = None
    outer_permittivity: Optional[float] = None
    default_permittivity: Optional[float] = None


@dataclass
class FCGeometryComponent:
    """One edge-connected boundary component of a logical FC entity."""

    entity: Any
    index: int
    faces: List[FCFaceGeometry]
    classifier_solids: List[FCClassifierSolid]
    source_references: List[FCSourceReference]
    shell: Any
    bbox: Optional[FCBoundingBox]
    closed: bool
    orientable: bool
    orientation_reliable: bool
    diagnostics: List[FCDiagnostic] = field(default_factory=list)
    face_index: Optional[FCBoundingBoxIndex] = None

    def candidate_face_pairs(self, other, tolerance):
        return self.face_index.candidate_pairs(other.face_index, tolerance)

    def classify_point(self, point, tolerance):
        return [(solid, solid.classify_point(point, tolerance))
                for solid in self.classifier_solids]


@dataclass
class FCEntityGeometry:
    """Transient geometry for one logical FCConductor or FCDielectric."""

    fc_object: Any
    kind: str
    components: List[FCGeometryComponent]
    classifier_solids: List[FCClassifierSolid]
    source_references: List[FCSourceReference]
    bbox: Optional[FCBoundingBox]
    diagnostics: List[FCDiagnostic]
    default_permittivity: Optional[float] = None
    inner_permittivity: Optional[float] = None
    outer_permittivity: Optional[float] = None
    declared_orientation: Optional[str] = None
    component_index: Optional[FCBoundingBoxIndex] = None

    def classify_point(self, point, tolerance):
        return [(solid, solid.classify_point(point, tolerance))
                for solid in self.classifier_solids]


@dataclass
# The model centralizes reusable candidate queries and ensures each later stage
# applies the same tolerance and provenance rules.
class FCGeometryModel:
    """Complete transient Phase 2 extraction result."""

    context: FCSolverContext
    entities: List[FCEntityGeometry]
    diagnostics: List[FCDiagnostic]
    entity_index: FCBoundingBoxIndex
    component_index: FCBoundingBoxIndex

    @property
    def has_errors(self):
        return any(item.severity == FC_DIAGNOSTIC_ERROR
                   for item in self.diagnostics)

    def candidate_entity_pairs(self):
        return self.entity_index.candidate_pairs(
            tolerance=self.context.geometry_tolerance)

    def candidate_component_pairs(self, entity_a=None, entity_b=None):
        tolerance = self.context.geometry_tolerance
        if entity_a is None:
            return self.component_index.candidate_pairs(tolerance=tolerance)
        if entity_b is None:
            return entity_a.component_index.candidate_pairs(
                tolerance=tolerance)
        return entity_a.component_index.candidate_pairs(
            entity_b.component_index, tolerance)

    def candidate_face_pairs(self, component_a, component_b):
        return component_a.candidate_face_pairs(
            component_b, self.context.geometry_tolerance)

    def classify_point(self, point, entity=None):
        entities = self.entities if entity is None else [entity]
        tolerance = self.context.geometry_tolerance
        return [(item, item.classify_point(point, tolerance))
                for item in entities]


@dataclass
class _RawFace:
    face: Any
    source_object: Any
    source_subname: str
    source_path: Tuple[int, ...]
    source_kind: str
    classifier_solid: Optional[FCClassifierSolid]
    source_reference: FCSourceReference


def _diagnostic(severity, code, message, fc_object=None,
                component_index=None, raw_face=None, face_index=None,
                details=None):
    source_object = raw_face.source_object if raw_face is not None else None
    source_subname = raw_face.source_subname if raw_face is not None else ""
    return FCDiagnostic(
        severity, code, message, fc_object, component_index,
        source_object, source_subname, face_index, details or {})


def _fc_type(obj):
    return getattr(getattr(obj, "Proxy", None), "Type", None)


# Topological identity helpers --------------------------------------------
# OpenCascade bindings differ slightly across FreeCAD releases, so these
# wrappers preserve identity semantics while tolerating API variants.
def _shape_hash(shape):
    try:
        return int(shape.hashCode())
    except TypeError:
        return int(shape.hashCode(2147483647))
    except (AttributeError, RuntimeError, ValueError):
        try:
            return hash(shape)
        except TypeError:
            return id(shape)


def _is_same_shape(first, second):
    try:
        return bool(first.isSame(second))
    except (AttributeError, RuntimeError, TypeError):
        return first is second


def _reverse_shape(shape):
    try:
        return shape.reversed()
    except AttributeError:
        copied = shape.copy()
        copied.reverse()
        return copied


def _combine_bboxes(items):
    bbox = None
    for item in items:
        item_bbox = item.bbox
        bbox = item_bbox if bbox is None else bbox.union(item_bbox)
    return bbox


def _unique_identity(items):
    result = []
    identities = set()
    for item in items:
        identity = id(item)
        if identity not in identities:
            identities.add(identity)
            result.append(item)
    return result


def _validate_scalar(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise FCGeometryConfigurationError(
            "%s must be a finite positive number" % name)
    if not math.isfinite(number) or number <= 0.0:
        raise FCGeometryConfigurationError(
            "%s must be a finite positive number" % name)
    return number


# Validate all document-wide assumptions before touching source geometry; a
# failed context therefore cannot leave a partially extracted model.
def buildFCSolverContext(document=None, solver=None):
    """Build a validated solver context or raise a clear configuration error."""
    if document is None:
        document = getattr(solver, "Document", None) or FreeCAD.ActiveDocument
    if document is None:
        raise FCGeometryConfigurationError(
            "FasterCap/FastCap geometry extraction requires an active document")

    solvers = [obj for obj in getattr(document, "Objects", [])
               if _fc_type(obj) == "FCSolver"]
    if solver is None:
        if not solvers:
            raise FCGeometryConfigurationError(
                "FasterCap/FastCap geometry extraction requires one FCSolver")
        if len(solvers) != 1:
            raise FCGeometryConfigurationError(
                "FasterCap/FastCap geometry extraction found %d FCSolver objects; select one explicitly"
                % len(solvers))
        solver = solvers[0]
    elif _fc_type(solver) != "FCSolver":
        raise FCGeometryConfigurationError(
            "The supplied solver is not an FCSolver")
    elif getattr(solver, "Document", document) is not document:
        raise FCGeometryConfigurationError(
            "The supplied FCSolver belongs to a different document")

    dimension = str(getattr(solver, "Dimension", ""))
    target_solver = str(getattr(solver, "TargetSolver", ""))
    units = str(getattr(solver, "Units", ""))
    if dimension not in EMFCSOLVER_DIMENSIONS:
        raise FCGeometryConfigurationError(
            "FCSolver Dimension must be 2D or 3D")
    if target_solver not in EMFCSOLVER_SOLVERS:
        raise FCGeometryConfigurationError(
            "FCSolver TargetSolver must be FasterCap or FastCap")
    if not units:
        raise FCGeometryConfigurationError("FCSolver Units is empty")

    space_permittivity = _validate_scalar(
        getattr(solver, "SpacePermittivity", None), "SpacePermittivity")
    geometry_tolerance = _validate_scalar(
        getattr(solver, "GeometryTolerance",
                EMFCSOLVER_DEF_GEOMETRY_TOLERANCE),
        "GeometryTolerance")

    reference = getattr(solver, "ReferenceConductor", None)
    if dimension == "2D" and _fc_type(reference) != "FCConductor":
        raise FCGeometryConfigurationError(
            "A 2D FCSolver requires a valid ReferenceConductor")

    return FCSolverContext(
        solver, document, dimension, target_solver, units,
        space_permittivity, geometry_tolerance, reference)


def _is_null_or_invalid(shape):
    try:
        if shape is None or shape.isNull():
            return True
    except (AttributeError, RuntimeError):
        return shape is None
    try:
        return not shape.isValid()
    except (AttributeError, RuntimeError):
        return False


# Recursively flatten compounds and compsolids while extending source_path.
# Solids contribute both classifier volumes and boundary faces; open faces and
# shells contribute boundaries only.
def _walk_boundary_shape(shape, source_reference, path, raw_faces,
                         classifier_solids, diagnostics, fc_object):
    shape_type = getattr(shape, "ShapeType", "")
    if shape_type == "Solid":
        if _is_null_or_invalid(shape):
            diagnostics.append(_diagnostic(
                FC_DIAGNOSTIC_ERROR, "invalid_solid",
                "Solid classifier geometry is null or invalid",
                fc_object))
            return
        classifier = FCClassifierSolid(
            shape, source_reference.source_object,
            source_reference.source_subname, path,
            FCBoundingBox.from_shape(shape))
        classifier_solids.append(classifier)
        for index, face in enumerate(shape.Faces):
            raw_faces.append(_RawFace(
                face, source_reference.source_object,
                source_reference.source_subname, path + (index,),
                "solid", classifier, source_reference))
        return

    if shape_type == "Shell":
        if _is_null_or_invalid(shape):
            diagnostics.append(_diagnostic(
                FC_DIAGNOSTIC_ERROR, "invalid_shell",
                "Explicit shell is null or invalid", fc_object))
            return
        for index, face in enumerate(shape.Faces):
            raw_faces.append(_RawFace(
                face, source_reference.source_object,
                source_reference.source_subname, path + (index,),
                "surface", None, source_reference))
        return

    if shape_type == "Face":
        if _is_null_or_invalid(shape):
            diagnostics.append(_diagnostic(
                FC_DIAGNOSTIC_ERROR, "invalid_face",
                "Explicit face is null or invalid", fc_object))
            return
        raw_faces.append(_RawFace(
            shape, source_reference.source_object,
            source_reference.source_subname, path,
            "surface", None, source_reference))
        return

    if shape_type in ("Compound", "CompSolid"):
        for index, child in enumerate(shape.childShapes()):
            _walk_boundary_shape(
                child, source_reference, path + (index,), raw_faces,
                classifier_solids, diagnostics, fc_object)
        return

    diagnostics.append(_diagnostic(
        FC_DIAGNOSTIC_WARNING, "unsupported_shape",
        "Ignoring unsupported Base shape type '%s'" % shape_type,
        fc_object))


# Remove repeated topological faces within one logical object, retaining the
# first provenance record and reporting the redundant source as a diagnostic.
def _deduplicate_faces(raw_faces, diagnostics, fc_object):
    buckets = {}
    unique = []
    for raw_face in raw_faces:
        key = _shape_hash(raw_face.face)
        duplicate = None
        for existing in buckets.setdefault(key, []):
            if _is_same_shape(existing.face, raw_face.face):
                duplicate = existing
                break
        if duplicate is None:
            buckets[key].append(raw_face)
            unique.append(raw_face)
            continue
        diagnostics.append(_diagnostic(
            FC_DIAGNOSTIC_WARNING, "duplicate_face",
            "The same topological face was referenced more than once and was retained once",
            fc_object, raw_face=raw_face))
    return unique


def _edge_orientation(edge):
    orientation = str(getattr(edge, "Orientation", ""))
    if orientation == "Forward":
        return 1
    if orientation == "Reversed":
        return -1
    return None


# Map undirected topological edge identities to incident faces.  Shared-edge
# direction is evaluated separately when propagating orientation.
def _edge_groups(raw_faces):
    buckets = {}
    groups = []
    for face_index, raw_face in enumerate(raw_faces):
        seen_on_face = set()
        for edge in raw_face.face.Edges:
            key = _shape_hash(edge)
            group = None
            bucket = buckets.setdefault(key, [])
            for candidate in bucket:
                if _is_same_shape(candidate[0], edge):
                    group = candidate
                    break
            if group is None:
                group = [edge, []]
                bucket.append(group)
                groups.append(group)
            group_id = id(group)
            if group_id in seen_on_face:
                continue
            seen_on_face.add(group_id)
            group[1].append((face_index, _edge_orientation(edge)))
    return groups


# Traverse each edge-connected component, assigning local flips so adjacent
# faces traverse their shared edge in opposite directions.
def _connected_orientation(raw_faces):
    groups = _edge_groups(raw_faces)
    # Store the required relative flip across each edge, not a guessed global
    # normal; the solid classifier establishes outward direction later.
    adjacency = [[] for _raw in raw_faces]
    invalid_edges = set()
    nonmanifold_edges = set()
    for group_index, (_edge, occurrences) in enumerate(groups):
        if len(occurrences) > 2:
            nonmanifold_edges.add(group_index)
        if len(occurrences) < 2:
            continue
        first_face, first_direction = occurrences[0]
        for other_face, other_direction in occurrences[1:]:
            if first_direction is None or other_direction is None:
                invalid_edges.add(group_index)
                relation = False
            else:
                relation = first_direction == other_direction
            adjacency[first_face].append((other_face, relation, group_index))
            adjacency[other_face].append((first_face, relation, group_index))

    components = []
    flips = [None] * len(raw_faces)
    # Propagate flips through each connected component. A contradictory loop
    # stays a diagnostic instead of silently choosing one of its orientations.
    conflicts = set()
    for seed in range(len(raw_faces)):
        if flips[seed] is not None:
            continue
        flips[seed] = False
        stack = [seed]
        component = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor, relation, group_index in adjacency[current]:
                expected = bool(flips[current]) ^ relation
                if flips[neighbor] is None:
                    flips[neighbor] = expected
                    stack.append(neighbor)
                elif bool(flips[neighbor]) != expected:
                    conflicts.add(group_index)
        components.append(component)
    return components, flips, groups, invalid_edges, nonmanifold_edges, conflicts


# Probe candidates avoid relying on a single possibly singular center point;
# the caller can try several interior locations before declaring uncertainty.
def _face_probe_candidates(face):
    try:
        umin, umax, vmin, vmax = face.ParameterRange
    except (AttributeError, RuntimeError, ValueError):
        return []
    fractions = (0.5, 0.25, 0.75)
    return [(umin + (umax - umin) * fu,
             vmin + (vmax - vmin) * fv)
            for fu in fractions for fv in fractions]


# Compare small normal offsets with the source solid classifier to decide
# whether a locally consistent face still needs a component-wide outward flip.
def _solid_outward_flip(face, solid, tolerance):
    bbox = FCBoundingBox.from_shape(face)
    probe_distance = max(tolerance * 10.0, bbox.diagonal * 1.0e-7,
                         1.0e-9)
    for u, v in _face_probe_candidates(face):
        try:
            point = face.valueAt(u, v)
            try:
                if not face.isInside(point, tolerance, True):
                    continue
            except (AttributeError, RuntimeError, TypeError):
                pass
            normal = face.normalAt(u, v)
            if normal.Length <= 1.0e-15:
                continue
            normal.normalize()
            plus_inside = solid.isInside(
                point + normal * probe_distance, tolerance, False)
            minus_inside = solid.isInside(
                point - normal * probe_distance, tolerance, False)
            if plus_inside != minus_inside:
                return bool(plus_inside)
        except (AttributeError, RuntimeError, ValueError, TypeError):
            continue
    return None


# Prefer solid evidence from multiple faces and require a consistent result;
# ambiguous open surfaces retain their source orientation.
def _component_global_flip(raw_faces, indices, local_flips, tolerance):
    votes = []
    tested_solids = set()
    for face_index in indices:
        raw_face = raw_faces[face_index]
        solid = raw_face.classifier_solid
        if solid is None or id(solid) in tested_solids:
            continue
        face = (_reverse_shape(raw_face.face)
                if local_flips[face_index] else raw_face.face)
        vote = _solid_outward_flip(face, solid.shape, tolerance)
        if vote is not None:
            votes.append(vote)
            tested_solids.add(id(solid))
    if not votes:
        return None
    if any(vote != votes[0] for vote in votes[1:]):
        return "conflict"
    return votes[0]


# Resolve LinkSub entries at panelization time so the transient model reflects
# the current parametric state of every linked source object.
def _extract_sources(fc_object, diagnostics, prepared_sources=None):
    source_references = []
    raw_faces = []
    classifier_solids = []
    for source_object, subelements in normalizeFCBase(
            getattr(fc_object, "Base", [])):
        for subelement in subelements:
            try:
                if prepared_sources is None:
                    shape = _fc_subshape(source_object, subelement)
                else:
                    shape = next(shape for source, subname, shape in
                                 prepared_sources[fc_object.Name]
                                 if source is source_object and subname == subelement)
            except (AttributeError, RuntimeError, ValueError) as error:
                shape = None
                diagnostics.append(FCDiagnostic(
                    FC_DIAGNOSTIC_ERROR, "source_resolution_failed",
                    "Could not resolve Base reference: %s" % error,
                    fc_object, source_object=source_object,
                    source_subname=subelement))
                continue
            if shape is None or _is_null_or_invalid(shape):
                diagnostics.append(FCDiagnostic(
                    FC_DIAGNOSTIC_ERROR, "invalid_source",
                    "Base reference has no valid TopoShape", fc_object,
                    source_object=source_object,
                    source_subname=subelement))
                continue
            reference = FCSourceReference(
                source_object, subelement, shape)
            source_references.append(reference)
            try:
                _walk_boundary_shape(
                    shape, reference, (), raw_faces, classifier_solids,
                    diagnostics, fc_object)
            except (AttributeError, RuntimeError, ValueError, TypeError) as error:
                diagnostics.append(FCDiagnostic(
                    FC_DIAGNOSTIC_ERROR, "source_extraction_failed",
                    "Could not extract source boundary: %s" % error,
                    fc_object, source_object=source_object,
                    source_subname=subelement))
    return (source_references,
            _deduplicate_faces(raw_faces, diagnostics, fc_object),
            _unique_identity(classifier_solids))


# A logical FC material object may contain several overlapping or face-touching
# solid Bases. Normalize those volumes before boundary extraction so the
# subsequent surface pipeline sees the same exterior that a user-created Part
# Boolean union would expose. This is required for a conductor's equipotential
# boundary and equally for one dielectric material region. Disconnected solids
# remain separate output solids, and zero-thickness Base faces/shells remain.
def _best_fused_face_source(face, solid_faces, tolerance):
    face_box = FCBoundingBox.from_shape(face)
    candidates = [
        raw for raw in solid_faces
        if face_box.overlaps(
            FCBoundingBox.from_shape(raw.face), tolerance)]
    if not candidates:
        candidates = list(solid_faces)

    best = None
    best_area = -1.0
    for raw in candidates:
        try:
            common = face.common(raw.face, tolerance)
            area = sum(float(item.Area)
                       for item in getattr(common, "Faces", []))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            area = 0.0
        if area > best_area:
            best, best_area = raw, area
    if best is not None and best_area > tolerance * tolerance:
        return best

    best_distance = float("inf")
    for raw in candidates:
        try:
            distance = float(face.distToShape(raw.face)[0])
        except (AttributeError, RuntimeError, TypeError, ValueError):
            continue
        if distance < best_distance:
            best, best_distance = raw, distance
    return best


def _normalize_entity_solid_union(raw_faces, classifier_solids,
                                  tolerance, diagnostics, fc_object, kind):
    """Replace interacting solids of one FC material object by their union."""
    if len(classifier_solids) < 2:
        return raw_faces, classifier_solids

    try:
        fused = classifier_solids[0].shape.multiFuse(
            [item.shape for item in classifier_solids[1:]], tolerance)
        fused = fused.removeSplitter()
        fused_solids = list(getattr(fused, "Solids", []))
        if not fused_solids and getattr(fused, "ShapeType", "") == "Solid":
            fused_solids = [fused]
        if not fused_solids or not fused.isValid():
            raise RuntimeError("OCC returned no valid union solids")
    except (AttributeError, RuntimeError, TypeError, ValueError) as error:
        diagnostics.append(_diagnostic(
            FC_DIAGNOSTIC_WARNING, "%s_union_failed" % kind.lower(),
            "Could not normalize overlapping/touching %s solids; " % kind +
            "continuing with their individual boundaries: %s" % error,
            fc_object))
        return raw_faces, classifier_solids

    source_volume = sum(
        float(getattr(item.shape, "Volume", 0.0))
        for item in classifier_solids)
    fused_volume = sum(
        float(getattr(item, "Volume", 0.0))
        for item in fused_solids)
    volume_tolerance = max(
        tolerance ** 3, source_volume * 1.0e-10)
    changed = (
        len(fused_solids) < len(classifier_solids) or
        fused_volume < source_volume - volume_tolerance)
    if not changed:
        # Running a Boolean over truly disconnected solids adds cost and can
        # replace stable source topology without improving the solver boundary.
        return raw_faces, classifier_solids

    solid_faces = [
        raw for raw in raw_faces
        if raw.classifier_solid is not None]
    surface_faces = [
        raw for raw in raw_faces
        if raw.classifier_solid is None]
    # The union replaces filled solids only; explicitly assigned open surfaces
    # remain boundaries in their own right and must not disappear with the union.
    if not solid_faces:
        return raw_faces, classifier_solids

    normalized_faces = list(surface_faces)
    normalized_solids = []
    for solid_index, solid in enumerate(fused_solids):
        solid_box = FCBoundingBox.from_shape(solid)
        contributors = [
            raw for raw in solid_faces
            if solid_box.overlaps(
                raw.classifier_solid.bbox, tolerance)]
        source = contributors[0] if contributors else solid_faces[0]
        classifier = FCClassifierSolid(
            solid, source.source_object, source.source_subname,
            source.source_path + (solid_index,), solid_box)
        normalized_solids.append(classifier)

        for face_index, face in enumerate(solid.Faces):
            # Boolean faces no longer share the source's identity. Recover
            # provenance so later errors still point to a useful Base assignment.
            provenance = _best_fused_face_source(
                face, contributors or solid_faces, tolerance)
            if provenance is None:
                provenance = source
            normalized_faces.append(_RawFace(
                face, provenance.source_object,
                provenance.source_subname,
                provenance.source_path + (face_index,),
                "solid", classifier, provenance.source_reference))

    return (
        _deduplicate_faces(normalized_faces, diagnostics, fc_object),
        normalized_solids)


# Assemble one logical conductor or dielectric: extract, deduplicate, connect,
# orient, bound, and index its faces while retaining classifier solids.
def _build_entity(fc_object, context, prepared_sources=None):
    kind = _fc_type(fc_object)
    diagnostics = []
    source_references, raw_faces, classifier_solids = _extract_sources(
        fc_object, diagnostics, prepared_sources)
    if kind in ("FCConductor", "FCDielectric"):
        raw_faces, classifier_solids = _normalize_entity_solid_union(
            raw_faces, classifier_solids,
            context.geometry_tolerance, diagnostics, fc_object, kind)

    if not raw_faces:
        diagnostics.append(_diagnostic(
            FC_DIAGNOSTIC_ERROR, "empty_boundary",
            "FC object produced no boundary faces", fc_object))
        return FCEntityGeometry(
            fc_object, kind, [], classifier_solids, source_references,
            None, diagnostics)

    (component_indices, local_flips, groups, invalid_edges,
     nonmanifold_edges, conflicts) = _connected_orientation(raw_faces)
    # Associate topology defects with their connected component before building
    # its public records; one bad shell must not taint unrelated source pieces.
    face_to_component = {}
    for component_index, indices in enumerate(component_indices):
        for face_index in indices:
            face_to_component[face_index] = component_index

    groups_by_component = [[] for _indices in component_indices]
    for _edge, occurrences in groups:
        component_ids = {face_to_component[face_index]
                         for face_index, _direction in occurrences}
        for component_id in component_ids:
            groups_by_component[component_id].append(occurrences)

    issues_by_component = {
        index: {"invalid": False, "nonmanifold": False, "conflict": False}
        for index in range(len(component_indices))}
    for issue_name, issue_groups in (
            ("invalid", invalid_edges), ("nonmanifold", nonmanifold_edges),
            ("conflict", conflicts)):
        for group_index in issue_groups:
            for face_index, _direction in groups[group_index][1]:
                issues_by_component[face_to_component[face_index]][issue_name] = True

    components = []
    entity_orientation = str(getattr(fc_object, "Orientation", "Forward"))
    for component_index, indices in enumerate(component_indices):
        issues = issues_by_component[component_index]
        has_solid = any(raw_faces[index].classifier_solid is not None
                        for index in indices)
        orientable = not (
            issues["invalid"] or issues["nonmanifold"] or issues["conflict"])
        reliable = orientable
        global_flip = False
        component_diagnostics = []

        if has_solid:
            # Local edge consistency permits either overall direction. Use the
            # solid classifier to select outward before applying user reversal.
            outward = _component_global_flip(
                raw_faces, indices, local_flips,
                context.geometry_tolerance)
            if outward == "conflict":
                reliable = False
                component_diagnostics.append(_diagnostic(
                    FC_DIAGNOSTIC_ERROR, "solid_orientation_conflict",
                    "Classifier solids disagree on the component outward direction",
                    fc_object, component_index))
            elif outward is None:
                reliable = False
                component_diagnostics.append(_diagnostic(
                    FC_DIAGNOSTIC_WARNING, "solid_orientation_unresolved",
                    "Could not verify the component outward direction using solid classification",
                    fc_object, component_index))
            else:
                global_flip = bool(outward)
        elif kind == "FCDielectric":
            global_flip = entity_orientation == "Reversed"

        if issues["invalid"]:
            component_diagnostics.append(_diagnostic(
                FC_DIAGNOSTIC_ERROR, "unsupported_edge_orientation",
                "A shared edge has an unsupported OCC orientation",
                fc_object, component_index))
        if issues["nonmanifold"]:
            component_diagnostics.append(_diagnostic(
                FC_DIAGNOSTIC_ERROR, "nonmanifold_component",
                "More than two faces share a topological edge",
                fc_object, component_index))
        if issues["conflict"]:
            component_diagnostics.append(_diagnostic(
                FC_DIAGNOSTIC_ERROR, "nonorientable_component",
                "Face-adjacency orientation constraints are inconsistent",
                fc_object, component_index))

        component_groups = groups_by_component[component_index]
        closed = bool(component_groups) and all(
            len(occurrences) == 2 for occurrences in component_groups)

        faces = []
        for output_index, raw_index in enumerate(indices):
            raw_face = raw_faces[raw_index]
            flip = bool(local_flips[raw_index]) ^ global_flip
            oriented_face = (_reverse_shape(raw_face.face)
                             if flip else raw_face.face)
            try:
                bbox = FCBoundingBox.from_shape(oriented_face)
            except (AttributeError, RuntimeError, ValueError) as error:
                component_diagnostics.append(_diagnostic(
                    FC_DIAGNOSTIC_ERROR, "face_bbox_failed",
                    "Could not compute face bounding box: %s" % error,
                    fc_object, component_index, raw_face, output_index))
                continue
            face_record = FCFaceGeometry(
                oriented_face, raw_face.face, raw_face.source_object,
                raw_face.source_subname, raw_face.source_path,
                raw_face.source_kind, raw_face.classifier_solid,
                component_index, output_index, flip, bbox)
            if kind == "FCDielectric":
                face_record.inner_permittivity = float(
                    fc_object.InnerPermittivity)
                face_record.outer_permittivity = float(
                    fc_object.OuterPermittivity)
            else:
                face_record.default_permittivity = float(
                    fc_object.DefaultPermittivity)
            faces.append(face_record)

        normalized_shell = None
        if faces:
            try:
                normalized_shell = Part.makeShell(
                    [face.shape for face in faces])
                closed = bool(normalized_shell.isClosed())
                if not normalized_shell.isValid():
                    reliable = False
                    component_diagnostics.append(_diagnostic(
                        FC_DIAGNOSTIC_WARNING, "invalid_normalized_shell",
                        "OCC reports the normalized component shell as invalid",
                        fc_object, component_index))
            except (AttributeError, RuntimeError, ValueError, TypeError) as error:
                component_diagnostics.append(_diagnostic(
                    FC_DIAGNOSTIC_WARNING, "shell_construction_failed",
                    "Could not build the transient component shell: %s" % error,
                    fc_object, component_index))

        component_sources = _unique_identity(
            [raw_faces[index].source_reference for index in indices])
        component_solids = _unique_identity(
            [raw_faces[index].classifier_solid for index in indices
             if raw_faces[index].classifier_solid is not None])
        # "shell" is an OCC geometry object, not a subprocess shell option.
        # The below "nosec B604" is used to suppress the false positive from Bandit tool
        component = FCGeometryComponent(
            entity=None, index=component_index, faces=faces,
            classifier_solids=component_solids,
            source_references=component_sources, shell=normalized_shell,  # nosec B604
            bbox=_combine_bboxes(faces), closed=closed,
            orientable=orientable, orientation_reliable=reliable,
            diagnostics=component_diagnostics)
        component.face_index = FCBoundingBoxIndex(faces)
        components.append(component)
        diagnostics.extend(component_diagnostics)

    entity = FCEntityGeometry(
        fc_object, kind, components, classifier_solids, source_references,
        _combine_bboxes(components), diagnostics)
    if kind == "FCDielectric":
        entity.inner_permittivity = float(fc_object.InnerPermittivity)
        entity.outer_permittivity = float(fc_object.OuterPermittivity)
        entity.declared_orientation = entity_orientation
    else:
        entity.default_permittivity = float(fc_object.DefaultPermittivity)
    for component in components:
        component.entity = entity
    entity.component_index = FCBoundingBoxIndex(components)
    return entity


# Public extraction performs no Boolean splitting.  It returns oriented source
# geometry plus candidate indexes for the panelization stage.
def extractFCGeometry(document=None, solver=None, objects=None,
                      prepared_sources=None):
    """Extract a complete transient Phase 2 geometry model.

    No intersections, splitting, cleanup, tessellation, panelization, export,
    document-object creation, or document recomputes are performed.
    """
    context = buildFCSolverContext(document, solver)
    if objects is None:
        objects = [obj for obj in getattr(context.document, "Objects", [])
                   if _fc_type(obj) in FC_ENTITY_TYPES]

    if context.dimension == "2D":
        from .EM_FC2D import extractFCGeometry2D
        return extractFCGeometry2D(context, objects)

    entities = []
    diagnostics = []
    seen = set()
    for fc_object in objects:
        if id(fc_object) in seen:
            continue
        seen.add(id(fc_object))
        kind = _fc_type(fc_object)
        if kind not in FC_ENTITY_TYPES:
            diagnostics.append(_diagnostic(
                FC_DIAGNOSTIC_WARNING, "unsupported_fc_object",
                "Ignoring an object that is not FCConductor or FCDielectric",
                fc_object))
            continue
        entity = _build_entity(fc_object, context, prepared_sources)
        entities.append(entity)
        diagnostics.extend(entity.diagnostics)

    components = [component for entity in entities
                  for component in entity.components]
    return FCGeometryModel(
        context, entities, diagnostics,
        FCBoundingBoxIndex(entities),
        FCBoundingBoxIndex(components))
