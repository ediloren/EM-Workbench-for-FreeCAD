"""Opt-in, bounded simplification of the *analysis* geometry.

The CAD document is never edited.  Both boundary extraction and solid
classification consume the same replacement shapes.  Feature size expresses
user intent, not an OCC sewing tolerance: increasing GeometryTolerance is not
a substitute for these operations.

This intentionally conservative first implementation handles removable small
solid faces, near-aligned planar contacts and curved tangencies.  Unsupported
or ambiguous features are retained and diagnosed, never deleted from a mesh.
"""

from dataclasses import dataclass
import math

import FreeCAD
import Part


DEFAULT_RELATIVE_SIZE = 0.002
DEFAULT_RELATIVE_DEVIATION = 0.002
MIN_RELATIVE_VALUE = 1.0e-8
MAX_RELATIVE_VALUE = 0.1
POLICIES = ["Align contacts", "Align and regularize"]
MODES = ["Inherit", "Disabled", "Custom"]


def ensureDefeaturingProperties(obj, solver=False):
    """Install defeaturing controls without changing global GUI precision.

    FreeCAD's PropertyFloatConstraint editor always formats values with the
    application's global Units/Decimals preference.  Relative defeaturing
    values are usually below 0.01, so use two local string properties instead:
    their complete decimal text stays visible in the Property editor.  Values
    are parsed and range-checked before the panelizer consumes them.
    """
    definitions = []
    if solver:
        definitions.append(("App::PropertyBool", "DefeaturingEnabled",
                            "Allow approximate analysis geometry; Base geometry is unchanged", False))
    else:
        definitions.extend([
            ("App::PropertyEnumeration", "Defeaturing",
             "Inherit solver controls, preserve this object's geometry, or use custom controls", MODES),
            ("App::PropertyInteger", "DefeaturingPriority",
             "Higher priority is the alignment reference; disabled objects are always fixed", 0)])
    definitions.extend([
        ("App::PropertyString", "DefeaturingRelativeSize",
         "Candidate feature size / original connected Base component bounding-box diagonal. Enter a decimal between 1e-8 and 0.1; displayed text retains its precision.",
         _relative_text(DEFAULT_RELATIVE_SIZE)),
        ("App::PropertyString", "DefeaturingRelativeDeviation",
         "Allowed analysis-boundary movement / original component diagonal; face-removal bound is sampled. Enter a decimal between 0 and 0.1; displayed text retains its precision.",
         _relative_text(DEFAULT_RELATIVE_DEVIATION)),
        ("App::PropertyEnumeration", "DefeaturingPolicy",
         "Align near planar contacts; optionally regularize curved tangencies by bounded solid contraction", POLICIES)])
    for kind, name, description, default in definitions:
        if name not in obj.PropertiesList:
            obj.addProperty(kind, name, "Defeaturing", description)
            setattr(obj, name, default)
            if name == "DefeaturingPolicy":
                obj.DefeaturingPolicy = "Align and regularize"
    if not solver:
        syncDefeaturingEditor(obj)


def _relative_text(value):
    """Stable, readable decimal text for the per-object property editor."""
    return format(float(value), ".12g")


def relativeValue(obj, name, default, minimum=MIN_RELATIVE_VALUE):
    """Read a local precision-preserving value and reject invalid text early."""
    try:
        value = float(str(getattr(obj, name)))
    except (TypeError, ValueError):
        value = default
    if not math.isfinite(value):
        value = default
    return min(MAX_RELATIVE_VALUE, max(minimum, value))


def normalizeRelativeValue(obj, name):
    """Canonicalize direct Property-editor edits without changing preferences."""
    default = (DEFAULT_RELATIVE_SIZE if name == "DefeaturingRelativeSize"
               else DEFAULT_RELATIVE_DEVIATION)
    minimum = MIN_RELATIVE_VALUE if name == "DefeaturingRelativeSize" else 0.0
    value = relativeValue(obj, name, default, minimum)
    text = _relative_text(value)
    if getattr(obj, name) != text:
        obj.__setattr__(name, text)


