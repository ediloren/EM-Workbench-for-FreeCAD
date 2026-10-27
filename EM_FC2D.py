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



__title__="FreeCAD E.M. Workbench FasterCap 2D Classes"
__author__ = "FastFieldSolvers - Enrico Di Lorenzo"
__url__ = "http://www.fastfieldsolvers.com"

"""Classes and functions to handle 2D FasterCap regions and their conformal, material-labelled contours.

The path is independent of 3D defeaturing, surface probes and meshing. A single
planar arrangement supplies both region ownership and shared boundary edges.
Edges are discretized once, then inexpensive line tests audit the final chords.
Original document geometry is never modified.
"""

from dataclasses import dataclass, field
import math

import FreeCAD as App
import Part

from EM_FCCommon import normalizeFCBase, _fc_subshape
from EM_FCGeometry import (FCBoundingBox, FCBoundingBoxIndex, FCDiagnostic,
    FCSourceReference, FCFaceGeometry, FCGeometryComponent, FCEntityGeometry,
    FCGeometryModel)


@dataclass
class _Region:
    shape: object
    entity: object
    component: object
    source: object
    bbox: object
    cells: set = field(default_factory=set)


@dataclass
class _Cell:
    shape: object
    owners: list = field(default_factory=list)
    conductor: object = None
    dielectric: object = None


def _inside_value(region):
    obj = region.entity.fc_object
    return float(obj.OuterPermittivity if obj.Orientation == "Reversed"
                 else obj.InnerPermittivity)


def _outside_value(region):
    obj = region.entity.fc_object
    return float(obj.InnerPermittivity if obj.Orientation == "Reversed"
                 else obj.OuterPermittivity)


def _error(diagnostics, code, message, obj=None):
    diagnostics.append(FCDiagnostic("error", code, message, obj))


def _source_parts(shape):
    """Filled faces/closed loops plus explicitly oriented open contour edges."""
    if shape.Solids:
        raise ValueError('Select planar cross-section faces, not whole solids')
    faces = list(shape.Faces)
    # Do not interpret the trimming wires of an existing face a second time
    # as independent contours. Only unclaimed wires/edges need conversion.
    used = [e for f in faces for e in f.Edges]
    loops, edges = [], []
    for wire in shape.Wires:
        if all(any(e.isSame(old) for old in used) for e in wire.Edges):
            continue
        used.extend(wire.Edges)
        if wire.isClosed():
            loops.append(wire)
        else:
            edges.extend(wire.OrderedEdges)
    # Part.Wire changes ownership flags on its input edges; do not share those
    # edges with the document, even for the pre-panelization orientation aid.
    loose = [e.copy() for e in shape.Edges if not any(e.isSame(old) for old in used)]
    for chain in Part.sortEdges(loose) if loose else []:
        wire = Part.Wire(chain)
        if wire.isClosed():
            loops.append(wire)
        else:
            edges.extend(wire.OrderedEdges)
    if loops:
        # Build nested loops together so inner loops remain holes, rather than
        # becoming overlapping filled faces with their own material ownership.
        faces.extend(Part.makeFace(loops, 'Part::FaceMakerBullseye').Faces)
    if not faces and not edges:
        raise ValueError('The 2D source has no faces or contour edges')
    return faces, edges


