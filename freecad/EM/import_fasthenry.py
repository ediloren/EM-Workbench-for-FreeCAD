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

"""FastHenry input geometry reader and surface-only FreeCAD visualization.

Geometry follows readGeom.c, HOLE.C, CONTACT.C, read_tree.c and writefastcap.c
in the FastHenry source. Parsing/plane meshing uses only Python's
standard library; FreeCAD/Part are loaded only by read_fasthenry_file().
Coordinates in the parsed model are SI; displayed coordinates are millimeters.
This is the unrefined (-f simple) segment geometry, with thick planes (-g thick).
Like writefastcap.c, the default drawing omits segment end caps.
"""

from collections import defaultdict
from dataclasses import dataclass, field
import math
import os
import re

FH_PROGRESS_INTERVAL = 128
FH_MAX_CELLS = 1000000
FH_MAX_SEGMENTS = 1000000
_EPS = 1e-13  # FastHenry EPS, used for direction comparisons (not length units).
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_ASSIGNMENT = re.compile(r'(\w+)\s*=\s*("[^"\n]*"|\'[^\'\n]*\'|[^\s(),]+)')
_CALL = re.compile(r"(hole|contact)\s+(\w+)\s+(?:(\S+)\s*)?\(([^)]*)\)", re.I)
_NODE = re.compile(r"(n[^\s(),=]*)\s*\(([^)]*)\)", re.I)


class FHImportError(ValueError):
    """Invalid or unsupported FastHenry geometry, with source context."""


class FHImportCancelled(Exception):
    """The progress callback requested cancellation."""


class _Progress:
    def __init__(self, callback=None):
        self.callback = callback
        self.work = 0

    def check(self, stage, current=0, total=0, force=False):
        self.work += 1
        if self.callback and (force or self.work % FH_PROGRESS_INTERVAL == 0):
            if self.callback(stage, current, total) is False:
                raise FHImportCancelled()


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _mul(a, scale):
    return tuple(x * scale for x in a)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])


def _unit(a):
    length = math.sqrt(_dot(a, a))
    if not length or not math.isfinite(length):
        raise FHImportError("Zero or invalid direction vector")
    return _mul(a, 1 / length)


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        raise FHImportError("Non-finite numeric value: " + value)
    return result


def _positive(value, name):
    if value <= 0:
        raise FHImportError(name + " must be positive")
    return value


def _integer(value, name):
    if value != int(value) or value <= 0:
        raise FHImportError(name + " must be a positive integer")
    return int(value)


def _path(filename, base=None):
    filename = os.path.expanduser(os.fspath(filename))
    if base and not os.path.isabs(filename):
        filename = os.path.join(base, filename)
    return os.path.abspath(filename)


def _identity(path):
    return os.path.normcase(os.path.realpath(path))


def _logical_lines(path, progress):
    # getoneline/getaline/plusline skip blank lines, reserve the first logical
    # line as a title, and allow comments between continuation lines.
    current = None
    first = True
    with open(path, encoding="utf-8-sig", errors="replace") as stream:
        for number, physical in enumerate(stream, 1):
            progress.check("Reading FastHenry input", number)
            text = physical.strip()
            if not text or text.startswith("*"):
                if first and text:
                    first = False
                continue
            if text.startswith("+"):
                if current is None:
                    raise FHImportError("%s:%d: nothing to continue" % (path, number))
                current = (current[0], current[1] + " " + text[1:].strip())
            else:
                if current is not None:
                    yield current
                if first:
                    first = False
                    current = None
                else:
                    current = (number, text)
        if current is not None:
            yield current


def _assignments(text, allowed):
    values = {}
    position = 0
    while position < len(text):
        if not text[position:].strip():
            break
        position += len(text[position:]) - len(text[position:].lstrip())
        match = _ASSIGNMENT.match(text, position)
        if match is None:
            raise FHImportError("Unrecognized parameters: " + text[position:].strip())
        key = match[1].lower()
        if key not in allowed:
            raise FHImportError("Unrecognized parameter: " + key)
        values[key] = match[2].strip('"\'') if key == "file" else _float(match[2])
        position = match.end()
    return values


@dataclass
class FHSegmentGeometry:
    name: str
    start: tuple
    end: tuple
    width: float
    height: float
    width_direction: tuple = None
    group: str = "Segments"
    source_line: int = 0

    def __post_init__(self):
        _positive(self.width, "Segment width")
        _positive(self.height, "Segment height")
        length = _sub(self.end, self.start)
        axis = _unit(length)
        if self.width_direction is None:
            # writefastcap.c: default width lies in XY, with X for verticals.
            width = (-axis[1], axis[0], 0.)
            if abs(width[0]) < _EPS and abs(width[1]) < _EPS:
                width = (1., 0., 0.)
            self.width_direction = _unit(width)
        else:
            self.width_direction = _unit(self.width_direction)
        _unit(_cross(axis, self.width_direction))


