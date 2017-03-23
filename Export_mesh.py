#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2014                                                    *
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

import FreeCAD, Mesh, Part, MeshPart, DraftGeomUtils, os
from FreeCAD import Vector

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtGui
else:
    def translate(ctxt,txt):
        return txt

__title__="FreeCAD E.M. Mesh Macros"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

DEF_FOLDER = "."


def export_mesh(filename, meshobj=None, isDiel=False, showNormals=False, folder=DEF_FOLDER):
    '''export mesh in FasterCap format as conductor or dielectric interface

    'filename' is the name of the export file
    'meshobj' must be a Mesh::Feature object
    'isDiel' specifies if the mesh is a dielectric, so the function will add
        a reference point to each panel to indicate which is the external side (outside)
    'showNormals' will add a compound object composed by a set of arrows showing the
        normal direction for each panel
    'folder' is the folder in which 'filename' will be saved

    Example:
    mymeshGui = Gui.ActiveDocument.Mesh
    mymeshObj = mymeshGui.Object
    export_mesh("mymesh.txt", meshobj=mymeshObj, folder="C:/temp")
'''

    # if no valid mesh was passed
    if meshobj == None:
        return
    elif meshobj.TypeId != "Mesh::Feature":
        FreeCAD.Console.PrintMessage("Error: 'meshobj' is not an object of type 'Mesh::Feature'")
        return

    if not os.path.isdir(folder):
        os.mkdir(folder)

    with open(folder + os.sep + filename, 'w') as fid:
        # write the preamble
        if isDiel == True:
            fid.write("0 dielectric definition file for mesh '" + meshobj.Label)
        else:
            fid.write("0 conductor definition file for mesh '" + meshobj.Label)
        fid.write("' created using FreeCAD's ElectroMagnetic workbench\n")
        fid.write("* see http://www.freecad.org and http://www.fastfieldsolvers.com\n")
        # export facets
        arrows = []
        condName = meshobj.Label.replace(" ","_")
        for facet in meshobj.Mesh.Facets:
            if len(facet.Points) == 3:
                fid.write("T " + condName)
            elif len(facet.Points) == 4:
                fid.write("Q " + condName)
            else:
                FreeCAD.Console.PrintMessage("Unforseen number of mesh facet points: " + len(facet.Points) + ", skipping facet")
                continue
            center = Vector(0.0, 0.0, 0.0)
            avgSideLen = 0.0
            for j, point in enumerate(facet.Points):
                fid.write(" ")
                for i in range(3):
                    fid.write(" " + str(point[i]))
                if isDiel == True or showNormals == True:
                    # 'point' is a tuple, transform in vector
                    center = center + Vector(point)
                    # get side length
                    side = Vector(facet.Points[(j+1)%3]) - Vector(point)
                    avgSideLen += side.Length
            if isDiel == True or showNormals == True:
                # calculate the reference point
                # (there should be a better way to divide a vector by a scalar..)
                center.multiply(1.0 / len(facet.Points) )
                # and now move along the normal, proportional to the average facet dimension
                scaledNormal = Vector(facet.Normal)
                scaledNormal.multiply(avgSideLen / len(facet.Points) )
                refpoint = center + scaledNormal
                if isDiel == True:
                    fid.write(" ")
                    for i in range(3):
                        fid.write(" " + str(refpoint[i]))
            fid.write("\n")
            if showNormals == True:
                arrows.append(make_arrow(center, refpoint))

        if showNormals == True:
            # add the vector normals visualization to the view
            # Note: could also use Part.show(normals) but in this case we could
            # not give the (permanent) name to the object, only change the label afterwards
            normals = Part.makeCompound(arrows)
            normalobj = FreeCAD.ActiveDocument.addObject("Part::Feature","Normals")
            normalobj.Shape = normals

    fid.closed

def make_arrow(startpoint, endpoint):
    '''create an arrow

    'startpoint' is a Vector specifying the start position
    'endpoint' is a Vector specifying the end position
'''

    line = Part.makeLine(startpoint, endpoint)
    # calculate arrow head base
    dir = endpoint - startpoint
    len = dir.Length
    base = dir
    base.normalize()
    base.multiply(len * 0.8)
    base = startpoint + base
    # radius2 is calculated for a fixed arrow head angle tan(15deg)=0.27
    cone = Part.makeCone(0.2 * len * 0.27, 0.0, 0.2 * len, base, dir, 360)

    # add the compound representing the arrow
    arrow = Part.makeCompound([line, cone])

    return arrow