def _extract(context, objects, diagnostics):
    entities, regions = [], []
    z_level = None
    tol = context.geometry_tolerance
    for obj in objects:
        entity = FCEntityGeometry(obj, obj.Proxy.Type, [], [], [], None, [])
        entity.default_permittivity = getattr(obj, "DefaultPermittivity", None)
        entity.inner_permittivity = getattr(obj, "InnerPermittivity", None)
        entity.outer_permittivity = getattr(obj, "OuterPermittivity", None)
        entities.append(entity)
        for base, names in normalizeFCBase(obj.Base):
            for name in names:
                try:
                    shape = _fc_subshape(base, name)
                    if shape is None or shape.isNull() or not shape.isValid():
                        raise ValueError("Base geometry is empty or invalid")
                    faces, edges = _source_parts(shape)
                    reference = FCSourceReference(base, name, shape)
                    entity.source_references.append(reference)
                    for face in faces + edges:
                        is_face = face.ShapeType == 'Face'
                        box = face.BoundBox
                        if (is_face and not isinstance(face.Surface, Part.Plane)) or box.ZLength > tol:
                            raise ValueError("All 2D geometry must lie parallel to X/Y")
                        height = (box.ZMin + box.ZMax)*0.5
                        if z_level is None:
                            z_level = height
                        if abs(height-z_level) > tol:
                            raise ValueError("All 2D regions must use the same Z level")
                        face = face.copy()
                        # Remove only the accepted numerical Z discrepancy on
                        # the copy; the exported model has X/Y coordinates only.
                        face.translate(App.Vector(0, 0, z_level-height))
                        if is_face and face.normalAt(0, 0).z < 0:
                            face.reverse()
                        if (face.Area <= tol*tol if is_face else face.Length <= tol):
                            raise ValueError("A 2D source has zero area or length")
                        index = len(entity.components)
                        # Keep provenance for both kinds of source. Open edges
                        # carry a boundary condition but no filled-region flags.
                        bbox = FCBoundingBox.from_shape(face)
                        source = FCFaceGeometry(face, face, base, name, (),
                            "2D region" if is_face else "2D contour", None, index, 0, False, bbox)
                        comp = FCGeometryComponent(entity, index, [source], [],
                            [reference], face, bbox, is_face, is_face, is_face)
                        comp.face_index = FCBoundingBoxIndex([source])
                        entity.components.append(comp)
                        entity.bbox = bbox if entity.bbox is None else entity.bbox.union(bbox)
                        regions.append(_Region(face, entity, comp, source, bbox))
                except (ValueError, RuntimeError, TypeError, AttributeError) as exc:
                    _error(diagnostics, "invalid_2d_region", str(exc), obj)
        if not entity.components:
            _error(diagnostics, "empty_2d_region", "FC object has no valid 2D region", obj)
        entity.component_index = FCBoundingBoxIndex(entity.components)
    components = [c for e in entities for c in e.components]
    model = FCGeometryModel(context, entities, list(diagnostics),
        FCBoundingBoxIndex(entities), FCBoundingBoxIndex(components))
    return model, regions


def extractFCGeometry2D(context, objects):
    """Public geometry extraction uses the same planar rules as panelization."""
    return _extract(context, objects, [])[0]


def _topology_item(buckets, shape, factory):
    """OCC identity, ignoring orientation; no coordinate rounding of gaps."""
    key = shape.hashCode()
    bucket = buckets.setdefault(key, [])
    for previous, value in bucket:
        if previous.isSame(shape):
            return value
    value = factory()
    bucket.append((shape, value))
    return value


def _arrange(regions, tolerance, diagnostics):
    if len(regions) == 1:
        result = regions[0].shape
        history = [[regions[0].shape]]
    else:
        result, history = regions[0].shape.generalFuse(
            [r.shape for r in regions[1:]], tolerance)
    if len(history) != len(regions):
        raise RuntimeError("Incomplete 2D Boolean history")
    cells, buckets = [], {}
    # Boolean history, not point sampling, determines which original regions
    # own each cell. One cell may belong to several inputs before resolution.

    def new_cell(face):
        face = face if face.normalAt(0, 0).z > 0 else face.reversed()
        cell = _Cell(face)
        cells.append(cell)
        return cell

    for region, mapped in zip(regions, history):
        # FreeCAD's history lists modified images only; untouched, disjoint
        # faces can have an empty entry. Accept them only if present in output.
        if not mapped and any(f.isSame(region.shape) for f in result.Faces):
            mapped = [region.shape]
        area = 0.0
        for shape in mapped:
            for face in shape.Faces:
                if not face.isValid():
                    raise RuntimeError("Invalid face in 2D arrangement")
                cell = _topology_item(buckets, face, lambda: new_cell(face))
                if id(cell) in region.cells:
                    continue
                region.cells.add(id(cell))
                cell.owners.append(region)
                area += face.Area
        if abs(area-region.shape.Area) > max(tolerance*tolerance, region.shape.Area*1e-7):
            raise RuntimeError("2D arrangement did not preserve complete region coverage")

    reported = set()
    for cell in cells:
        # A shared cell unites pieces of one potential; different conductor
        # owners instead mean a physical short that must remain an error.
        conductors = {id(r.entity): r for r in cell.owners
                      if r.entity.kind == "FCConductor"}
        if len(conductors) > 1:
            key = tuple(sorted(conductors))
            if key not in reported:
                _error(diagnostics, "different_conductors_overlap",
                    "Different 2D conductors occupy the same area; combine them "
                    "or provide physical separation",
                    next(iter(conductors.values())).entity.fc_object)
                reported.add(key)
        cell.conductor = next(iter(conductors.values()), None)
        dielectrics = [r for r in cell.owners if r.entity.kind == "FCDielectric"]
        # Proper containment of cell sets permits nested materials. Partial
        # overlap is not nesting, even when the original bounding boxes contain.
        for i, a in enumerate(dielectrics):
            for b in dielectrics[i+1:]:
                if a.entity is b.entity:
                    continue
                if math.isclose(_inside_value(a), _inside_value(b), rel_tol=1e-12):
                    if a.cells != b.cells or math.isclose(_outside_value(a), _outside_value(b), rel_tol=1e-12):
                        continue
                if a.cells < b.cells or b.cells < a.cells:
                    continue
                key = tuple(sorted((id(a.entity), id(b.entity))))
                if key not in reported:
                    _error(diagnostics, "incompatible_dielectric_volumes",
                        "2D dielectric regions with different permittivities "
                        "partly overlap or duplicate one another", a.entity.fc_object)
                    reported.add(key)
        cell.dielectric = min(dielectrics, key=lambda r: r.shape.Area, default=None)
    return cells


