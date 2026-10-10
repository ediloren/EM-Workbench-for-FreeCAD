"""Bounded repairs of copied BREP contacts, independent of document primitives.

Analytic supports are retrimmed with native offsets and Boolean splits. Fuzzy
General Fuse is a fallback, not a displacement certificate. Both paths pass
the same boundary, topology, contact and material checks before publication.
"""

import math

import FreeCAD
import Part


_ERRORS = (AttributeError, ImportError, RuntimeError, TypeError, ValueError)


def _boundary(shape):
    return Part.makeCompound(shape.Faces)


def preservesContacts(before, after, other, tolerance):
    """Preserve the actual footprint of existing positive-area interfaces.

    A minimum distance of zero also describes isolated tangencies and does
    not establish a shared interface. Tangency regularization remains allowed.
    """
    common = _boundary(before).common(_boundary(other), tolerance)
    if common.Area <= tolerance*tolerance:
        return True
    retained = common.common(_boundary(after), tolerance)
    # Protect the old contact footprint, not just a nonzero overlap somewhere
    # else on the neighbor after the proposed repair.
    allowance = max(tolerance*tolerance, common.Area*1e-8,
                    common.Length*tolerance*4)
    return retained.Area >= common.Area-allowance


def _kind(surface):
    for cls in (Part.Plane, Part.Cylinder, Part.Sphere):
        if isinstance(surface, cls):
            return cls
    return None


def _corners(box):
    return [FreeCAD.Vector(x, y, z)
            for x in (box.XMin, box.XMax)
            for y in (box.YMin, box.YMax)
            for z in (box.ZMin, box.ZMax)]


def _support_bound(face, target):
    """Conservative mismatch bound for the complete selected analytic face."""
    source = face.Surface
    kind = _kind(source)
    if kind is None or kind is not _kind(target):
        return None
    if kind is Part.Plane:
        normal = target.Axis
        # Avoid bbox overestimation for two identical tilted planes.
        if source.Axis.cross(normal).Length < 1e-12:
            return abs(normal.dot(source.Position-target.Position))
        return max(abs(normal.dot(p-target.Position))
                   for p in _corners(face.BoundBox))
    if kind is Part.Sphere:
        return (source.Center-target.Center).Length + abs(source.Radius-target.Radius)
    axis = target.Axis
    # Bound cylinder-axis drift over the trimmed axial interval, then include
    # radius mismatch and tilt across the circular section.
    ends = [source.Center + source.Axis*v for v in face.ParameterRange[2:]]
    offset = max((p-target.Center).cross(axis).Length for p in ends)
    sine = source.Axis.cross(axis).Length
    return offset + abs(source.Radius-target.Radius) + source.Radius*sine


def _project(point, surface):
    u, v = surface.parameter(point)
    return surface.value(u, v)


def _footprint(first, second, tolerance):
    """Look for an extended trimmed overlap, not just nearby support planes."""
    from EM_FCDefeaturing import _samples, _normal
    for source, target in ((first, second), (second, first)):
        points = []
        for point in _samples(source):
            projected = _project(point, target.Surface)
            if not target.isInside(projected, tolerance, True):
                continue
            if abs(_normal(source, point).dot(_normal(target, projected))) < .999:
                continue
            if not points:
                points.append(projected)
            elif len(points) == 1:
                if (projected-points[0]).Length > tolerance:
                    points.append(projected)
            elif (points[1]-points[0]).cross(projected-points[0]).Length > tolerance*tolerance:
                # Three non-collinear witnesses distinguish a contact footprint
                # from a lone tangent point or a narrow line of proximity.
                return True
    return False


def _extended_support(surface, box):
    if isinstance(surface, Part.Sphere):
        return surface.toShape()
    parameters = [surface.parameter(p) for p in _corners(box)]
    margin = max(box.DiagonalLength*.1, 1e-6)
    vmin = min(p[1] for p in parameters)-margin
    vmax = max(p[1] for p in parameters)+margin
    if isinstance(surface, Part.Cylinder):
        return surface.toShape(0, 2*math.pi, vmin, vmax)
    return surface.toShape(min(p[0] for p in parameters)-margin,
                           max(p[0] for p in parameters)+margin, vmin, vmax)


def _signed(point, surface):
    if isinstance(surface, Part.Plane):
        return surface.Axis.dot(point-surface.Position)
    delta = point-surface.Center
    if isinstance(surface, Part.Cylinder):
        return delta.cross(surface.Axis).Length-surface.Radius
    return delta.Length-surface.Radius