def segment_faces(segment, end_caps=False):
    """Return the four lateral quads written by writefastcap.c (SI units)."""
    width = _mul(segment.width_direction, segment.width / 2)
    height = _mul(_unit(_cross(_sub(segment.end, segment.start),
                              segment.width_direction)), segment.height / 2)
    rings = []
    for point in (segment.start, segment.end):
        rings.append([_add(point, _add(_mul(width, sw), _mul(height, sh)))
                      for sw, sh in ((-1, 1), (-1, -1), (1, -1), (1, 1))])
    a, b = rings
    faces = [(a[i], a[(i+1) % 4], b[(i+1) % 4], b[i]) for i in range(4)]
    if end_caps:
        faces.extend((tuple(reversed(a)), tuple(b)))
    return faces


@dataclass
class FHGeometry:
    source: str
    files: list = field(default_factory=list)
    segments: list = field(default_factory=list)
    plane_names: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def append(self, segment):
        if len(self.segments) >= FH_MAX_SEGMENTS:
            raise FHImportError("FastHenry visualization segment limit exceeded")
        self.segments.append(segment)


@dataclass
class _PlaneCall:
    kind: str
    values: tuple
    offset: tuple
    name: str = ""


@dataclass(eq=False)
class _Cell:
    x0: float
    y0: float
    x1: float
    y1: float
    children: list = field(default_factory=list)
    split: str = ""
    grid: tuple = None
    hole: bool = False

    def containing(self, x, y):
        cell = self
        while cell.children:
            if cell.grid:
                nx, ny = cell.grid
                i = min(nx-1, max(0, int((x-cell.x0)/(cell.x1-cell.x0)*nx)))
                j = min(ny-1, max(0, int((y-cell.y0)/(cell.y1-cell.y0)*ny)))
                cell = cell.children[(ny-j-1)*nx+i]
            else:
                # find_nonuni_path.c uses strict > at binary boundaries.
                high = ((x-cell.x0)/(cell.x1-cell.x0) > .5 if cell.split == "EW"
                        else (y-cell.y0)/(cell.y1-cell.y0) > .5)
                cell = cell.children[0 if high else 1]
        return cell

    def leaves(self):
        stack = [self]
        while stack:
            cell = stack.pop()
            if cell.children:
                stack.extend(reversed(cell.children))
            else:
                yield cell