def _boundaries(cells, tolerance, diagnostics):
    edges, vertices = {}, {}
    for cell in cells:
        for edge in cell.shape.Edges:
            users = _topology_item(edges, edge, list)
            users.append((cell, edge))
        if cell.conductor is not None:
            for vertex in cell.shape.Vertexes:
                users = _topology_item(vertices, vertex, dict)
                users[id(cell.conductor.entity)] = cell.conductor.entity
    reported = set()
    for bucket in vertices.values():
        for _, users in bucket:
            if len(users) > 1:
                key = tuple(sorted(users))
                if key not in reported:
                    _error(diagnostics, "different_conductors_touch",
                        "Different 2D conductors touch; combine them or add a gap",
                        next(iter(users.values())).fc_object)
                    reported.add(key)
    result = []
    for bucket in edges.values():
        for _, users in bucket:
            if len(users) > 2:
                raise RuntimeError("A planar boundary has more than two region sides")
            first, edge = users[0]
            second = users[1][0] if len(users) == 2 else None
            a, b = first.conductor, second.conductor if second else None
            # Decide ownership once per shared edge: metal replaces dielectric
            # contact segments, and internal edges of a metal region disappear.
            if a is not None and b is not None:
                continue  # Same conductor's internal edge, or already diagnosed short.
            if a is not None or b is not None:
                if b is not None:
                    first, second = second, first
                    edge = users[1][1]
                owner = first.conductor
                perm = (_inside_value(second.dielectric)
                        if second and second.dielectric else owner.entity.default_permittivity)
                result.append((edge, owner, float(perm), None, None))
                continue
            if second and second.dielectric.shape.Area < first.dielectric.shape.Area:
                first, second = second, first
                edge = users[1][1]
            owner = first.dielectric
            # An adjacent filled region gives the actual material across this
            # interface; use the object's outside value only at an exposed rim.
            inner = _inside_value(owner)
            outer = _inside_value(second.dielectric) if second else _outside_value(owner)
            if math.isclose(inner, outer, rel_tol=1e-12):
                continue
            if owner.entity.fc_object.Orientation == "Reversed":
                edge = edge.reversed()
                inner, outer = outer, inner
            result.append((edge, owner, None, inner, outer))
    return result


def _orient_fragment(edge, original):
    """Boolean history does not promise to retain the input edge direction."""
    parameter = (edge.FirstParameter + edge.LastParameter)*0.5
    point = edge.valueAt(parameter)
    tangent = original.tangentAt(original.Curve.parameter(point))
    if original.Orientation == 'Reversed':
        tangent = -tangent
    current = edge.tangentAt(parameter)
    if edge.Orientation == 'Reversed':
        current = -current
    return edge.reversed() if current.dot(tangent) < 0 else edge