def _interior_point(solid, tolerance):
    from EM_FCPanelization import _face_center_normal
    center = solid.CenterOfMass
    # A torus or concave Boolean cell can have its centre of mass outside the
    # material. Fall back to inward face probes before trusting a cell label.
    if solid.isInside(center, tolerance, False):
        return center
    for face in solid.Faces:
        point, normal = _face_center_normal(face)
        for distance in (10*tolerance, solid.BoundBox.DiagonalLength*1e-5):
            probe = point-normal*distance
            if solid.isInside(probe, tolerance, False):
                return probe
    raise ValueError("could not classify a Boolean cell interior")


def _union(shapes):
    if not shapes:
        raise ValueError("repair removed the component")
    return (shapes[0].multiFuse(shapes[1:]) if len(shapes) > 1
            else shapes[0]).removeSplitter()


def _retrim(shape, face, target, distance, tolerance):
    """Replace a support through a local offset collar and exact cell split.

    The collar is built from the actual trimmed face, including its holes.
    No document primitive, radius/length property or parametric history is
    consulted. Collateral cuts on non-convex shapes are rejected by the audit.
    """
    from BOPTools import SplitAPI
    from EM_FCPanelization import _face_center_normal
    point, normal = _face_center_normal(face)
    padding = distance*1.25 + 10*tolerance
    if isinstance(face.Surface, Part.Plane):
        collar = face.extrude(normal*padding)
    else:
        try:
            collar = face.makeOffsetShape(padding, tolerance, fill=True, join=2)
        except _ERRORS:
            # A complete spherical surface has no trimming wire to close.
            shell = face.makeOffsetShape(padding, tolerance, fill=False, join=2)
            if not shell.isClosed():
                raise ValueError("could not close the offset collar")
            collar = Part.makeSolid(shell)
    expanded = shape.fuse(collar).removeSplitter()
    # Split the temporarily expanded solid on the target support, then retain
    # only its original material side. This changes BREP, not primitive inputs.
    support = _extended_support(target, expanded.BoundBox)
    fragments = SplitAPI.slice(expanded, [support], "Split", tolerance).Solids
    projected = _project(point, target)
    # Determine the material side from the original face's outward normal.
    direction = _signed(projected+normal*padding, target)
    if abs(direction) <= tolerance:
        raise ValueError("could not establish the support's material side")
    kept = [s for s in fragments
            if _signed(_interior_point(s, tolerance), target)*direction < 0]
    return _union(kept)


def _fuzzy(shape, reference, distance, tolerance):
    # Put the reference first, but still verify the actual resulting support:
    # argument order is not a kernel guarantee of geometric precedence.
    _result, history = reference.copy().generalFuse(
        [shape.copy()], distance + max(tolerance*2, distance*1e-6))
    return _union(list(history[1]))


def _audit(piece, candidate, source_face, reference_face, bound, others, tolerance):
    from EM_FCDefeaturing import _safe_replacement, _samples
    if not _safe_replacement(piece, candidate, others, tolerance):
        raise ValueError("repair changes a protected contact or material connectivity")
    allowance = piece.budget-piece.moved
    # Charge every accepted edit against the remaining budget; a sequence of
    # individually small repairs must not accumulate an unlimited displacement.
    old_rim, new_rim = _boundary(piece.shape), _boundary(candidate)
    distance = max(Part.Vertex(p).distToShape(rim)[0]
                   for shape, rim in ((piece.shape, new_rim), (candidate, old_rim))
                   for p in _samples(shape))
    distance = max(distance, bound)
    if distance > allowance+tolerance:
        raise ValueError("repair exceeds the remaining boundary-deviation budget")
    # OCC also exposes Volume on open faces/shells, but that is not enclosed
    # material volume and cannot constrain a surface-only repair.
    if piece.shape.Solids:
        if candidate.Volume <= 0 or abs(candidate.Volume-piece.shape.Volume) > (
                max(candidate.Area, piece.shape.Area)*allowance):
            raise ValueError("repair changes too much component volume")
    # Fuzzy topology must agree with its geometry; increasing stored tolerance
    # alone is not a repair. Keep this check independent of the size budget.
    coherence = max(tolerance*10, piece.shape.getTolerance(1)*2)
    for face in candidate.Faces:
        for edge in face.Edges:
            for t in (0., .25, .5, .75, 1.):
                p = edge.valueAt(edge.FirstParameter + t*(edge.LastParameter-edge.FirstParameter))
                if (p-_project(p, face.Surface)).Length > coherence:
                    raise ValueError("Boolean edges do not lie on their supporting faces")
    # Adjacent faces may be retrimmed, but unrelated supports must survive.
    for old in piece.shape.Faces:
        if old.isSame(source_face):
            continue
        if _kind(old.Surface) is not None and not any(
                (d is not None and d <= coherence)
                for d in (_support_bound(f, old.Surface) for f in candidate.Faces)):
            raise ValueError("repair removed an unrelated face support")
    aligned = [f for f in candidate.Faces
               if (d := _support_bound(f, reference_face.Surface)) is not None
               and d <= tolerance*10]
    # Matching an infinite support is insufficient: the repaired trimmed face
    # must actually overlap the requested reference interface.
    if not aligned or Part.makeCompound(aligned).common(
            reference_face, tolerance).Area <= tolerance*tolerance:
        raise ValueError("repair did not establish the requested trimmed interface")
    return distance