def syncDefeaturingEditor(obj):
    """Make it clear that only Custom uses the object's numeric overrides."""
    mode = 0 if str(getattr(obj, "Defeaturing", "Inherit")) == "Custom" else 1
    for name in ("DefeaturingRelativeSize", "DefeaturingRelativeDeviation", "DefeaturingPolicy"):
        if name in obj.PropertiesList:
            obj.setEditorMode(name, mode)


def defeaturingSignature(obj):
    """Include even currently inactive overrides in the frozen-model signature."""
    return tuple(getattr(obj, key, None) for key in (
        "DefeaturingEnabled", "Defeaturing", "DefeaturingRelativeSize",
        "DefeaturingRelativeDeviation", "DefeaturingPolicy", "DefeaturingPriority"))


@dataclass
class Settings:
    enabled: bool
    relative_size: float
    relative_deviation: float
    policy: str
    priority: int


def settingsFor(obj, solver):
    mode = str(getattr(obj, "Defeaturing", "Inherit"))
    source = obj if mode == "Custom" else solver
    return Settings(
        mode == "Custom" or (mode != "Disabled" and
                             bool(getattr(solver, "DefeaturingEnabled", False))),
        relativeValue(source, "DefeaturingRelativeSize", DEFAULT_RELATIVE_SIZE),
        relativeValue(source, "DefeaturingRelativeDeviation",
                      DEFAULT_RELATIVE_DEVIATION, 0.0),
        str(getattr(source, "DefeaturingPolicy", POLICIES[-1])),
        int(getattr(obj, "DefeaturingPriority", 0)))


@dataclass
class _Piece:
    obj: object
    shape: object
    original: object
    settings: Settings
    size: float
    budget: float
    moved: float = 0.0

    @property
    def kind(self):
        return self.obj.Proxy.Type

    @property
    def bbox(self):
        from EM_FCGeometry import FCBoundingBox
        return FCBoundingBox.from_shape(self.original)


def _pieces(shape):
    # A compound's disconnected children must not borrow a large scene scale.
    # Explicit shells (including open shells) remain intact.
    if shape.ShapeType in ("Compound", "CompSolid"):
        return [piece for child in shape.childShapes() for piece in _pieces(child)]
    return [shape]


def _near(a, b, distance):
    return all(getattr(a.BoundBox, axis + "Min") <=
               getattr(b.BoundBox, axis + "Max") + distance and
               getattr(b.BoundBox, axis + "Min") <=
               getattr(a.BoundBox, axis + "Max") + distance
               for axis in "XYZ")


def _is_plane(face):
    return isinstance(face.Surface, Part.Plane)


def _normal(face, point):
    u, v = face.Surface.parameter(point)
    normal = face.normalAt(u, v)
    if normal.Length <= 1e-15:
        raise ValueError("Surface normal is undefined at this contact")
    return normal / normal.Length


def _warn(diagnostics, piece, code, message, **details):
    # Lazy import avoids a property-definition/geometry-module import cycle.
    from EM_FCGeometry import FCDiagnostic
    diagnostics.append(FCDiagnostic(
        "warning", code, message, piece.obj, details=details))


def _samples(shape):
    """Bounded-density audit, not a mathematical Hausdorff certificate.

    Rigid alignment and uniform contraction have analytic displacement bounds;
    OCC face removal additionally needs this bidirectional surface audit.
    Trimmed samples outside the actual face are excluded (holes matter).
    """
    for vertex in shape.Vertexes:
        yield vertex.Point
    for edge in shape.Edges:
        if edge.Length > 1e-12:
            for fraction in (0.25, 0.5, 0.75):
                yield edge.valueAt(edge.FirstParameter + fraction *
                                   (edge.LastParameter - edge.FirstParameter))
    for face in shape.Faces:
        u0, u1, v0, v1 = face.ParameterRange
        for i in range(1, 5):
            for j in range(1, 5):
                point = face.valueAt(u0 + (u1-u0)*i/5, v0 + (v1-v0)*j/5)
                if face.isInside(point, 1e-7, True):
                    yield point