def _open_boundaries(boundaries, contours, cells, tolerance, diagnostics):
    """Node open contours against all retained region boundaries once.

    Open dielectric edges are explicit two-sided interfaces, not filled regions.
    They do not infer a global material volume from an incomplete contour.
    """
    records = list(boundaries)
    for owner in contours:
        obj = owner.entity.fc_object
        edge = owner.shape
        if owner.entity.kind == 'FCConductor':
            records.append((edge, owner, float(obj.DefaultPermittivity), None, None))
        else:
            if obj.Orientation == 'Reversed':
                edge = edge.reversed()
            records.append((edge, owner, None, float(obj.InnerPermittivity),
                            float(obj.OuterPermittivity)))
    if len(records) == 1:
        result, history = records[0][0], [[records[0][0]]]
    else:
        result, history = records[0][0].generalFuse([r[0] for r in records[1:]], tolerance)
    if len(history) != len(records):
        raise RuntimeError('Incomplete open-contour Boolean history')
    fragments = {}
    # The same output edge may occur in several history entries. Preserve those
    # owners until coincident metal and dielectric conditions are compared.
    for record, images in zip(records, history):
        original = record[0]
        if not images and any(e.isSame(original) for e in result.Edges):
            images = [original]
        length = 0.
        seen = {}
        for image in images:
            for edge in image.Edges:
                marker = _topology_item(seen, edge, list)
                if marker:
                    continue
                marker.append(True)
                length += edge.Length
                directed = _orient_fragment(edge, original)
                _topology_item(fragments, edge, list).append((directed,)+record[1:])
        if abs(length-original.Length) > max(tolerance, original.Length*1e-7):
            raise RuntimeError('Open-contour splitting lost part of an edge')
    cell_boxes = [(c, FCBoundingBox.from_shape(c.shape)) for c in cells]
    resolved = []
    for bucket in fragments.values():
        for edge, users in bucket:
            midpoint = edge.valueAt((edge.FirstParameter+edge.LastParameter)*0.5)
            # All retained region boundaries have already split this edge.
            # Its midpoint can therefore classify the complete fragment.
            containing = [c for c, box in cell_boxes
                          if box.contains_point(midpoint, tolerance)
                          and c.shape.isInside(midpoint, tolerance, True)]
            metal = {id(c.conductor.entity): c.conductor for c in containing
                     if c.conductor is not None}
            conductors = [r for r in users if r[1].entity.kind == 'FCConductor']
            identities = set(metal) | {id(r[1].entity) for r in conductors}
            if len(identities) > 1:
                _error(diagnostics, 'different_conductors_overlap',
                       'An open conductor overlaps or touches another conductor',
                       users[0][1].entity.fc_object)
            # An existing filled-region metal boundary is authoritative.
            solid_boundary = next((r for r in conductors
                                   if r[1].shape.ShapeType == 'Face'), None)
            if solid_boundary is not None:
                resolved.append(solid_boundary)
                continue
            if metal:
                continue  # Open edges inside/on metal add no dielectric/sheet surface.
            if conductors:
                chosen = conductors[0]
                eps = {_inside_value(c.dielectric) for c in containing
                       if c.dielectric is not None}
                interfaces = [r for r in users if r[1].entity.kind == 'FCDielectric']
                for r in interfaces:
                    eps.update((r[3], r[4]))
                if len(eps) > 1:
                    _error(diagnostics, 'ambiguous_2d_sheet_material',
                        'A zero-thickness conductor lies on an interface between '
                        'different materials; use a finite-width conductor instead',
                        chosen[1].entity.fc_object)
                perm = next(iter(eps)) if len(eps) == 1 else chosen[2]
                resolved.append((chosen[0], chosen[1], perm, None, None))
                continue
            chosen = users[0]
            # Oppositely directed coincident edges exchange left/right sides;
            # compare their material pairs in one direction before deduplicating.
            for other in users[1:]:
                aligned = _orient_fragment(other[0], chosen[0]).Orientation == other[0].Orientation
                pair = (other[3], other[4]) if aligned else (other[4], other[3])
                if not all(math.isclose(a, b, rel_tol=1e-12)
                           for a, b in zip((chosen[3], chosen[4]), pair)):
                    _error(diagnostics, 'incompatible_dielectric_interfaces',
                        'Coincident open dielectric edges specify conflicting material sides',
                        other[1].entity.fc_object)
            if not math.isclose(chosen[3], chosen[4], rel_tol=1e-12):
                resolved.append(chosen)
    vertices = {}
    # Area tests cannot detect a short between zero-thickness conductors.
    # Shared vertices also catch crossings that the edge splitter just noded.
    for edge, owner, _, _, _ in resolved:
        if owner.entity.kind == 'FCConductor':
            for vertex in edge.Vertexes:
                _topology_item(vertices, vertex, dict)[id(owner.entity)] = owner.entity
    for bucket in vertices.values():
        for _, owners in bucket:
            if len(owners) > 1:
                _error(diagnostics, 'different_conductors_touch',
                    'Different 2D conductors touch; combine them or add a gap',
                    next(iter(owners.values())).fc_object)
    return resolved