def export_faces(filename, isDiel=False, name="", showNormals=False, folder=DEF_FOLDER):
    '''export faces in FasterCap format as conductor or dielectric interface

    The function operates on the selection. The selection can be a face, a compound or a solid.
    'filename' is the name of the export file
    'isDiel' specifies if the mesh is a dielectric, so the function will add
        a reference point to each panel to indicate which is the external side (outside)
    'name' is the name of the conductor created in the file. If not specified, defaults
        to the label of the first element in the selection set
    'showNormals' will add a compound object composed by a set of arrows showing the
        normal direction for each panel
    'folder' is the folder in which 'filename' will be saved

    Example:
    export_faces("mymesh.txt", folder="C:/temp")
'''
    # get selection
    sel = FreeCADGui.Selection.getSelection()
    # if no valid mesh was passed
    if sel == None:
        return

    if name == "":
        condName = sel[0].Label.replace(" ","_")
    else:
        condName = name

    # scan objects in selection and extract all faces
    faces = []
    facets = []
    for obj in sel:
        if obj.TypeId == "Mesh::Feature":
            facets.extend(obj.Mesh.Facets)
        else:
            if obj.Shape.ShapeType == "Face":
                faces.append(obj.Shape)
            elif obj.Shape.ShapeType == "Compound" or obj.Shape.ShapeType == "Solid":
                faces.extend(obj.Shape.Faces)
    # scan faces and find out which faces have more than 4 vertexes
    # TBD warning: should mesh also curve faces
    facesComplex = [x for x in faces if len(x.Vertexes) >= 5]
    facesSimple = [x for x in faces if len(x.Vertexes) < 5]
    # mesh complex faces
    doc = FreeCAD.ActiveDocument
    for face in facesComplex:
        mesh = doc.addObject("Mesh::Feature","Mesh")
        mesh.Mesh = MeshPart.meshFromShape(Shape=face, Fineness=0, SecondOrder=0, Optimize=1, AllowQuad=0)
        facets.extend(mesh.Mesh.Facets)
    # now we have faces and facets. Uniform all
    panels = []
    for face in facesSimple:
        sortEdges = DraftGeomUtils.sortEdges(face.Edges)
        # Point of a Vertex is a Vector, as well as Face.normalAt()
        points = [x.Vertexes[0].Point for x in sortEdges]
        panels.append( [points, face.normalAt(0,0)] )
    for facet in facets:
        points = [ Vector(x) for x in facet.Points]
        panels.append( [points, Vector(facet.Normal)] )

    if not os.path.isdir(folder):
        os.mkdir(folder)

    with open(folder + os.sep + filename, 'w') as fid:
        # write the preamble
        if isDiel == True:
            fid.write("0 dielectric definition file for the following objects\n")
        else:
            fid.write("0 conductor definition file for the following objects\n")
        for obj in sel:
            fid.write("* - " + obj.Label + "\n")
        fid.write("* created using FreeCAD's ElectroMagnetic workbench\n")
        fid.write("* see http://www.freecad.org and http://www.fastfieldsolvers.com\n")

        arrows = []
        # export faces
        for panel in panels:
            pointsNum = len(panel[0])
            if pointsNum == 3:
                fid.write("T " + condName)
            elif pointsNum == 4:
                fid.write("Q " + condName)
            else:
                FreeCAD.Console.PrintMessage("Unforseen number of panel vertexes: " + pointsNum + ", skipping panel")
                continue
            center = Vector(0.0, 0.0, 0.0)
            avgSideLen = 0.0
            for j, vertex in enumerate(panel[0]):
                fid.write(" ")
                for i in range(3):
                    fid.write(" " + str(vertex[i]))
                if isDiel == True or showNormals == True:
                    # 'point' is a tuple, transform in vector
                    center = center + vertex
                    # get side length
                    side = panel[0][(j+1)%3] - vertex
                    avgSideLen += side.Length
            if isDiel == True or showNormals == True:
                # calculate the reference point
                # (there should be a better way to divide a vector by a scalar..)
                center.multiply(1.0 / pointsNum )
                # and now move along the normal, proportional to the average facet dimension
                scaledNormal = panel[1]
                scaledNormal.multiply(avgSideLen / pointsNum )
                refpoint = center + scaledNormal
                if isDiel == True:
                    fid.write(" ")
                    for i in range(3):
                        fid.write(" " + str(refpoint[i]))
            fid.write("\n")
            if showNormals == True:
                arrows.append(make_arrow(center, refpoint))

    fid.closed

    if showNormals == True:
        # add the vector normals visualization to the view
        # Note: could also use Part.show(normals) but in this case we could
        # not give the (permanent) name to the object, only change the label afterwards
        normals = Part.makeCompound(arrows)
        normalobj = FreeCAD.ActiveDocument.addObject("Part::Feature","Normals")
        normalobj.Shape = normals
