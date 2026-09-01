#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2017                                                    *  
#*   FastFieldSolvers S.R.L.  http://www.fastfieldsolvers.com              *  
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

import FreeCAD, Mesh, Draft, Part, os
from collections import namedtuple
from FreeCAD import Vector

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtGui
else:
    def translate(ctxt,txt):
        return txt

__title__="FreeCAD E.M. FasterCap Importer"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

DEF_FOLDER = "."
COLORMAP_LEN = 256
AUTOREFINE_MAX_PARSE_LEVEL = 32

# filePosMap members
filePosData = namedtuple('filePosData', ['lineNum', 'filePos'])

# global vars
#
m_lDielNum = 0
m_lCondNum = 0
m_iParseLevel = -1
m_iGroupNum = [1]
m_lGroupDielNum = 0 
m_bUseMesh = True
# number of input panels
m_ulInputPanelNum = 0


# report parser diagnostics through the FreeCAD console
def _fc_message(kind, message):
    printer = (FreeCAD.Console.PrintError if kind == "Error"
               else FreeCAD.Console.PrintWarning)
    printer("%s: %s\n" % (kind, message))


def _fc_complex(value):
    """Parse FastCap's compact ``a-jb`` complex-number notation."""
    value = value.strip().lower().replace("i", "j")
    if "j" not in value:
        return complex(float(value))
    value = value.replace("+j", "+").replace("-j", "-") + "j"
    return complex(value)


# convert an optional FastCap hexadecimal RGB value to a FreeCAD color tuple
def _fc_color(value):
    if not value.lower().startswith("0x"):
        return None
    hex_color = value[2:]
    if len(hex_color) not in (6, 8):
        raise ValueError("color '%s' must be 0xRRGGBB or 0xRRGGBBAA" % value)
    # FasterCap sample files and FreeCAD Python color tuples both use RGBA,
    # where alpha 0.0 is transparent and alpha 1.0 is opaque.
    alpha = int(hex_color[6:8], 16) / 255.0 if len(hex_color) == 8 else 1.0
    return (int(hex_color[0:2], 16) / 255.0,
            int(hex_color[2:4], 16) / 255.0,
            int(hex_color[4:6], 16) / 255.0, alpha)


def _fc_record(fields):
    """Normalize the long and abbreviated embedded-file keywords."""
    if not fields:
        return ""
    record = fields[0].upper()
    if record in ("F", "FILE"):
        return "F"
    if record in ("E", "END"):
        return "E"
    return record


# build the equivalent of FasterCap CreateFileMap() for combined input files
def _fc_embedded_files(lines):
    """Index the ``File name``/``End`` subfiles in a combined input file."""
    files = {}
    current = None
    for line_number, line in lines:
        fields = line.split()
        record = _fc_record(fields)
        if record == "F":
            if len(fields) < 2:
                raise ValueError("line %d: File record has no name" % line_number)
            current = fields[1]
            files[current] = []
        elif record == "E":
            current = None
        elif current is not None:
            files[current].append((line_number, line))
    return files