def _points(edge, deflection, vertices):
    points = list(edge.discretize(Deflection=deflection))
    if len(points) < 2:
        raise RuntimeError("Could not discretize a 2D contour edge")
    # OCC discretization follows increasing parameters, independently of the
    # edge's orientation in the cell. Pin all endpoints to shared CAD vertices.
    for index, parameter in ((0, edge.FirstParameter), (-1, edge.LastParameter)):
        p = edge.valueAt(parameter)
        vertex = min(edge.Vertexes, key=lambda v: (v.Point-p).Length)
        points[index] = _topology_item(vertices, vertex, lambda: vertex.Point)
    if edge.Orientation == "Reversed":
        points.reverse()
    return points


def _segment_conflict(a, b, tolerance):
    """Intersecting interiors, partial overlaps and unmatched T junctions."""
    p, q = a.points
    r, s = b.points
    u = (q[0]-p[0], q[1]-p[1])
    v = (s[0]-r[0], s[1]-r[1])
    w = (r[0]-p[0], r[1]-p[1])
    length = math.hypot(*u)
    other = math.hypot(*v)
    if min(length, other) <= tolerance:
        return True
    cross = lambda x, y: x[0]*y[1]-x[1]*y[0]
    den = cross(u, v)
    if abs(den) <= 1e-14*length*other:
        if abs(cross(w, u))/length > tolerance:
            return False
        t0 = (w[0]*u[0]+w[1]*u[1])/(length*length)
        t1 = t0+(v[0]*u[0]+v[1]*u[1])/(length*length)
        return min(1., max(t0, t1))-max(0., min(t0, t1)) > tolerance/length
    t, k = cross(w, v)/den, cross(w, u)/den
    eps, other_eps = tolerance/length, tolerance/other
    if not (-eps <= t <= 1+eps and -other_eps <= k <= 1+other_eps):
        return False
    return eps < t < 1-eps or other_eps < k < 1-other_eps