class _NonuniformPlane:
    """Rectangular partition with source-compatible contact refinement.

    The C implementation maintains cell/node adjacency while splitting. Here
    leaf boundary intervals are swept after refinement, giving the same segment
    widths/center offsets (read_tree.c:get_width_and_shift), including T nodes.
    """
    def __init__(self, plane, progress):
        self.plane = plane
        self.progress = progress
        self.root = _Cell(0., 0., plane.length1, plane.length2)
        self.count = 1

    def _reserve(self, number):
        self.count += number
        if self.count > FH_MAX_CELLS:
            raise FHImportError("Nonuniform plane cell limit exceeded")
        self.progress.check("Discretizing nonuniform planes", self.count)

    def split(self, cell, direction):
        self._reserve(2)
        x0, y0, x1, y1 = cell.x0, cell.y0, cell.x1, cell.y1
        if direction == "EW":
            mid = (x0+x1)/2
            bounds = [(mid, y0, x1, y1), (x0, y0, mid, y1)]
        else:
            mid = (y0+y1)/2
            bounds = [(x0, mid, x1, y1), (x0, y0, x1, mid)]
        if mid in ((x0, x1) if direction == "EW" else (y0, y1)):
            raise FHImportError("Contact refinement exceeds floating-point resolution")
        cell.children = [_Cell(*bound) for bound in bounds]
        cell.split = direction

    def read_tree(self, path):
        with open(path, encoding="utf-8-sig") as stream:
            lines = iter(enumerate(stream, 1))
            try:
                number, line = next(lines)
                total = _integer(_float(line.split()[0]), "Hierarchy cell count")
            except (StopIteration, IndexError):
                raise FHImportError("%s: missing hierarchy cell count" % path)
            if total > FH_MAX_CELLS:
                raise FHImportError("Hierarchy cell limit exceeded")
            records = {}
            for number, line in lines:
                self.progress.check("Reading plane discretization", number, total+1)
                fields = line.split()
                if not fields:
                    continue
                try:
                    index = int(fields[0])
                    kind = fields[1].upper()
                    if not 1 <= index <= total or index in records:
                        raise ValueError("duplicate or out-of-range cell ID")
                    if kind == "NONE" and len(fields) == 2:
                        records[index] = None
                    elif kind == "B" and len(fields) == 5 and fields[2].upper() in ("EW", "NS"):
                        records[index] = (fields[2].upper(), int(fields[3]), int(fields[4]))
                    else:
                        raise ValueError("expected ID NONE or ID B EW/NS CHILD1 CHILD2")
                except (ValueError, IndexError) as error:
                    raise FHImportError("%s:%d: %s" % (path, number, error))
            if len(records) != total:
                raise FHImportError("%s: expected %d cell records" % (path, total))
        seen = set()
        stack = [(1, self.root)]
        while stack:
            index, cell = stack.pop()
            if index in seen or index not in records:
                raise FHImportError("%s: cyclic, shared, or missing hierarchy cell %d" % (path, index))
            seen.add(index)
            record = records[index]
            if record:
                self.split(cell, record[0])
                stack.extend(zip(record[1:], cell.children))
        if len(seen) != total:
            raise FHImportError("%s: unreachable hierarchy cells" % path)

    def initial_grid(self, nx, ny, mesh=False):
        if self.root.children:
            raise FHImportError("initial_grid requires an undivided plane (file=NONE)")
        nx, ny = _integer(nx, "Grid X count"), _integer(ny, "Grid Y count")
        self._reserve(nx*ny)
        root = self.root
        dx, dy = root.x1/nx, root.y1/ny
        root.grid = (nx, ny)
        for row in range(ny):
            for col in range(nx):
                self.progress.check("Discretizing nonuniform planes")
                # Preserve set_grid_coords operation order: rounding at a
                # subsequent binary split can select a different point cell.
                left, top = col*dx, root.y1-row*dy
                root.children.append(_Cell(left, top-dy, left+dx, top,
                                           hole=mesh and row % 2 == 1 and col % 2 == 1))

    def cut(self, x, y, max_x, max_y, cell=None):
        _positive(max_x, "Maximum cell X width")
        _positive(max_y, "Maximum cell Y width")
        cell = (cell or self.root).containing(x, y)
        if cell.hole:
            return cell
        while max_x < cell.x1-cell.x0 or max_y < cell.y1-cell.y0:
            direction = "EW" if (cell.x1-cell.x0)/max_x > (cell.y1-cell.y0)/max_y else "NS"
            self.split(cell, direction)
            cell = cell.containing(x, y)
        return cell

    def walk(self, x0, y0, x1, y1, max_x, max_y):
        # Follow the C line walker: cut the containing leaf, advance to its
        # boundary, then enter the neighboring leaf in the travel direction.
        dx, dy = x1-x0, y1-y0
        if dx == dy == 0:
            return
        t = 0.
        cell = self.root.containing(x0, y0)
        previous = None
        visited = set()
        while t < 1-_EPS:
            state = (t, id(cell))
            if previous is not None and t > previous[0]:
                visited.clear()
            if state in visited:
                raise FHImportError("Cannot traverse a refined contact boundary")
            previous = state
            visited.add(state)
            self.progress.check("Refining plane contacts")
            x, y = x0+t*dx, y0+t*dy
            tolerance = 1e-12 * max(self.root.x1, self.root.y1)
            if not (cell.x0-tolerance <= x <= cell.x1+tolerance and
                    cell.y0-tolerance <= y <= cell.y1+tolerance):
                raise FHImportError("Contact line extends outside the plane")
            cell = self.cut(x, y, max_x, max_y, cell)
            tx = ((cell.x1 if dx > 0 else cell.x0)-x0)/dx if dx else math.inf
            ty = ((cell.y1 if dy > 0 else cell.y0)-y0)/dy if dy else math.inf
            advance = min(tx, ty)
            if advance >= 1-_EPS:
                break
            if advance < t-1e-12:
                raise FHImportError("Cannot advance along contact line")
            t = max(t, advance)
            # nextafter, rather than a fixed spatial epsilon, retains very
            # small refined cells and the C walker's positive-side edge choice.
            x, y = x0+t*dx, y0+t*dy
            if tx == advance:
                x = cell.x1 if dx > 0 else cell.x0
            if ty == advance:
                y = cell.y1 if dy > 0 else cell.y0
            x = math.nextafter(x, math.inf if dx >= 0 else -math.inf)
            y = math.nextafter(y, math.inf if dy > 0 else -math.inf)
            neighbor = self.root.containing(x, y)
            # Normalized grid/binary tests can round a one-ULP step back onto
            # the old side. The C walker follows explicit node adjacency;
            # step only until that neighboring leaf is actually selected.
            for _ in range(32):
                if neighbor is not cell:
                    break
                x = math.nextafter(x, math.inf if dx >= 0 else -math.inf)
                y = math.nextafter(y, math.inf if dy > 0 else -math.inf)
                neighbor = self.root.containing(x, y)
            cell = neighbor
            if (dx > 0 and x > self.root.x1 or dx < 0 and x < 0 or
                    dy > 0 and y > self.root.y1 or dy < 0 and y < 0):
                raise FHImportError("Contact line extends outside the plane")

    def rect(self, x, y, wx, wy, max_x, max_y):
        for value, name in ((wx, "Rectangle X width"), (wy, "Rectangle Y width"),
                            (max_x, "Maximum cell X width"), (max_y, "Maximum cell Y width")):
            _positive(value, name)
        xl, xr = max(0., x-wx/2), min(self.root.x1, x+wx/2)
        yl, yr = max(0., y-wy/2), min(self.root.y1, y+wy/2)
        if xr <= xl or yr <= yl:
            raise FHImportError("Contact rectangle is outside the plane")
        # CONTACT.C:cut_inside_rect walks equally spaced vertical then
        # horizontal lines, including all four rectangle boundaries.
        xt = xl
        while xt < xr:
            self.walk(xt, yl, xt, yr, max_x, max_y)
            nxt = xt+max_x
            if nxt == xt:
                raise FHImportError("Contact resolution is too small")
            xt = nxt
        self.walk(xr, yl, xr, yr, max_x, max_y)
        yt = yl
        while yt < yr:
            self.walk(xl, yt, xr, yt, max_x, max_y)
            nxt = yt+max_y
            if nxt == yt:
                raise FHImportError("Contact resolution is too small")
            yt = nxt
        self.walk(xl, yr, xr, yr, max_x, max_y)
        return (xl, yl, xr, yr)

    def decay(self, x, y, wx, wy, mx, my, stop_x, stop_y):
        for value in (wx, wy, mx, my):
            _positive(value, "Decay rectangle width")
        xl, xr = max(0., x-wx/2), min(self.root.x1, x+wx/2)
        yl, yr = max(0., y-wy/2), min(self.root.y1, y+wy/2)
        x, y, wx, wy = (xl+xr)/2, (yl+yr)/2, xr-xl, yr-yl
        _positive(wx, "Clipped rectangle X width")
        _positive(wy, "Clipped rectangle Y width")
        if wx <= mx:
            mx = .99*wx
        if wy < my:
            my = .99*wy
        while True:
            xl, xr = max(0., x-wx/2), min(self.root.x1, x+wx/2)
            yl, yr = max(0., y-wy/2), min(self.root.y1, y+wy/2)
            self.rect((xl+xr)/2, (yl+yr)/2, xr-xl, yr-yl, mx, my)
            if not ((mx < stop_x or my < stop_y or stop_x < 0 or stop_y < 0) and
                    (xl > 0 or xr < self.root.x1 or yl > 0 or yr < self.root.y1)):
                break
            rx, ry = mx/wx, my/wy
            if rx >= 1 or ry >= 1:
                raise FHImportError("Invalid decay rectangle cell/rectangle ratio")
            wx, wy, mx, my = wx/(1-rx), wy/(1-ry), wx*rx/(1-rx), wy*ry/(1-ry)

    def contacts(self):
        # make_contactlist prepends: the solver processes contacts in reverse
        # source order, initial grids first, equivalences last (no geometry).
        calls = list(reversed(self.plane.contacts))
        for call in calls:
            if call.kind.startswith("initial"):
                if len(call.values) != 2:
                    raise FHImportError("Initial grid requires two values")
                self.initial_grid(*call.values, mesh=call.kind == "initial_mesh_grid")
        arities = {"point": 5, "line": 8, "rect": 7, "decay_rect": 9,
                   "equiv_rect": 5, "connection": 6, "trace": 8}
        for call in calls:
            kind, values = call.kind, call.values
            if kind.startswith("initial"):
                continue
            if len(values) != arities[kind]:
                raise FHImportError("Contact %s requires %d values" % (kind, arities[kind]))
            x, y, _ = self.plane.local(_add(values[:3], call.offset))
            if kind == "equiv_rect":
                continue  # Changes electrical equivalence, not displayed geometry.
            if kind == "point":
                if not (0 <= x <= self.root.x1 and 0 <= y <= self.root.y1):
                    raise FHImportError("Contact point is outside the plane")
                self.cut(x, y, *values[3:5])
            elif kind == "rect":
                self.rect(x, y, *values[3:])
            elif kind in ("decay_rect", "connection"):
                if kind == "connection":
                    ratio = _positive(values[5], "Connection refinement ratio")
                    args = (values[3], values[4], values[3]/ratio, values[4]/ratio, -1., -1.)
                else:
                    args = values[3:]
                self.decay(x, y, *args)
            elif kind in ("line", "trace"):
                x1, y1, _ = self.plane.local(_add(values[3:6], call.offset))
                if not all((0 <= a <= self.root.x1 and 0 <= b <= self.root.y1)
                           for a, b in ((x, y), (x1, y1))):
                    raise FHImportError("Contact line endpoints are outside the plane")
                if kind == "line":
                    self.walk(x, y, x1, y1, *values[6:])
                else:
                    self.trace(x, y, x1, y1, values[6], values[7])

    def trace(self, x0, y0, x1, y1, width, factor):
        _positive(width, "Trace width")
        if factor < 1:
            raise FHImportError("Trace factor must be at least one")
        dx, dy = x1-x0, y1-y0
        length = math.hypot(dx, dy)
        _positive(length, "Trace length")
        half = width/2
        if dx == 0:
            mx, my = half, abs(dy)
        elif dy == 0:
            mx, my = abs(dx), half
        else:
            tangent = abs(dy/dx)
            scale = factor**tangent if tangent <= 1 else (1/factor)**tangent
            mx, my = ((half/tangent*scale, half*scale) if tangent <= 1
                      else (half*scale, half/tangent*scale))
        mx, my = min(mx, length), min(my, length)
        for offset, ratio in ((0, 1), (1, 1), (-1, 1), (3, 2), (-3, 3)):
            sx, sy = -dy/length*half*offset, dx/length*half*offset
            self.walk(x0+sx, y0+sy, x1+sx, y1+sy, mx*ratio, my*ratio)

    def segments(self):
        # For each local axis, sweep leaf edge intervals. Contributions on
        # either side supply the outer bounds used by get_width_and_shift().
        leaves = list(self.root.leaves())
        def canonical(values, length):
            # C grid nodes are shared by identity even where neighboring cell
            # bounds differ by a few ULPs. Reconcile only rounding-sized gaps,
            # after all contact decisions have used the original coordinates.
            mapping = {}
            previous = None
            for value in sorted(set(values)):
                self.progress.check("Resolving plane boundaries")
                adjusted = min(length, max(0., value))
                if previous is not None and abs(adjusted-previous) <= 4*max(math.ulp(length), math.ulp(adjusted), math.ulp(previous)):
                    mapping[value] = previous
                else:
                    previous = adjusted
                    mapping[value] = adjusted
            return mapping
        xs = canonical([v for c in leaves for v in (c.x0, c.x1)], self.root.x1)
        ys = canonical([v for c in leaves for v in (c.y0, c.y1)], self.root.y1)
        for vertical in (True, False):
            lines = defaultdict(list)
            for original in leaves:
                cell = _Cell(xs[original.x0], ys[original.y0], xs[original.x1], ys[original.y1], hole=original.hole)
                if cell.x1 <= cell.x0 or cell.y1 <= cell.y0:
                    raise FHImportError("Plane refinement exceeds coordinate precision")
                self.progress.check("Generating plane segments")
                if vertical:
                    edges = ((cell.x0, cell.y0, cell.y1, 1, cell.x1),
                             (cell.x1, cell.y0, cell.y1, -1, cell.x0))
                else:
                    edges = ((cell.y0, cell.x0, cell.x1, 1, cell.y1),
                             (cell.y1, cell.x0, cell.x1, -1, cell.y0))
                for at, begin, end, side, outer in edges:
                    # Hole edges still split neighboring intervals, but make
                    # zero width contributions on the missing-material side.
                    outer = at if cell.hole else outer
                    lines[at].append((begin, end, side, outer))
            for at, intervals in sorted(lines.items()):
                events = defaultdict(list)
                for ident, (begin, end, side, outer) in enumerate(intervals):
                    events[begin].append((True, ident, side, outer))
                    events[end].append((False, ident, side, outer))
                active = {}
                positions = sorted(events)
                for i, begin in enumerate(positions[:-1]):
                    self.progress.check("Generating plane segments")
                    for entering, ident, side, outer in events[begin]:
                        if entering:
                            active[ident] = (side, outer)
                        else:
                            active.pop(ident, None)
                    if not active:
                        continue
                    end = positions[i+1]
                    lower = min((outer for side, outer in active.values() if side == -1), default=at)
                    upper = max((outer for side, outer in active.values() if side == 1), default=at)
                    width = (upper-lower)/2
                    if width <= 0:
                        continue
                    center = at/2+(upper+lower)/4
                    a, b = ((center, begin, 0.), (center, end, 0.)) if vertical else ((begin, center, 0.), (end, center, 0.))
                    yield self.plane.segment(a, b, width,
                                             self.plane.ux if vertical else self.plane.uy)