def _safe_replacement(piece, candidate, others, tolerance):
    """Never introduce shorts or new incompatible dielectric volume overlaps."""
    if candidate.isNull() or not candidate.isValid():
        return False
    if len(candidate.Solids) != len(piece.shape.Solids):
        return False
    for other in others:
        if other is piece:
            continue
        if other.obj is piece.obj:
            if (_near(piece.shape, other.shape, tolerance) and
                    piece.shape.distToShape(other.shape)[0] <= tolerance and
                    candidate.distToShape(other.shape)[0] > tolerance):
                return False
            continue
        distinct_metals = piece.kind == other.kind == "FCConductor"
        incompatible = (piece.kind == other.kind == "FCDielectric" and
                        float(piece.obj.InnerPermittivity) !=
                        float(other.obj.InnerPermittivity))
        if not (distinct_metals or incompatible):
            continue
        if not _near(candidate, other.shape, tolerance):
            continue
        if distinct_metals and candidate.distToShape(other.shape)[0] <= tolerance:
            # Even a point/edge short changes electrical connectivity.
            return False
        if incompatible:
            old_volume = piece.shape.common(other.shape).Volume
            if candidate.common(other.shape).Volume > old_volume + tolerance**3:
                return False
    return True


def _remove_small_faces(piece, others, tolerance, diagnostics):
    if piece.shape.ShapeType != "Solid" or piece.budget <= tolerance:
        return
    # Hydraulic width recognizes long narrow fillets as well as small holes.
    # Faces of a wholly small component are not grounds for deleting that body.
    faces = [face for face in piece.shape.Faces
             if face.Length > tolerance and
             2.0 * face.Area / face.Length < piece.size]
    if not faces or len(faces) == len(piece.shape.Faces):
        return
    try:
        candidate = piece.shape.defeaturing(faces)
        if len(candidate.Faces) >= len(piece.shape.Faces):
            raise ValueError("OCC could not remove the candidate faces")
        if not _safe_replacement(piece, candidate, others, tolerance):
            raise ValueError("replacement changes validity or material connectivity")
        maximum = piece.budget - piece.moved
        distance = max(Part.Vertex(point).distToShape(target)[0]
                       for source, target in ((piece.shape, candidate),
                                              (candidate, piece.shape))
                       for point in _samples(source))
        if distance > maximum or abs(candidate.Volume - piece.shape.Volume) > (
                max(candidate.Area, piece.shape.Area) * maximum):
            raise ValueError("replacement exceeds the boundary-deviation budget")
        piece.shape = candidate
        piece.moved += distance
        _warn(diagnostics, piece, "defeaturing_faces_removed",
              "Removed %d small solid face(s); sampled boundary movement %.6g CAD units. Inspect the approximation"
              % (len(faces), distance),
              faces=len(faces), sampled_deviation=distance)
    except (AttributeError, RuntimeError, ValueError, TypeError) as error:
        _warn(diagnostics, piece, "defeaturing_feature_retained",
              "Small solid features retained: %s" % error)


def _alignment(piece, reference, threshold, tolerance):
    """Fit translations to independent, nearly coincident support planes.

    Actual finite face bounds must be close too: parallel planes at unrelated
    locations are not contacts.  Conflicting shifts in one normal direction
    are ambiguous, so callers retain the geometry rather than averaging them.
    """
    constraints = []
    for face in piece.shape.Faces:
        if not _is_plane(face):
            continue
        normal = _normal(face, face.CenterOfMass)
        for other in reference.shape.Faces:
            if not _is_plane(other) or not _near(face, other, threshold):
                continue
            if abs(normal.dot(_normal(other, other.CenterOfMass))) < 1.0-1e-9:
                continue
            offset = normal.dot(other.CenterOfMass-face.CenterOfMass)
            if abs(offset) <= threshold:
                constraints.append((normal, offset))
    shift = FreeCAD.Vector()
    basis = []
    for normal, offset in constraints:
        residual = normal - sum((axis * normal.dot(axis) for axis in basis),
                                FreeCAD.Vector())
        mismatch = offset-normal.dot(shift)
        if residual.Length <= 1e-8:
            if abs(mismatch) > tolerance:
                return None
        else:
            shift += residual * (mismatch / residual.dot(residual))
            basis.append(residual / residual.Length)
    return shift