def _discretize(boundaries, tolerance, diagnostics, progress):
    import EM_FCPanelization as P
    factors = [1.0]*len(boundaries)
    for attempt in range(7):
        # Each trial uses one discretization per retained CAD edge. Reusing
        # shared vertex coordinates prevents cracks at material transitions.
        patches, panels, vertices = [], [], {}
        for index, (edge, owner, perm, inner, outer) in enumerate(boundaries):
            if index % 128 == 0:
                P._progress_checkpoint(progress, "Creating 2D contour segments")
            relative = float(owner.entity.fc_object.PanelCurvatureTolerance)
            deflection = max(tolerance, owner.bbox.diagonal*relative*factors[index])
            points = _points(edge, deflection, vertices)
            patch = P.FCSurfacePatch(edge, owner.entity, owner.component, owner.source,
                index, FCBoundingBox.from_shape(edge), normal=App.Vector(0, 0, 1),
                surrounding_permittivity=perm, inner_permittivity=inner,
                outer_permittivity=outer)
            patches.append(patch)
            for start, end in zip(points, points[1:]):
                if (end-start).Length <= tolerance:
                    raise ValueError("A 2D segment is shorter than GeometryTolerance; "
                                     "reduce that tolerance or repair the contour")
                panel = P.FCPanel("S", (tuple(start), tuple(end)), owner.entity,
                    patch, len(panels), surrounding_permittivity=perm,
                    inner_permittivity=inner, outer_permittivity=outer)
                if inner is not None:
                    panel.reference_point = P._reference_for_panel(panel, tolerance)
                panels.append(panel)
        P._progress_checkpoint(progress, "Checking 2D segment intersections")
        def bbox(panel):
            a, b = panel.points
            return FCBoundingBox(min(a[0],b[0]), min(a[1],b[1]), a[2],
                                 max(a[0],b[0]), max(a[1],b[1]), a[2])
        conflicts = set()
        for a, b in FCBoundingBoxIndex(panels, bbox).candidate_pairs(tolerance=tolerance):
            if _segment_conflict(a, b, tolerance):
                conflicts.update((a.patch.index, b.patch.index))
        if not conflicts:
            return patches, panels
        refinable = [i for i in conflicts
                     if "Line" not in type(boundaries[i][0].Curve).__name__]
        if not refinable:
            break
        # Refining a straight edge cannot remove a real crossing. Tighten only
        # curved participants whose chord approximation caused the conflict.
        for index in refinable:
            factors[index] *= .25
    _error(diagnostics, "intersecting_2d_segments",
        "Curved contour chords still intersect or overlap after refinement; "
        "repair the geometry or reduce PanelCurvatureTolerance")
    # Do not publish or export a contour set containing unresolved crossings.
    return [], []


def _make_dielectric_groups_2d(panelization, progress=None):
    """Bounded candidate search on both sides; no pairwise line arrangement.

    Interior points often cover an entire convex contour. Surrounding points
    cover broad runs on non-convex contours. Every member must satisfy the
    same strict half-plane test; an inner reference is exported with D's '-'.
    Per-segment OUTPERM references remain untouched for orientation arrows.
    """
    import numpy as np
    import EM_FCPanelization as P

    tolerance = panelization.context.geometry_tolerance
    semantics = {}
    # A D record has one owner and one ordered material pair, regardless of how
    # many disconnected contour portions its reference point happens to cover.
    for panel in panelization.panels:
        if panel.entity.kind == 'FCDielectric':
            key = (id(panel.entity), round(panel.outer_permittivity, 12),
                   round(panel.inner_permittivity, 12))
            semantics.setdefault(key, []).append(panel)
    groups = []
    for items in semantics.values():
        P._progress_checkpoint(progress, 'Grouping 2D dielectric segments')
        centers = np.asarray([tuple(P._panel_center(p)) for p in items])
        normals = np.asarray([tuple(P._segment_normal(p)) for p in items])
        inward = -normals
        origin = centers[0]
        local = centers-origin
        middle = (local.min(axis=0)+local.max(axis=0))*0.5
        radius = max(float(np.linalg.norm(np.ptp(local, axis=0))), tolerance*100)
        candidates = [origin+local.mean(axis=0), origin+middle]
        # Centroids often cover a whole convex contour on its inner side;
        # surrounding candidates cover larger runs on a concave contour.
        # Separate/disconnected source regions can have useful distinct centers.
        components = {}
        for i, panel in enumerate(items):
            components.setdefault(id(panel.patch.component), []).append(i)
        component_indices = list(components.values())
        for i in np.linspace(0, len(component_indices)-1,
                             min(32, len(component_indices)), dtype=int):
            candidates.append(origin+local[component_indices[i]].mean(axis=0))
        for angle in np.arange(16)*(2*math.pi/16):
            direction = np.array([math.cos(angle), math.sin(angle), 0.])
            candidates.append(origin+middle+direction*(radius*8))
        candidates = np.asarray(candidates)
        pending = np.arange(len(items))
        while pending.size:
            P._progress_checkpoint(progress, 'Grouping 2D dielectric segments')
            seed = items[pending[0]]
            # Guarantee progress with the seed's already validated local point.
            # The remaining centroid helps after a larger group is removed.
            points = np.vstack((candidates,
                                origin+local[pending].mean(axis=0),
                                seed.reference_point))
            best_count, best_point, best_side = 0, None, 'outer'
            for side, side_normals in (('outer', normals), ('inner', inward)):
                counts = np.zeros(len(points), dtype=np.int64)
                for start in range(0, len(pending), P.FCPANEL_GROUP_PANEL_BLOCK):
                    P._progress_checkpoint(progress, 'Grouping 2D dielectric segments')
                    indices = pending[start:start+P.FCPANEL_GROUP_PANEL_BLOCK]
                    # Score in bounded blocks with a conservative margin;
                    # exact scalar membership is checked for the winner below.
                    signed = np.einsum('ijk,jk->ij',
                        points[:, None, :]-centers[indices], side_normals[indices])
                    counts += (signed > tolerance*2).sum(axis=1)
                winner = int(counts.argmax())
                if int(counts[winner]) > best_count:
                    best_count = int(counts[winner])
                    best_point, best_side = tuple(points[winner]), side
                if best_count == len(pending):
                    break
            if best_point is None:
                best_point, best_side = seed.reference_point, 'outer'
            # Final scalar checks match export's side convention exactly and
            # guard against rounding for far-translated or very small models.
            membership = np.array([P._point_on_panel_side(
                best_point, items[i], best_side, tolerance) for i in pending])
            if not membership.any():
                best_point, best_side = seed.reference_point, 'outer'
                membership = np.array([P._point_on_panel_side(
                    best_point, items[i], best_side, tolerance) for i in pending])
            if not membership.any():
                raise ValueError('No robust reference point for a 2D dielectric segment')
            members = [items[i] for i in pending[membership]]
            groups.append(P.FCDielectricPanelGroup(seed.entity, members,
                seed.inner_permittivity, seed.outer_permittivity,
                best_point, best_side))
            pending = pending[~membership]
    for index, group in enumerate(groups):
        group.index = index
        for panel in group.panels:
            panel.dielectric_group = index
    panelization.dielectric_groups = groups