class _Plane:
    def __init__(self, name, params, holes, contacts, line):
        self.name, self.params, self.holes, self.contacts, self.line = name, params, holes, contacts, line
        self.corners = [tuple(params[axis+str(i)] for axis in "xyz") for i in (1, 2, 3)]
        a, b, c = self.corners
        d1, d2 = _sub(b, a), _sub(c, b)
        self.length1, self.length2 = math.sqrt(_dot(d1, d1)), math.sqrt(_dot(d2, d2))
        self.ux, self.uy = _unit(d1), _unit(d2)
        if abs(_dot(self.ux, self.uy)) > 1e-8:
            raise FHImportError("Plane corners must form perpendicular edges")
        self.normal = _unit(_cross(self.ux, self.uy))
        self.thickness = _positive(params["thick"], "Plane thickness")
        self.nonuniform = "file" in params
        self.counter = 0

    def local(self, point):
        relative = _sub(point, self.corners[0])
        return (_dot(relative, self.ux), _dot(relative, self.uy), _dot(relative, self.normal))

    def global_point(self, point):
        return _add(self.corners[0], _add(_mul(self.ux, point[0]), _add(_mul(self.uy, point[1]), _mul(self.normal, point[2]))))

    def segment(self, a, b, width, width_direction):
        self.counter += 1
        return FHSegmentGeometry("%s_%d" % (self.name, self.counter), self.global_point(a),
                                 self.global_point(b), width, self.thickness,
                                 width_direction, self.name, self.line)

    def uniform_segments(self, progress, warnings):
        p = self.params
        nx, ny = _integer(p["seg1"], "seg1"), _integer(p["seg2"], "seg2")
        if nx*(ny+1)+ny*(nx+1) > FH_MAX_SEGMENTS:
            raise FHImportError("Uniform plane segment limit exceeded")
        dx, dy = self.length1/nx, self.length2/ny
        wx, wy = min(p.get("segwid1", dy), dy), min(p.get("segwid2", dx), dx)
        _positive(wx, "segwid1")
        _positive(wy, "segwid2")
        removed = set()
        # readGeom.c's uniform grid starts at corner 2 and runs towards corner
        # 1 (opposite the nonuniform local X axis) and towards corner 3.
        def nearest(point):
            x, y, _ = self.local(point)
            i, j = int((self.length1-x)/dx+.5), int(y/dy+.5)
            if not (0 <= i <= nx and 0 <= j <= ny):
                raise FHImportError("Hole reference is outside plane " + self.name)
            return i, j
        for hole in self.holes:
            values = hole.values
            point = _add(values[:3], hole.offset)
            i, j = nearest(point)
            if hole.kind == "point":
                removed.add((i, j))
            elif hole.kind == "rect":
                i2, j2 = nearest(_add(values[3:6], hole.offset))
                for a in range(min(i, i2), max(i, i2)+1):
                    for b in range(min(j, j2), max(j, j2)+1):
                        progress.check("Applying plane holes")
                        removed.add((a, b))
            elif hole.kind == "circle":
                radius = _positive(values[3], "Hole radius")
                x, y, _ = self.local(point)
                ref1, ref2 = (self.length1-i*dx)-x, j*dy-y
                ref1 = -ref1  # Projection onto uniform X, toward corner 1.
                # Preserve HOLE.C's coarse-grid guard and C integer truncation.
                if ref1*ref1+ref2*ref2 > radius:
                    warnings.append("Plane %s: discretization too coarse for circular hole" % self.name)
                    continue
                for a in range(int((-radius-ref1)/dx), int((radius-ref1)/dx)+1):
                    edge = math.sqrt(max(0., radius*radius-(ref1+a*dx)**2))
                    if -edge-ref2 < 0 < edge-ref2:
                        for b in range(int((-edge-ref2)/dy), int((edge-ref2)/dy)+1):
                            progress.check("Applying plane holes")
                            if 0 <= i+a <= nx and 0 <= j+b <= ny:
                                removed.add((i+a, j+b))
        for j in range(ny+1):
            for i in range(nx):
                progress.check("Generating plane segments")
                if (i, j) not in removed and (i+1, j) not in removed:
                    yield self.segment((self.length1-i*dx, j*dy, 0.),
                                       (self.length1-(i+1)*dx, j*dy, 0.), wx, _mul(self.uy, -1))
        for i in range(nx+1):
            for j in range(ny):
                progress.check("Generating plane segments")
                if (i, j) not in removed and (i, j+1) not in removed:
                    yield self.segment((self.length1-i*dx, j*dy, 0.),
                                       (self.length1-i*dx, (j+1)*dy, 0.), wy, _mul(self.ux, -1))