# read text together with original line numbers for contextual parse errors
def _fc_read_lines(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as stream:
        return list(enumerate(stream, 1))


# append a panel or segment to its electrical conductor / dielectric group
def _fc_add_geometry(groups, name, kind, geometry):
    group = groups.setdefault(name, {"kind": kind, "panels": [], "segments": []})
    group["panels" if len(geometry) == 3 else "segments"].append(geometry)


# convert panel densities to face colors using one min/max range for the full
# hierarchy of external and embedded input files
def _fc_density_coloring(groups):
    """Return face colors and the global density range.

    The density range covers the complete input hierarchy rather than an
    individual include file or conductor.
    """
    densities = [density
                 for group in groups.values()
                 for _vertices, _color, density in group["panels"]
                 if density is not None]
    if not densities:
        return None, None, None

    density_min = min(densities)
    density_max = max(densities)
    # colormap() belongs to the legacy importer and returns RGBT tuples with
    # a zero fourth component. Convert its RGB output to opaque RGBA tuples
    # before assigning it to FreeCAD's current DiffuseColor property.
    legacy_gradient = colormap([(0.0, 1.0, 1.0), (0.0, 0.0, 1.0),
                                (0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                                (1.0, 1.0, 0.0)])
    gradient = [(red, green, blue, 1.0)
                for red, green, blue, _transparency in legacy_gradient]
    if density_max == density_min:
        # A constant field has no low/high end. Use the map center instead of
        # dividing by zero or suggesting a false extremum.
        def density_index(_density):
            return (COLORMAP_LEN - 1) // 2
    else:
        scale = (COLORMAP_LEN - 1) / float(density_max - density_min)

        def density_index(density):
            return max(0, min(COLORMAP_LEN - 1,
                              int((density - density_min) * scale)))

    colors = []
    default_color = (0.8, 0.8, 0.8, 1.0)
    for group in groups.values():
        for _vertices, explicit_color, density in group["panels"]:
            if density is not None:
                colors.append(gradient[density_index(density)])
            elif explicit_color is not None:
                colors.append(explicit_color)
            else:
                colors.append(default_color)
    return colors, density_min, density_max


# create either one Mesh per electrical element or a nested Part compound;
# the outer compound contains one child compound per conductor or dielectric
def _fc_build_result(groups, use_part_type, is_2d):
    """Build one child shape per electrical conductor or dielectric."""
    if use_part_type == "mesh" and not is_2d:
        meshes = []
        for name, group in groups.items():
            triangles = []
            for vertices, _color, _density in group["panels"]:
                if len(vertices) == 3:
                    triangles.extend(vertices)
                else:
                    triangles.extend((vertices[0], vertices[1], vertices[2],
                                      vertices[0], vertices[2], vertices[3]))
            mesh = Mesh.Mesh(triangles)
            Mesh.show(mesh)
            meshes.append(mesh)
        return meshes

    group_shapes = []
    group_names = []
    group_types = []
    explicit_face_colors = []
    for name, group in groups.items():
        shapes = []
        panel_colors = []
        for vertices, color, _density in group["panels"]:
            wire = Part.makePolygon(vertices + [vertices[0]])
            shapes.append(Part.Face(wire))
            panel_colors.append(color)
        for start, end, _color, _density in group["segments"]:
            shapes.append(Part.makeLine(start, end))
        if not shapes:
            continue
        group_shapes.append(Part.makeCompound(shapes))
        group_names.append(name)
        group_types.append(group["kind"])
        explicit_face_colors.extend(panel_colors)

    outer_compound = Part.makeCompound(group_shapes)
    document = FreeCAD.ActiveDocument
    if document is None:
        document = FreeCAD.newDocument()
    feature = document.addObject("Part::Feature", "FasterCap_Compound")
    feature.Label = "FasterCap / FastCap geometry"
    feature.Shape = outer_compound
    feature.addProperty("App::PropertyStringList", "ElementNames", "FasterCap")
    feature.addProperty("App::PropertyStringList", "ElementTypes", "FasterCap")
    feature.ElementNames = group_names
    feature.ElementTypes = group_types

    density_colors, density_min, density_max = _fc_density_coloring(groups)
    if density_colors is not None:
        feature.addProperty("App::PropertyFloat", "DensityMinimum", "FasterCap")
        feature.addProperty("App::PropertyFloat", "DensityMaximum", "FasterCap")
        feature.DensityMinimum = density_min
        feature.DensityMaximum = density_max
        feature.ViewObject.DiffuseColor = density_colors
    elif (explicit_face_colors and
          all(color is not None for color in explicit_face_colors)):
        feature.ViewObject.DiffuseColor = explicit_face_colors
    document.recompute()
    return feature

def read_fastcap_file(filename, folder=DEF_FOLDER, usePartType='compound'):
    '''Import a FasterCap/FastCap 2D or 3D input hierarchy.

    'filename' is the name of the FasterCap/FastCap input file
    'folder' is the folder where the input file resides
    'usePartType' selects a Part compound (default) or a set of Meshes

    The Part result is an outer compound containing one nested compound for
    every distinct conductor and dielectric interface. Panel charge densities,
    when present, are converted into face colors over the global density range.

    The function returns the new FreeCAD Part::Feature, a list of Meshes when
    usePartType is 'mesh', or False if the input cannot be parsed.

    Example:
    fastercapObj = read_fastcap_file('array_of_5_spheres.lst',
                                      'FasterCap/Samples/3D')
    '''
    #
    # this function is a Python implementation of CAutoRefine::ReadFastCapFile(),
    # CreateFileMap(), Parse3DInputFile(), and Parse2DInputFile() from FasterCap.
    # It indexes embedded files, recursively follows C and D references, collects
    # T, Q, or S geometry by electrical element, and finally creates the selected
    # FreeCAD representation.
    #
    global m_lDielNum, m_lCondNum, m_iParseLevel, m_iGroupNum
    global m_lGroupDielNum, m_sUsePartType, m_ulInputPanelNum

    # validate the requested FreeCAD representation before reading any files
    if usePartType not in ('compound', 'mesh'):
        _fc_message("Error", "usePartType must be 'compound' or 'mesh'")
        return False

    # resolve the input path before recursion; relative include names are resolved
    # from the directory of the file containing the reference
    root = os.path.abspath(os.path.join(folder, filename))
    if not os.path.isfile(root) or not os.access(root, os.R_OK):
        _fc_message("Error", "file '%s' is not readable" % root)
        return False

    # initialize the parser state for a new, independent import operation
    m_lDielNum = 0
    m_lCondNum = 0
    m_iParseLevel = -1
    m_iGroupNum = [1] * AUTOREFINE_MAX_PARSE_LEVEL
    m_lGroupDielNum = 0
    m_sUsePartType = usePartType
    m_ulInputPanelNum = 0

    # read the top-level file once and index any File / End definitions so the
    # same embedded geometry can be referenced multiple times with new offsets
    try:
        root_lines = _fc_read_lines(root)
        embedded = _fc_embedded_files(root_lines)
    except (OSError, ValueError) as error:
        _fc_message("Error", "cannot read '%s': %s" % (root, error))
        return False

    # FasterCap identifies a 2D problem by looking for 2D in the first line
    first_line = root_lines[0][1] if root_lines else ""
    is_2d = "2d" in first_line.lower()
    # preserve insertion order so compound children and face colors follow the
    # order in which conductors, dielectrics, and panels occur in the input
    groups = {}
    active_sources = []

    # parse() mirrors Parse2DInputFile() and Parse3DInputFile(). source_lines is
    # set only for a definition embedded between File and End statements; offset
    # is accumulated across references, group_prefix identifies the target
    # conductor or dielectric compound, and element_color carries the optional
    # color assigned on the enclosing C or D statement.
    def parse(source_name, source_lines=None, offset=Vector(0.0, 0.0, 0.0),
              is_dielectric=False, group_prefix="", element_color=None,
              depth=0):
        global m_lDielNum, m_lCondNum, m_iParseLevel, m_lGroupDielNum
        global m_ulInputPanelNum
        # enforce the same maximum nesting depth used by FasterCap
        if depth >= AUTOREFINE_MAX_PARSE_LEVEL:
            raise ValueError("maximum include depth (%d) exceeded at '%s'" %
                             (AUTOREFINE_MAX_PARSE_LEVEL, source_name))

        # keep a stack of active sources to detect circular file references
        source_path = os.path.abspath(source_name)
        identity = (source_path if source_lines is None
                    else "%s#embedded:%s" % (root, source_name))
        if identity in active_sources:
            raise ValueError("recursive include cycle involving '%s'" % source_name)
        active_sources.append(identity)
        m_iParseLevel = depth
        try:
            # an external definition is opened from disk; an embedded definition
            # instead reuses the lines indexed from the top-level combined file
            if source_lines is None:
                lines = _fc_read_lines(source_path)
                base_folder = os.path.dirname(source_path)
                local_embedded = _fc_embedded_files(lines)
            else:
                lines = source_lines
                base_folder = os.path.dirname(root)
                local_embedded = embedded

            # conductor group numbering is local to every parsing level
            group_number = 1
            in_embedded = False
            # scan only the current file section; embedded sections are parsed later
            # when referenced by a conductor or dielectric statement
            for line_number, raw_line in lines:
                fields = raw_line.split()
                if not fields or fields[0].startswith(("*", "#", ";")):
                    continue
                record = _fc_record(fields)
                if record == "F":
                    in_embedded = True
                    continue
                if record == "E":
                    in_embedded = False
                    continue
                if in_embedded or record == "N":
                    continue

                try:
                    # if a conductor or dielectric reference, validate its material data,
                    # accumulate its offset, and recursively parse its geometry file
                    if record in ('C', 'D'):
                        minimum = ((5 if is_2d else 6) if record == 'C'
                                   else (8 if is_2d else 10))
                        if len(fields) < minimum:
                            raise ValueError("too few fields for %s record" % record)
                        child_name = fields[1]
                        _fc_complex(fields[2])
                        coordinate = 3
                        if record == 'D':
                            _fc_complex(fields[3])
                            coordinate = 4
                        dimensions = 2 if is_2d else 3
                        values = [float(value) for value in
                                  fields[coordinate:coordinate + dimensions]]
                        if dimensions == 2:
                            values.append(0.0)
                        child_offset = offset + Vector(*values)
                        # C and D records may assign one color to the complete
                        # referenced element, after their other optional values.
                        child_color = next((_fc_color(value) for value in fields
                                            if value.lower().startswith("0x")),
                                           None)
                        # reproduce the FasterCap conductor grouping convention; a trailing
                        # plus sign joins this reference to the following conductor group

                        if record == 'C':
                            prefix_base = "g" if depth == 0 else group_prefix
                            child_group = "%s%d_" % (prefix_base, group_number)
                            optional_index = coordinate + dimensions
                            joined_to_next = (len(fields) > optional_index and
                                              fields[optional_index] == '+')
                            if not joined_to_next:
                                group_number += 1
                            m_lCondNum += 1
                        else:
                            child_group = "diel%d" % m_lGroupDielNum
                            m_lGroupDielNum += 1
                            m_lDielNum += 1

                        # embedded definitions take precedence over external files
                        child_lines = local_embedded.get(child_name)
                        if child_lines is not None:
                            parse(child_name, child_lines, child_offset,
                                  record == 'D', child_group, child_color,
                                  depth + 1)
                        else:
                            child_path = (child_name if os.path.isabs(child_name)
                                          else os.path.join(base_folder, child_name))
                            parse(child_path, None, child_offset,
                                  record == 'D', child_group, child_color,
                                  depth + 1)

                    # if a 3D triangular or quadrilateral panel, read all vertexes
                    elif record in ('T', 'Q') and not is_2d:
                        count = 3 if record == 'T' else 4
                        needed = 2 + count * 3
                        if len(fields) < needed:
                            raise ValueError("too few coordinates for %s panel" % record)
                        numbers = [float(value) for value in fields[2:needed]]
                        vertices = [offset + Vector(*numbers[index:index + 3])
                                    for index in range(0, len(numbers), 3)]
                        optional = fields[needed:]
                        trailing = optional[3:] if len(optional) >= 3 else optional
                        panel_color = _fc_color(trailing[-1]) if trailing else None
                        # a panel-specific color overrides the color inherited
                        # from its enclosing C or D element
                        color = panel_color if panel_color is not None else element_color
                        density = (None if not trailing or panel_color is not None
                                   else float(trailing[-1]))
                        name = group_prefix if is_dielectric else group_prefix + fields[1]
                        _fc_add_geometry(groups, name, "Dielectric" if is_dielectric
                                         else "Conductor", (vertices, color, density))
                        m_ulInputPanelNum += 1

                    # if a 2D segment, read its two endpoints and optional data
                    elif record == 'S' and is_2d:
                        if len(fields) < 6:
                            raise ValueError("too few coordinates for S segment")
                        start = offset + Vector(float(fields[2]), float(fields[3]), 0.0)
                        end = offset + Vector(float(fields[4]), float(fields[5]), 0.0)
                        optional = fields[6:]
                        trailing = optional[2:] if len(optional) >= 2 else optional
                        panel_color = _fc_color(trailing[-1]) if trailing else None
                        # a panel-specific color overrides the color inherited
                        # from its enclosing C or D element
                        color = panel_color if panel_color is not None else element_color
                        density = (None if not trailing or panel_color is not None
                                   else float(trailing[-1]))
                        name = group_prefix if is_dielectric else group_prefix + fields[1]
                        _fc_add_geometry(groups, name, "Dielectric" if is_dielectric
                                         else "Conductor", (start, end, color, density))
                        m_ulInputPanelNum += 1
                except (IndexError, TypeError, ValueError) as error:
                    raise ValueError("%s:%d: %s" %
                                     (source_name, line_number, error))
        # restore the recursion stack and current parsing level also on errors
        finally:
            active_sources.pop()
            m_iParseLevel = depth - 1

    try:
        # start parsing from the top-level FasterCap / FastCap file
        parse(root)
        if not groups:
            raise ValueError("no panel or segment records were found")
        return _fc_build_result(groups, usePartType, is_2d)
    except (OSError, ValueError) as error:
        _fc_message("Error", str(error))
        return False

def import_fastercap(filename, folder=DEF_FOLDER, use_mesh=True):
    '''Import file in FasterCap format as Mesh or Part.compound
        
    'filename' is the name of the export file
    'folder' is the folder where the file resides
        
    Example:
    fastercapObj = import_fastercap('cube.txt')
'''
    
    if not os.path.isdir(folder):
        FreeCAD.Console.PrintMessage("Error: '" + folder + "' is not a valid folder\n")
        return
        
    if not os.path.exists(folder + os.sep + filename):
        FreeCAD.Console.PrintMessage("Error: '" + filename + "' is not a valid file in the directory " + folder + "\n")
        return
        
    try:
        with open(folder + os.sep + filename, 'rb') as fid:
            # reset the list of triangle vertexes
            panelVertexes = []
            chargeDensity = []
            # and scan all the file
            for i, line in enumerate(fid):
                # if first line, or empty line, skip
                if i == 0 or line in ['', '\n', '\r\n']:
                    continue
                # now check for actual statements
                #
                # first split the line into the components
                splitLine = line.split()
                # if the line was actually composed only by separators, continue
                if len(splitLine) == 0:
                    continue

                # then check content
                #
                # if triangle
                if splitLine[0] == 'T':
                    try:
                        # if using mesh, we need a flat list of vertexed, that will be used in triplets
                        # to build the triangular-only mesh faces
                        if use_mesh == True:
                            panelVertexes.extend( [ [float(splitLine[2]), float(splitLine[3]), float(splitLine[4])],
                                                    [float(splitLine[5]), float(splitLine[6]), float(splitLine[7])],
                                                    [float(splitLine[8]), float(splitLine[9]), float(splitLine[10])] ])
                        # if using faces, we need FreeCAD.Vector or tuple of three floats for each vertex, in a vector
                        # with as many elements as the vertexes of the polygon supporting the face
                        else:
                            panelVertexes.append( [ (float(splitLine[2]), float(splitLine[3]), float(splitLine[4])),
                                                    (float(splitLine[5]), float(splitLine[6]), float(splitLine[7])),
                                                    (float(splitLine[8]), float(splitLine[9]), float(splitLine[10])) ])
                    except (IndexError, ValueError):
                        FreeCAD.Console.PrintMessage("Error on line " + format(i) + " : " + line + "\n")   
                    # if there is trailing charge density information, store it
                    if len(splitLine) >= 12:
                        chargeDensity.append(float(splitLine[11]))
                # if quadrilateral
                if splitLine[0] == 'Q':
                    try:
                        if use_mesh == True:
                            panelVertexes.extend( [ [float(splitLine[2]), float(splitLine[3]), float(splitLine[4])],
                                                    [float(splitLine[5]), float(splitLine[6]), float(splitLine[7])],
                                                    [float(splitLine[8]), float(splitLine[9]), float(splitLine[10])],
                                                    [float(splitLine[2]), float(splitLine[3]), float(splitLine[4])],
                                                    [float(splitLine[8]), float(splitLine[9]), float(splitLine[10])],
                                                    [float(splitLine[11]), float(splitLine[12]), float(splitLine[13])] ])
                            # if there is trailing charge density information, store it
                            if len(splitLine) >= 15:
                                # add twice, as a quadrilateral panel spits into two triangles in a triangular mesh
                                chargeDensity.extend([float(splitLine[14]), float(splitLine[14])])
                        else:
                            panelVertexes.extend( [[ (float(splitLine[2]), float(splitLine[3]), float(splitLine[4])),
                                                     (float(splitLine[5]), float(splitLine[6]), float(splitLine[7])),
                                                     (float(splitLine[8]), float(splitLine[9]), float(splitLine[10])),
                                                     (float(splitLine[11]), float(splitLine[12]), float(splitLine[13])) ]])              
                            # if there is trailing charge density information, store it
                            if len(splitLine) >= 15:
                                chargeDensity.append(float(splitLine[14]))
                    except ValueError:
                        FreeCAD.Console.PrintMessage("Error on line " + format(i) + " : " + line + "\n")  
                    # if there is trailing charge density information, store it
                    if len(splitLine) >= 15:
                        chargeDensity.append(float(splitLine[14]))

            fid.closed

    except OSError as err:
        FreeCAD.Console.PrintMessage("OS error: " + format(err) + "\n")
        return
                
    if use_mesh == True:
        # now create the mesh. As of FreeCAD 0.16 we cannot color the mesh faces individually,
        # so we'll ignore the charge information, even if present
        fastercapMesh = Mesh.Mesh(panelVertexes)
        # and show it
        Mesh.show(fastercapMesh)
        return fastercapMesh
    else:
        # check if there is charge information
        if len(chargeDensity) > 0:
            # check if every panel has the info
            if len(chargeDensity) != len(panelVertexes):
                FreeCAD.Console.PrintMessage("\nWarning: charge densities vector has length " + 
                                          format(len(chargeDensity)) + " while panels are " +
                                          format(len(panelVertexes)))
                chargeDensity = []
        # create faces
        facelist = []
        for panel in panelVertexes:
            # to create closed wires, the last point should be identical to the first
            wirepoly = Part.makePolygon(panel + [panel[0]])
            face = Part.Face(wirepoly)
            facelist.append(face)
        # cannot use a shell, otherwise face order will be all scrambled up,
        # as Part will stitch faces when building the shell, cutting the 
        # edges where there are other triangle vertexes in contact, and 
        # doing so changes the face order
        #shellObj = Part.makeShell(facelist)
        # a compound instead will just contain a list of faces
        compObj = Part.makeCompound(facelist)
        # might use "Part.show(compObj)" but we need access to the Part::Feature 'featObj'
        # to be able to change its ViewObject properties
        doc = App.ActiveDocument
        partFeatObj = doc.addObject("Part::Feature","FasterCap_Compound")
        partFeatObj.Shape = compObj
        doc.recompute() 
        # add density color
        if len(chargeDensity) > 0:
            # create colormap
            gradTable = [ (0.0, 1.0, 1.0), (0.0, 0.0, 1.0),
                          (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0)]
            colorMap = colormap(gradTable)
            
            #
            # create gradient table (debug only). Should implement using Pivy to have a fixed table at the side
            #~ facelist = []
            #~ for i in range(0,256):
                #~ wirepoly = Part.makePolygon( [ (0.0, i*10.0, 0.0), (0.0, (i+1)*10.0, 0.0), (0.0, (i+1)*10.0, 50.0),
                                               #~ (0.0, i*10.0, 50.0), (0.0, i*10.0, 0.0) ] )
                #~ face = Part.Face(wirepoly)
                #~ facelist.append(face)
            #~ shellGradObj = Part.makeShell(facelist)
            #~ gradObj = doc.addObject("Part::Feature","Gradient_Table")
            #~ gradObj.Shape = shellGradObj
            #~ doc.recompute()
            #~ gradObj.ViewObject.DiffuseColor = [colorMap[x] for x in range(0,256)]
            # end debug
            #
            
            # convert the charge density values into color indexes
            coeff = (COLORMAP_LEN - 1) / (max(chargeDensity) - min(chargeDensity))
            partFeatObj.ViewObject.DiffuseColor = [colorMap[(int)((x-min(chargeDensity))*coeff)] for x in chargeDensity]
        return partFeatObj
        
def colormap(gradientTable, maplen = COLORMAP_LEN):
    '''create a color map based on the given gradient table.
    
  'gradientTable' is a list of colors, represented as 3-tuples
  'maplen' is the length of the map that will be generated.
           The map will consist of 4-tuples, where the 4th
           element (alpha, transparency) is always zero.
    
  Example:
  gradientTable = [ (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
  myMap = colormap(gradientTable)
'''
    colorMap = []
    step = maplen / (float)(len(gradientTable) - 1)
    for i in range(0, maplen):
        gradientIndex = (int) (i/step)
        base = (int) (gradientIndex * step)
        # init color
        color = [0.0, 0.0, 0.0, 0.0]
        for j in range(0,3):
            colorstep = (gradientTable[gradientIndex+1][j] - gradientTable[gradientIndex][j]) / step
            color[j] = gradientTable[gradientIndex][j] + (i-base)*colorstep
            if(color[j] > 1.0):
                color[j] = 1.0
            elif(color[j] < 0.0):
                color[j] = 0.0
        colorMap.append((color[0], color[1], color[2], 0.0))
    return colorMap
    
    