def buildPanelization2D(context, objects, progress=None):
    """Build a 2D result without entering any 3D analysis or defeaturing stage."""
    import EM_FCPanelization as P
    diagnostics = []
    if context.target_solver != "FasterCap":
        raise P.FCPanelizationError("2D models require TargetSolver = FasterCap")
    if context.reference_conductor not in objects or context.reference_conductor.Document is not context.document:
        raise P.FCPanelizationError("ReferenceConductor must belong to this 2D document")
    if sum(obj.Proxy.Type == "FCConductor" for obj in objects) < 2:
        raise P.FCPanelizationError("A 2D model needs a signal conductor and a reference conductor")
    P._progress_checkpoint(progress, "Extracting planar 2D regions")
    geometry, regions = _extract(context, objects, diagnostics)
    patches, panels = [], []
    if regions and not diagnostics:
        try:
            # Resolve filled-region ownership first. Open contours are then
            # split against the retained boundaries without inventing volumes.
            P._progress_checkpoint(progress, "Resolving planar 2D regions")
            filled = [r for r in regions if r.shape.ShapeType == 'Face']
            contours = [r for r in regions if r.shape.ShapeType == 'Edge']
            cells = _arrange(filled, context.geometry_tolerance, diagnostics) if filled else []
            boundaries = _boundaries(cells, context.geometry_tolerance, diagnostics)
            if contours:
                P._progress_checkpoint(progress, 'Resolving open 2D contours')
                boundaries = _open_boundaries(boundaries, contours, cells,
                    context.geometry_tolerance, diagnostics)
            patches, panels = _discretize(boundaries, context.geometry_tolerance,
                                          diagnostics, progress)
        except P.FCPanelizationCancelled:
            raise
        except (RuntimeError, ValueError, TypeError, AttributeError) as exc:
            _error(diagnostics, "2d_boundary_resolution_failed", str(exc))
    if not panels:
        _error(diagnostics, "empty_panelization", "No valid 2D contour segments were generated")
    if not any(p.entity.fc_object is context.reference_conductor for p in panels):
        _error(diagnostics, "missing_2d_reference_boundary",
               "The reference conductor has no exposed contour segments", context.reference_conductor)
    result = P.FCPanelization(context, geometry, patches, panels, [], diagnostics,
                             P.getFCPanelizationSignature(context.document, context.solver))
    P._progress_checkpoint(progress, "Grouping 2D dielectric segments")
    _make_dielectric_groups_2d(result, progress)
    P._validate_panels(result, progress)
    return result