def _plane_definition(name, text, units, line):
    params, holes, contacts = {}, [], []
    offset = (0., 0., 0.)
    position = 0
    lengths = {axis+str(i) for axis in "xyz" for i in (1, 2, 3)} | {"thick", "segwid1", "segwid2", "relx", "rely", "relz"}
    allowed = lengths | {"seg1", "seg2", "sigma", "rho", "nhinc", "rh", "file"}
    kinds = {"point": 3, "rect": 6, "circle": 4}
    contact_kinds = {"point", "line", "rect", "decay_rect", "equiv_rect", "initial_grid", "initial_mesh_grid", "trace", "connection"}
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        assignment = _ASSIGNMENT.match(text, position)
        call = _CALL.match(text, position)
        node = _NODE.match(text, position)
        if assignment:
            key, value = assignment[1].lower(), assignment[2]
            if key not in allowed:
                raise FHImportError("Unrecognized plane parameter: " + key)
            value = value.strip('"\'') if key == "file" else _float(value)
            params[key] = value*units if key in lengths else value
            if key in ("relx", "rely", "relz"):
                offset = tuple(params.get("rel"+axis, 0.) for axis in "xyz")
            position = assignment.end()
        elif call:
            category, kind, call_name = call[1].lower(), call[2].lower(), call[3] or ""
            values = tuple(_float(v.strip()) for v in call[4].split(","))
            if category == "hole":
                if kind.startswith("user"):
                    # HOLE.C's seven user extension hooks have empty bodies.
                    position = call.end()
                    continue
                if kind not in kinds or len(values) != kinds[kind]:
                    raise FHImportError("Invalid hole type or number of values: " + kind)
                holes.append(_PlaneCall(kind, tuple(v*units for v in values), offset))
            else:
                if kind not in contact_kinds:
                    raise FHImportError("Unknown plane contact: " + kind)
                # Grid counts, trace factor and connection ratio are dimensionless.
                values = tuple(v if kind.startswith("initial") or
                               kind == "trace" and i == 7 or kind == "connection" and i == 5
                               else v*units for i, v in enumerate(values))
                contacts.append(_PlaneCall(kind, values, offset, call_name))
            position = call.end()
        elif node:
            # Plane user-node references establish electrical aliases only.
            coords = [v.strip() for v in node[2].split(",")]
            # readGeom.c's last sscanf accepts (x,y) as missing Z as well
            # as the explicitly empty third component (x,y,).
            if len(coords) == 2 and all(coords):
                coords.append("")
            if len(coords) != 3 or sum(not v for v in coords) > 1:
                raise FHImportError("Invalid plane node coordinates")
            for value in coords:
                if value:
                    _float(value)
            position = node.end()
        else:
            raise FHImportError("Unrecognized plane text: " + text[position:])
    required = {axis+str(i) for axis in "xyz" for i in (1, 2, 3)} | {"thick"}
    if not required <= params.keys():
        raise FHImportError("Missing plane parameters: " + ", ".join(sorted(required-params.keys())))
    if "file" in params and ("seg1" in params or "seg2" in params):
        raise FHImportError("A plane cannot specify both file and seg1/seg2")
    if "file" not in params and not {"seg1", "seg2"} <= params.keys():
        raise FHImportError("Uniform planes require seg1 and seg2")
    if params.get("rh", 2.) < 1:
        raise FHImportError("Plane rh must be at least one")
    return _Plane(name, params, holes, contacts, line)