def repairContacts(ordered, neighbors, tolerance, diagnostics, progress=None):
    """One bounded pass over nearby component pairs; publish checked edits only."""
    from EM_FCDefeaturing import _near, _warn
    lookup = {id(piece): piece for piece in ordered}
    rank = {id(piece): index for index, piece in enumerate(ordered)}
    for index, first in enumerate(ordered):
        nearby = sorted((lookup[key] for key in neighbors[id(first)]
                         if rank[key] > index), key=lambda p: rank[id(p)])
        for second in nearby:
            if first.kind == second.kind == "FCConductor" and first.obj is not second.obj:
                # Never turn a small electrical clearance into a short.
                continue
            # Preferred reference first. At equal priority try the other
            # enabled participant if preserving its neighbors requires it.
            directions = [(second, first)]
            if (first.settings.enabled and second.settings.enabled and
                    first.settings.priority == second.settings.priority):
                directions.append((first, second))
            for piece, reference in directions:
                if not piece.settings.enabled:
                    continue
                threshold = (min(piece.size, reference.size)
                             if reference.settings.enabled else piece.size)
                others = [lookup[key] for key in neighbors[id(piece)]]
                # A face can be retrimmed only once against this reference.
                # Re-fetch it after an accepted edit; source indices are not
                # stable across Boolean reconstruction.
                targets = list(reference.shape.Faces)
                for target in targets:
                    if progress:
                        progress("Reconciling nearby analysis interfaces")
                    matches = []
                    for face in piece.shape.Faces:
                        if not _near(face, target, threshold):
                            continue
                        bound = _support_bound(face, target.Surface)
                        if bound is None or not tolerance*2 < bound <= threshold:
                            continue
                        try:
                            if _footprint(face, target, tolerance):
                                matches.append((bound, face))
                        except _ERRORS:
                            continue
                    for bound, face in sorted(matches, key=lambda item: item[0]):
                        if bound > piece.budget-piece.moved+tolerance:
                            _warn(diagnostics, piece, "defeaturing_limit",
                                  "Local interface repair exceeds the remaining boundary movement")
                            break
                        errors = []
                        methods = [("analytic", lambda: _retrim(
                            piece.shape, face, target.Surface, bound, tolerance)),
                                   ("fuzzy", lambda: _fuzzy(
                            piece.shape, reference.shape, bound, tolerance))]
                        if piece.shape.ShapeType != "Solid":
                            methods = methods[1:]
                        for method, build in methods:
                            # Both reconstruction paths face the same audit.
                            # Failure leaves piece.shape untouched for the next try.
                            try:
                                candidate = build()
                                distance = _audit(piece, candidate, face, target,
                                                  bound, others, tolerance)
                            except _ERRORS as error:
                                errors.append(str(error))
                                continue
                            piece.shape = candidate
                            # Publish only after the complete audit, so later
                            # neighbors see a valid, budgeted analysis shape.
                            piece.moved += distance
                            _warn(diagnostics, piece, "defeaturing_contact_repaired",
                                  "Reconciled a local %s interface with %s using %s BREP repair; inspect the approximation"
                                  % (_kind(target.Surface).__name__, reference.obj.Label, method),
                                  reference=reference.obj.Name, method=method,
                                  sampled_deviation=distance)
                            break
                        else:
                            _warn(diagnostics, piece, "defeaturing_contact_retained",
                                  "Local repair of this component was not accepted: %s" % errors[-1],
                                  reference=reference.obj.Name, attempts=errors)
                        # Boolean operations invalidate the other face handles.
                        break