def _tangent_pair(piece, reference, threshold, tolerance):
    """Detect exact/near contacts with parallel local surface normals.

    This is geometry-type independent: a sphere pole, cylinder generator or
    spline contact can all qualify.  Whole coincident planar faces do not.
    OCC's closest-point witnesses avoid relying on face centres of mass.
    """
    for face in piece.shape.Faces:
        if _is_plane(face):
            continue
        for other in reference.shape.Faces:
            if not _near(face, other, threshold):
                continue
            distance, pairs, _info = face.distToShape(other)
            if distance > threshold:
                continue
            for first, second in pairs:
                if abs(_normal(face, first).dot(_normal(other, second))) > 0.999:
                    # Overlaid curved interfaces need ownership resolution,
                    # not contraction of an otherwise intentional shared wall.
                    if face.common(other).Area <= tolerance*tolerance:
                        return True
    return False


def prepareDefeaturingSources(objects, solver, tolerance, progress=None):
    """Return optional per-object source replacements plus diagnostics.

    One removal, alignment and contraction pass per component bounds the work;
    no unbounded remesh/search loop.  Exact unchanged sources are reused when
    disabled.  Every accepted edit is reported so the user can assess its
    electrical significance.  Higher-priority/disabled components are fixed
    references; a tie favours conductors, then document order.
    """
    from EM_FCCommon import normalizeFCBase, _fc_subshape
    from EM_FCGeometry import FCBoundingBoxIndex
    diagnostics = []
    if not any(settingsFor(obj, solver).enabled for obj in objects):
        return None, diagnostics
    records, pieces = [], []
    for obj in objects:
        settings = settingsFor(obj, solver)
        for source, subnames in normalizeFCBase(obj.Base):
            for subname in subnames:
                shape = _fc_subshape(source, subname)
                # Normal extraction remains responsible for invalid references.
                if shape is None or shape.isNull() or not shape.isValid():
                    records.append((obj, source, subname, [], shape))
                    continue
                children = []
                for child in _pieces(shape):
                    length = child.BoundBox.DiagonalLength
                    piece = _Piece(obj, child.copy(), child, settings,
                                   length*settings.relative_size,
                                   length*settings.relative_deviation)
                    pieces.append(piece)
                    children.append(piece)
                records.append((obj, source, subname, children, shape))
    ordered = sorted(pieces, key=lambda p: (
        p.settings.enabled, -p.settings.priority, p.kind != "FCConductor"))
    # Sweep original boxes expanded enough to include every allowed movement.
    # Re-use this conservative candidate graph for both passes; distant
    # components never invoke pairwise OCC operations.
    reach = max((p.size + 2*p.budget for p in ordered), default=0.0)
    neighbors = {id(p): set() for p in ordered}
    for first, second in FCBoundingBoxIndex(ordered).candidate_pairs(tolerance=reach):
        neighbors[id(first)].add(id(second))
        neighbors[id(second)].add(id(first))
    for index, piece in enumerate(ordered):
        if progress:
            progress("Preparing defeatured analysis geometry")
        if not piece.settings.enabled:
            continue
        nearby = [p for p in ordered if id(p) in neighbors[id(piece)]]
        _remove_small_faces(piece, nearby, tolerance, diagnostics)
        # One component-wide translation keeps its topology conformal and has
        # an exact movement bound. Never chain a sequence of subthreshold moves.
        for reference in ordered[:index]:
            if id(reference) not in neighbors[id(piece)]:
                continue
            threshold = min(piece.size, reference.size) if reference.settings.enabled else piece.size
            if not _near(piece.shape, reference.shape, threshold):
                continue
            try:
                shift = _alignment(piece, reference, threshold, tolerance)
                if shift is None:
                    _warn(diagnostics, piece, "defeaturing_ambiguous_alignment",
                          "Conflicting nearby planes; alignment retained unchanged")
                    continue
                if shift.Length <= tolerance:
                    continue
                if shift.Length > piece.budget-piece.moved:
                    _warn(diagnostics, piece, "defeaturing_limit",
                          "Contact alignment exceeds the allowed boundary movement")
                    continue
                candidate = piece.shape.copy()
                candidate.translate(shift)
                if not _safe_replacement(piece, candidate, nearby, tolerance):
                    _warn(diagnostics, piece, "defeaturing_protected_contact",
                          "Alignment retained: it could short distinct conductors or overlap incompatible materials")
                    continue
                piece.shape = candidate
                piece.moved += shift.Length
                _warn(diagnostics, piece, "defeaturing_aligned",
                      "Aligned support planes to %s by %.6g CAD units; inspect the changed contact"
                      % (reference.obj.Label, shift.Length),
                      reference=reference.obj.Name, displacement=shift.Length)
                break
            except (AttributeError, RuntimeError, ValueError, TypeError) as error:
                _warn(diagnostics, piece, "defeaturing_alignment_failed", str(error))
    # Curved contacts can create zero-angle cusps even when every original
    # face is large. A bounded homothety opens such a contact; it is an explicit
    # approximation of the whole connected solid, NOT merely a mesh repair.
    for piece in ordered:
        if not piece.settings.enabled or piece.settings.policy != POLICIES[-1]:
            continue
        if progress:
            progress("Preparing defeatured analysis geometry")
        remaining = min(piece.size, piece.budget-piece.moved)
        if remaining <= 10*tolerance:
            continue
        try:
            nearby = [p for p in ordered if id(p) in neighbors[id(piece)]]
            references = [other for other in nearby if other.obj is not piece.obj and
                          _near(piece.shape, other.shape, piece.size)]
            if not any(_tangent_pair(piece, other, min(piece.size, other.size)
                                    if other.settings.enabled else piece.size,
                                    tolerance) for other in references):
                continue
            if piece.shape.ShapeType != "Solid":
                _warn(diagnostics, piece, "defeaturing_tangency_retained",
                      "Curved open-surface tangency requires manual repair; no solid to regularize")
                continue
            center = piece.shape.BoundBox.Center
            radius_bound = 0.5*piece.shape.BoundBox.DiagonalLength
            candidate = piece.shape.copy()
            # Every point lies within this bbox-centred ball, giving an exact
            # bound (1-scale)*radius_bound on its displacement, including curves.
            candidate.scale(1.0-remaining/radius_bound, center)
            if not _safe_replacement(piece, candidate, nearby, tolerance):
                raise ValueError("contraction changes material connectivity")
            piece.shape = candidate
            piece.moved += remaining
            _warn(diagnostics, piece, "defeaturing_regularized",
                  "Contracted a curved solid at a tangent/near-tangent contact; movement bound %.6g CAD units. Inspect the changed clearance"
                  % remaining,
                  displacement_bound=remaining)
        except (AttributeError, RuntimeError, ValueError, TypeError) as error:
            _warn(diagnostics, piece, "defeaturing_tangency_retained", str(error))
    sources = {obj.Name: [] for obj in objects}
    for obj, source, subname, children, original in records:
        if not children:
            shape = original
        elif len(children) == 1:
            shape = children[0].shape
        else:
            shape = Part.makeCompound([piece.shape for piece in children])
        sources[obj.Name].append((source, subname, shape))
    return sources, diagnostics


def diagnoseDefeaturingPatches(patches, solver, tolerance):
    """Second-pass warning for small features created by material splitting.

    Keep full coverage and the normal bad-triangle checks. Deleting individual
    slivers here would create holes and disagree with classifier solids.
    """
    from EM_FCGeometry import FCDiagnostic
    found = {}
    for patch in patches:
        if patch.removed:
            continue
        obj = patch.entity.fc_object
        settings = settingsFor(obj, solver)
        if not settings.enabled:
            continue
        face = patch.shape
        length = patch.source_face.classifier_solid.shape.BoundBox.DiagonalLength if (
            patch.source_face.classifier_solid is not None) else patch.component.bbox.diagonal
        if face.Length > tolerance and 2*face.Area/face.Length < length*settings.relative_size:
            found.setdefault(obj.Name, (obj, []))[1].append(patch.index)
    return [FCDiagnostic(
        "warning", "defeaturing_residual_feature",
        "Small interface features remain after splitting; inspect or adjust the defeaturing controls",
        obj, details={"patch_indices": indices}) for obj, indices in found.values()]