def get_fasthenry_input_files(filename, progress=None):
    """Root input plus distinct file= discretizations, never recursive inputs.

    Discovery intentionally tolerates other malformed statements so the editor
    can open files when a geometry import fails. file=NONE is not a file.
    """
    root = _path(filename)
    files, seen = [root], {_identity(root)}
    for number, text in _logical_lines(root, _Progress(progress)):
        if text.lower().startswith(".end"):
            break
        if not text.lower().startswith("g"):
            continue
        # Remove call bodies before looking for file assignments.
        text = re.sub(r"\([^)]*\)", "", text)
        for match in _ASSIGNMENT.finditer(text):
            if match[1].lower() != "file":
                continue
            value = match[2].strip('"\'')
            if value.lower() == "none":
                continue
            path = _path(value, os.path.dirname(root))
            if _identity(path) not in seen:
                files.append(path)
                seen.add(_identity(path))
    return files


def parse_fasthenry(filename, progress=None):
    """Read native input into an unrefined segment geometry snapshot.

    No FreeCAD document is created. Raises FHImportError/OSError or
    FHImportCancelled. Case-insensitive entity names and ordered defaults match
    readGeom.c; paths preserve case on case-sensitive hosts.
    """
    root = _path(filename)
    model = FHGeometry(root, [root])
    reporter = _Progress(progress)
    reporter.check("Reading FastHenry input", force=True)
    nodes, names, planes = {}, set(), []
    units = 1.
    defaults = {"sigma": 5.8e7, "nhinc": 1, "nwinc": 1, "rh": 2., "rw": 2.}
    ended = False
    segment_keys = {"w", "h", "sigma", "rho", "nhinc", "nwinc", "rh", "rw", "wx", "wy", "wz"}
    default_keys = {"x", "y", "z", "w", "h", "sigma", "rho", "nhinc", "nwinc", "rh", "rw"}
    for number, text in _logical_lines(root, reporter):
        try:
            fields = text.split(None, 1)
            name, rest = fields[0], fields[1] if len(fields) > 1 else ""
            key = name.lower()
            if key.startswith("."):
                key = {"uni": ".units", "def": ".default", "ext": ".external",
                       "equ": ".equiv", "fre": ".freq", "end": ".end"}.get(key[1:4], key)
            if key == ".end":
                ended = True
                break
            if key == ".units":
                unit = rest.strip().lower()
                for prefix, scale in (("mil", 2.54e-5), ("in", .0254), ("um", 1e-6),
                                      ("mm", 1e-3), ("cm", 1e-2), ("m", 1.), ("km", 1e3)):
                    if unit.startswith(prefix):
                        units = scale
                        break
                else:
                    raise FHImportError("Unknown unit: " + rest)
            elif key == ".default":
                values = _assignments(rest, default_keys)
                for parameter, value in values.items():
                    if parameter in ("x", "y", "z", "w", "h"):
                        value *= units
                    elif parameter == "sigma":
                        value /= units
                    elif parameter == "rho":
                        parameter, value = "sigma", 1/(_positive(value, "rho")*units)
                    defaults[parameter] = value
            elif key == ".equiv":
                aliases = rest.lower().split()
                reference = next((nodes[n] for n in aliases if n in nodes), None)
                if reference is not None:
                    # New names alias an existing node; already defined nodes
                    # keep their own coordinates even when electrically shorted.
                    for alias in aliases:
                        nodes.setdefault(alias, reference)
            elif key in (".external", ".freq"):
                # Electrical constraints and frequency sweeps do not change
                # writefastcap.c's unrefined segment surfaces.
                continue
            elif key.startswith("n"):
                if key in names:
                    raise FHImportError("Duplicate node: " + name)
                values = _assignments(rest, {"x", "y", "z"})
                nodes[key] = tuple(values[a]*units if a in values else defaults[a] for a in "xyz")
                names.add(key)
            elif key.startswith("e"):
                parts = rest.split(None, 2)
                if len(parts) < 2:
                    raise FHImportError("A segment requires two nodes")
                a, b = nodes[parts[0].lower()], nodes[parts[1].lower()]
                values = _assignments(parts[2] if len(parts) > 2 else "", segment_keys)
                w = values["w"]*units if "w" in values else defaults["w"]
                h = values["h"]*units if "h" in values else defaults["h"]
                direction = None
                if {"wx", "wy", "wz"} & values.keys():
                    direction = tuple(values[a] for a in ("wx", "wy", "wz"))
                for ratio in ("rh", "rw"):
                    if values.get(ratio, defaults[ratio]) < 1:
                        raise FHImportError(ratio + " must be at least one")
                for count in ("nhinc", "nwinc"):
                    _integer(values.get(count, defaults[count]), count)
                model.append(FHSegmentGeometry(name, a, b, w, h, direction, source_line=number))
                names.add(key)
            elif key.startswith("g"):
                if key in names:
                    raise FHImportError("Duplicate plane: " + name)
                plane = _plane_definition(name, rest, units, number)
                planes.append(plane)
                model.plane_names.append(name)
                names.add(key)
            else:
                raise FHImportError("Unknown FastHenry statement: " + name)
        except (ValueError, KeyError, ZeroDivisionError) as error:
            raise FHImportError("%s:%d: %s" % (root, number, error)) from error
    if not ended:
        raise FHImportError(root + ": missing .end statement")
    for index, plane in enumerate(planes):
        reporter.check("Discretizing ground planes", index, len(planes), force=True)
        try:
            if plane.nonuniform:
                mesh = _NonuniformPlane(plane, reporter)
                path = plane.params["file"]
                if path.lower() != "none":
                    path = _path(path, os.path.dirname(root))
                    if _identity(path) not in {_identity(p) for p in model.files}:
                        model.files.append(path)
                    mesh.read_tree(path)
                # readGeom.c only applies 'hole' to uniform planes. Nonuniform
                # holes are generated by contact initial_mesh_grid instead.
                if plane.holes:
                    model.warnings.append("Plane %s: hole statements are ignored by FastHenry for nonuniform planes" % plane.name)
                mesh.contacts()
                segments = mesh.segments()
            else:
                if plane.contacts:
                    model.warnings.append("Plane %s: contacts are ignored by FastHenry for uniform planes" % plane.name)
                segments = plane.uniform_segments(reporter, model.warnings)
            for segment in segments:
                model.append(segment)
        except (ValueError, OSError) as error:
            raise FHImportError("%s:%d: plane %s: %s" % (root, plane.line, plane.name, error)) from error
    reporter.check("Geometry ready", len(model.segments), len(model.segments), force=True)
    if not model.segments:
        raise FHImportError(root + ": no segment geometry found")
    return model


def read_fasthenry_file(filename, folder=None, progress=None, end_caps=False):
    """Build grouped Part faces, following FCImport's Part::Compound layout.

    Returns the outer compound, or False on error/cancellation. All objects
    created by this call are removed on failure, also for scripted imports.
    """
    import FreeCAD
    import Part

    path = _path(filename, folder)
    created = []
    document = None
    reporter = _Progress(progress)
    try:
        model = parse_fasthenry(path, progress)
        for warning in model.warnings:
            FreeCAD.Console.PrintWarning(warning + "\n")
        document = FreeCAD.ActiveDocument
        if document is None:
            document = FreeCAD.newDocument()
        groups = defaultdict(list)
        for segment in model.segments:
            groups[segment.group].append(segment)
        children = []
        colors = []
        done = 0
        total = len(model.segments)
        reporter.check("Building FastHenry geometry", 0, total, force=True)
        for group, segments in groups.items():
            faces, face_indices = [], []
            for index, segment in enumerate(segments):
                for vertices in segment_faces(segment, end_caps):
                    points = [FreeCAD.Vector(*_mul(v, 1000.)) for v in vertices]
                    faces.append(Part.Face(Part.makePolygon(points+[points[0]])))
                    face_indices.append(index)
                done += 1
                reporter.check("Building FastHenry geometry", done, total)
            reporter.check("Grouping FastHenry surfaces", done, total, force=True)
            child = document.addObject("Part::Feature", "FastHenry_Element")
            created.append(child.Name)
            child.Label = group
            child.Shape = Part.makeCompound(faces)
            child.addProperty("App::PropertyString", "ElementType", "FastHenry")
            child.ElementType = "GroundPlane" if group in model.plane_names else "Segments"
            child.addProperty("App::PropertyStringList", "SegmentNames", "FastHenry")
            child.SegmentNames = [s.name for s in segments]
            child.addProperty("App::PropertyIntegerList", "FaceSegmentIndices", "FastHenry")
            child.FaceSegmentIndices = face_indices
            child.addProperty("App::PropertyIntegerList", "SourceLines", "FastHenry")
            child.SourceLines = [s.source_line for s in segments]
            if FreeCAD.GuiUp:
                color = (.80, .60, .25) if group == "Segments" else (.55, .70, .85)
                child.ViewObject.ShapeColor = color
                colors.extend([color] * len(faces))
            children.append(child)
        result = document.addObject("Part::Compound", "FastHenry_Compound")
        created.append(result.Name)
        result.Label = "FastHenry geometry"
        result.Links = children
        result.addProperty("App::PropertyPath", "SourceFile", "FastHenry")
        result.SourceFile = path
        result.addProperty("App::PropertyStringList", "InputFiles", "FastHenry")
        result.InputFiles = model.files
        result.addProperty("App::PropertyStringList", "PlaneNames", "FastHenry")
        result.PlaneNames = model.plane_names
        result.addProperty("App::PropertyInteger", "SegmentCount", "FastHenry")
        result.SegmentCount = total
        reporter.check("Updating FastHenry view", total, total, force=True)
        document.recompute()
        if FreeCAD.GuiUp:
            # Part::Compound can hide its children and display its own Shape.
            result.ViewObject.DiffuseColor = colors
        reporter.check("FastHenry import complete", total, total, force=True)
        return result
    except FHImportCancelled:
        FreeCAD.Console.PrintMessage("FastHenry import cancelled.\n")
    except (OSError, ValueError, RuntimeError) as error:
        FreeCAD.Console.PrintError("FastHenry import failed: %s\n" % error)
    except Exception:
        if document is not None:
            for name in reversed(created):
                if document.getObject(name) is not None:
                    document.removeObject(name)
        raise
    if document is not None:
        for name in reversed(created):
            if document.getObject(name) is not None:
                document.removeObject(name)
    return False
