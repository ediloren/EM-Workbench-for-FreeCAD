#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2018                                                    *
#*   Efficient Power Conversion Corporation, Inc.  http://epc-co.com       *
#*                                                                         *
#*   Developed by FastFieldSolvers S.R.L. under contract by EPC            *
#*   http://www.fastfieldsolvers.com                                       *
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
import numpy as np
    
if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtGui
else:
    def translate(ctxt,txt):
        return txt

__title__="FreeCAD E.M. FastHenry2 Macros"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

DEF_FOLDER = "."


def export_segs(filename="", disc=3, custDot="", FHbug=False, w=0, h=0, nhinc=0, nwinc=0, folder=DEF_FOLDER):
    '''Export segments in FastHenry format
    
    The function operates on the selection. The selection must be a sketch, a wire or an edge.
    'filename' is the name of the export file
    'disc' is the maximum number of segments into which curves will be discretized
    'custDot' is a custom directive added in the output file (a string added as it is on top of the file)
    'FHbug' works around a FastHenry bug happening for some very exact values of diagonal parallel segments,
        giving rise to 'uh oh segments don't seem parallel' kind of errors
    'w', 'h', 'nhinc', 'nwinc' are the FastHenry parameters;
        if zero, they are ignored (FastHenry will use the .default values).
        If 'w' is not zero, no segment shorter than abs(w)*3 will be output. Note that the end point of
            the previous segment will be the starting point of the *next* segment (skipping the short one).
            This might cause misalignments if there are many consecutive short segments.
        If 'w' is negative, it assures that no curve will be discretized if the radius is less than w*3,
            to avoid short thick (overlapping) segments.
    'folder' is the folder in which 'filename' will be saved
    
    Example:
    export_segs("mysegs.inp", folder="C:/temp")
'''
    # get selection
    sel = FreeCADGui.Selection.getSelection()
    # if no valid selection was passed
    if sel == None:
        return
        
    if filename == "":
        filename = sel[0].Label.replace(" ","_") + ".txt"

    if not os.path.isdir(folder):
        os.mkdir(folder)
   
    with open(folder + os.sep + filename, 'w') as fid:

        fid.write("* Conductor definition file for the following objects\n")
        for obj in sel:
            fid.write("* - " + obj.Label + "\n")
        fid.write("* created using FreeCAD's ElectroMagnetic Workbench\n")
        fid.write("* see http://www.freecad.org and http://www.fastfieldsolvers.com\n")
        fid.write("\n")
        
        # scan objects in selection and export to FastHenry one by one
        
        for obj in sel:
            
            edges_raw = []
            # checking TypeId; cannot check type(obj), too generic
            if obj.TypeId == "Sketcher::SketchObject":
                if obj.Shape.ShapeType == "Wire":
                    edges_raw.extend(obj.Shape.Edges)
            # compound
            elif obj.TypeId == "Part::Compound":
                edges_raw.extend(obj.Shape.Edges)
            # line or DWire (Draft Wire)
            elif obj.TypeId == "Part::Part2DObjectPython":
                if obj.Shape.ShapeType == "Wire":
                    edges_raw.extend(obj.Shape.Edges)
            # wire created by upgrading a set of (connected) edges
            elif obj.TypeId == "Part::Feature":
                if obj.Shape.ShapeType == "Wire":
                    edges_raw.extend(obj.Shape.Edges)
            # any other part, provided it has a 'Shape' attribute
            else:
                if hasattr(obj, "Shape"):
                    if obj.Shape.ShapeType == "Wire":
                        edges_raw.extend(obj.Shape.Edges)
                else:
                    # to be implemented?
                    FreeCAD.Console.PrintMessage("Unsupported object type for '" + obj.Label + "', skipping\n")
                    continue
                
            # sort the edges. If the selected path is disconnected, the path will be broken!
            edges = Part.__sortEdges__(edges_raw)
            # TBC: join parts with additional edges, or .equiv-ing them, using distToShape between the obj.Shape
            #      Can happen with a compound containing different edges / wires / stetches
            #edge = Part.Edge(Part.Line(Vector(154.0002, -62.6872,0), Vector(154.0002,-53.1876,0)))
            #v = Part.Vertex(edges[0].Curve.StartPoint)
            #v.Tolerance
            #App.ActiveDocument.Shape.Shape.Vertexes[1].distToShape(App.ActiveDocument.Shape001.Shape.Vertexes[0])
            
            # scan edges and derive nodes
            nodes = []
            for edge in edges:
                if type(edge.Curve) == Part.Circle:
                    # discretize
                    if edge.Curve.Radius < -w*3 and w < 0:
                        ddisc = 1
                    else:
                        ddisc = disc
                    for i in range(0, ddisc):
                        step = (edge.LastParameter - edge.FirstParameter) / ddisc
                        # always skip last vertex, as the next edge will start where this finishes
                        nodes.append(edge.valueAt(edge.FirstParameter + i*step))
                        # quick & dirty trick
                        lastvertex = edge.valueAt(edge.LastParameter)
                elif type(edge.Curve) == Part.Ellipse:
                    # discretize
                    if (edge.Curve.MajorRadius < -w*3 or edge.Curve.MinorRadius < -w*3) and w < 0:
                        ddisc = 1
                    else:
                        ddisc = disc
                    for i in range(0, ddisc):
                        step = (edge.LastParameter - edge.FirstParameter) / ddisc
                        # always skip last vertex, as the next edge will start where this finishes
                        nodes.append(edge.valueAt(edge.FirstParameter + i*step))
                        # quick & dirty trick
                        lastvertex = edge.valueAt(edge.LastParameter)
                elif type(edge.Curve) == Part.Line:
                    # if w=0, the following condition is always true
                    if edge.Length > abs(w)*3:
                        nodes.append(edge.valueAt(edge.FirstParameter))
                    # quick & dirty trick
                    lastvertex = edge.valueAt(edge.LastParameter)
                else:
                    FreeCAD.Console.PrintMessage("Unknown edge: " + str(type(edge.Curve)) + " in '" + obj.Label + "',, skipping\n")
            # now add the very last vertex
            nodes.append(lastvertex)
            
            if len(nodes) < 2:
                FreeCAD.Console.PrintMessage("Less than two nodes found in '" + obj.Label + "', skipping\n")
                continue
            
            # start actual object output in FastHenry format
            fid.write("* " + obj.Label + "\n")
            if custDot != "":
                fid.write(custDot + "\n")
            baseName = obj.Label.replace(" ","_") + "_"
            # now create nodes
            for i, node in enumerate(nodes):
                # extension in the node name must be "S" for the Start node
                # and "E" for the End node
                if i == 0:
                    ext = "S"
                elif i == len(nodes)-1:
                    ext = "E"
                else:
                    ext = str(i)
                
                if FHbug == True:
                    fid.write("N" + baseName + ext + " x=" + str(node.x) + " y=" + str(int(node.y)) + " z=" + str(node.z) + "\n")
                else:
                    fid.write("N" + baseName + ext + " x=" + str(node.x) + " y=" + str(node.y) + " z=" + str(node.z) + "\n")
            
            # and finally segments
            for i in range(0, len(nodes)-1):
                # extension in the node name must be "S" for the Start node
                # and "E" for the End node
                #
                # start node
                if i == 0:
                    ext1 = "S"
                else:
                    ext1 = str(i)
                # end node
                if i >= len(nodes)-2:
                    ext2 = "E"
                else:
                    ext2 = str(i+1)
               
                fid.write("E" + baseName + "N" + ext1 + "N" + ext2 + " ")
                fid.write("N" + baseName + ext1 + " " + "N" + baseName + ext2)
                if w > 0:
                    fid.write(" w=" + str(w))
                if h > 0:
                    fid.write(" h=" + str(w))
                if nhinc > 0:
                    fid.write(" nhinc=" + str(w))
                if nwinc > 0:
                    fid.write(" nwinc=" + str(w))
                fid.write("\n")
            # blank lines before next object
            fid.write("\n\n")
        
    fid.closed
    
def export_segs2(filename="", disc=3, custDot="", FHbug=False, breakSeg=False, w=0, h=0, nhinc=0, nwinc=0, folder=DEF_FOLDER):
    '''Export segments in FastHenry format
    
    The function operates on the selection. The selection must be a sketch, a wire or an edge.
    Version 2 means it discretizes both curved and straight parts of a path. It also dumps nodes of an underlying GND plane.
    'filename' is the name of the export file
    'disc' is the maximum number of segments into which curves will be discretized
    'custDot' is a custom directive added in the output file (a string added as it is on top of the file)
    'FHbug' works around a FastHenry bug happening for some very exact values of diagonal parallel segments,
        giving rise to 'uh oh segments don't seem parallel' kind of errors
    'breakSeg' if true breaks also straight segments into 'disc' parts
    'w', 'h', 'nhinc', 'nwinc' are the FastHenry parameters;
        if zero, they are ignored (FastHenry will use the .default values).
        If 'w' is not zero, no segment shorter than abs(w)*3 will be output. Note that the end point of
            the previous segment will be the starting point of the *next* segment (skipping the short one).
            This might cause misalignments if there are many consecutive short segments.
        If 'w' is negative, it assures that no curve will be discretized if the radius is less than w*3,
            to avoid short thick (overlapping) segments.
    'folder' is the folder in which 'filename' will be saved
    
    Example:
    export_segs2("mysegs.inp", folder="C:/temp")
'''
    # get selection
    sel = FreeCADGui.Selection.getSelection()
    # if no valid selection was passed
    if sel == None:
        return
        
    if filename == "":
        filename = sel[0].Label.replace(" ","_") + ".txt"

    if not os.path.isdir(folder):
        os.mkdir(folder)
   
    with open(folder + os.sep + filename, 'w') as fid:

        fid.write("* Conductor definition file for the following objects\n")
        for obj in sel:
            fid.write("* - " + obj.Label + "\n")
        fid.write("* created using FreeCAD's ElectroMagnetic Workbench\n")
        fid.write("* see http://www.freecad.org and http://www.fastfieldsolvers.com\n")
        fid.write("\n")
        

        # scan objects in selection and export to FastHenry one by one
        gndplane_nodes = []        
        for obj in sel:
            
            edges_raw = []
            # checking TypeId; cannot check type(obj), too generic
            if obj.TypeId == "Sketcher::SketchObject":
                if obj.Shape.ShapeType == "Wire":
                    edges_raw.extend(obj.Shape.Edges)
            # compound
            elif obj.TypeId == "Part::Compound":
                edges_raw.extend(obj.Shape.Edges)
            # line or DWire (Draft Wire)
            elif obj.TypeId == "Part::Part2DObjectPython":
                if obj.Shape.ShapeType == "Wire":
                    edges_raw.extend(obj.Shape.Edges)
            # wire created by upgrading a set of (connected) edges
            elif obj.TypeId == "Part::Feature":
                if obj.Shape.ShapeType == "Wire":
                    edges_raw.extend(obj.Shape.Edges)
            # any other part, provided it has a 'Shape' attribute
            else:
                if hasattr(obj, "Shape"):
                    if obj.Shape.ShapeType == "Wire":
                        edges_raw.extend(obj.Shape.Edges)
                else:
                    # to be implemented?
                    FreeCAD.Console.PrintMessage("Unsupported object type for '" + obj.Label + "', skipping\n")
                    continue
                
            # sort the edges. If the selected path is disconnected, the path will be broken!
            edges = Part.__sortEdges__(edges_raw)           
            # scan edges and derive nodes
            nodes = []
            for edge in edges:
                if type(edge.Curve) == Part.Circle:
                    # discretize
                    if edge.Curve.Radius < -w*3 and w < 0:
                        ddisc = 1
                    else:
                        ddisc = disc
                    for i in range(0, ddisc):
                        step = (edge.LastParameter - edge.FirstParameter) / ddisc
                        # always skip last vertex, as the next edge will start where this finishes
                        nodes.append(edge.valueAt(edge.FirstParameter + i*step))
                        # quick & dirty trick
                        lastvertex = edge.valueAt(edge.LastParameter)
                elif type(edge.Curve) == Part.Ellipse:
                    # discretize
                    if (edge.Curve.MajorRadius < -w*3 or edge.Curve.MinorRadius < -w*3) and w < 0:
                        ddisc = 1
                    else:
                        ddisc = disc
                    for i in range(0, ddisc):
                        step = (edge.LastParameter - edge.FirstParameter) / ddisc
                        # always skip last vertex, as the next edge will start where this finishes
                        nodes.append(edge.valueAt(edge.FirstParameter + i*step))
                        # quick & dirty trick
                        lastvertex = edge.valueAt(edge.LastParameter)
                elif type(edge.Curve) == Part.Line:
                    # if w=0, the following condition is always true
                    if edge.Length > abs(w)*3:
                        if breakSeg == False:
                            ddisc = 1
                        else:
                            ddisc = disc
                        for i in range(0, ddisc):
                            step = (edge.LastParameter - edge.FirstParameter) / ddisc
                            # always skip last vertex, as the next edge will start where this finishes
                            nodes.append(edge.valueAt(edge.FirstParameter + i*step))
                        # quick & dirty trick
                        lastvertex = edge.valueAt(edge.LastParameter)
                else:
                    FreeCAD.Console.PrintMessage("Unknown edge: " + str(type(edge.Curve)) + " in '" + obj.Label + "',, skipping\n")
            # now add the very last vertex
            nodes.append(lastvertex)
            
            if len(nodes) < 2:
                FreeCAD.Console.PrintMessage("Less than two nodes found in '" + obj.Label + "', skipping\n")
                continue
            
            # start actual object output in FastHenry format
            fid.write("* " + obj.Label + "\n")
            if custDot != "":
                fid.write(custDot + "\n")
            baseName = obj.Label.replace(" ","_") + "_"
            # now create nodes
            for i, node in enumerate(nodes):
                # extension in the node name must be "S" for the Start node
                # and "E" for the End node
                if i == 0:
                    ext = "S"
                elif i == len(nodes)-1:
                    ext = "E"
                else:
                    ext = str(i)
                
                if FHbug == True:
                    fid.write("N" + baseName + ext + " x=" + str(node.x) + " y=" + str(int(node.y)) + " z=" + str(node.z) + "\n")
                    gndplane_nodes.append( (baseName+ext, str(node.x), str(int(node.y)), str(node.z)) )
                else:
                    fid.write("N" + baseName + ext + " x=" + str(node.x) + " y=" + str(node.y) + " z=" + str(node.z) + "\n")
                    gndplane_nodes.append( (baseName+ext, str(node.x), str(int(node.y)), str(node.z)) )
            
            # and finally segments
            for i in range(0, len(nodes)-1):
                # extension in the node name must be "S" for the Start node
                # and "E" for the End node
                #
                # start node
                if i == 0:
                    ext1 = "S"
                else:
                    ext1 = str(i)
                # end node
                if i >= len(nodes)-2:
                    ext2 = "E"
                else:
                    ext2 = str(i+1)
               
                fid.write("E" + baseName + "N" + ext1 + "N" + ext2 + " ")
                fid.write("N" + baseName + ext1 + " " + "N" + baseName + ext2)
                if w > 0:
                    fid.write(" w=" + str(w))
                if h > 0:
                    fid.write(" h=" + str(w))
                if nhinc > 0:
                    fid.write(" nhinc=" + str(w))
                if nwinc > 0:
                    fid.write(" nwinc=" + str(w))
                fid.write("\n")

            # blank lines before next object
            fid.write("\n\n")

        # create GND plane nodes 
        for gndplane_node in gndplane_nodes:
            fid.write("+ Nplane" + gndplane_node[0] + " (" + gndplane_node[1] + "," +
                    gndplane_node[2] + "," + "-1.5" + ")\n" )

        # blank lines before next object
        fid.write("\n\n")

        # create .equiv plane nodes statements 
        for gndplane_node in gndplane_nodes:
            fid.write(".equiv Nplane" + gndplane_node[0] + " N" + gndplane_node[0] + "\n")

    fid.closed
    

def create_FH_plane(filename="", seg1=10, seg2=10, wx=10, wy=10, name="", custDot="", thick=1.0, folder=DEF_FOLDER):
    '''Create a conductive plane using primitive FastHenry segments
    
    'filename' is the name of the export file
    'seg1' is the number of segments along x
    'seg2' is the number of segments along y
    'wx', 'wy' are the plane dimensions along x and y
    'name' is the node extension name (e.g. Nname_1_2)
    'folder' is the folder in which 'filename' will be saved
    
    Example:
    create_FH_plane("plane.inp", seg1=5, seg2=3, folder="C:/temp")
'''
        
    if filename == "":
        filename = sel[0].Label.replace(" ","_") + ".txt"

    if not os.path.isdir(folder):
        os.mkdir(folder)
   
    with open(folder + os.sep + filename, 'w') as fid:

        fid.write("* Conductive plane built using primitive FastHenry segments\n")
        fid.write("* created using FreeCAD's ElectroMagnetic Workbench\n")
        fid.write("* see http://www.freecad.org and http://www.fastfieldsolvers.com\n")
        fid.write("\n")
        
        stepx = wx / seg1
        stepy = wy / seg2
        
        # lay down nodes
        
        for i in range(0, seg1+1):
            for j in range(0, seg2+1):
                fid.write("N" + name + "_" + str(i) + "_" + str(j) + " x=" + str(i*stepx) + " y=" + str(j*stepy) + " z=0 \n")
            
        # lay down segments 
        #
        # along y
        for i in range(0, seg1+1):
            for j in range(0, seg2):
                fid.write("E2"+ name + "_" + str(i) + "_" + str(j) + " N" + name + "_" + str(i) + "_" + str(j) + " N" + name + "_" + str(i) + "_" + str(j+1) + " w=" + str(stepx) + " h=" + str(thick) + " \n")
        # along x
        for j in range(0, seg2+1):
            for i in range(0, seg1):
                fid.write("E2"+ name + "_" + str(i) + "_" + str(j) + " N" + name + "_" + str(i) + "_" + str(j) + " N" + name + "_" + str(i+1) + "_" + str(j) + " w=" + str(stepy) + " h=" + str(thick) + " \n")
                       
        fid.write("\n")
        
    fid.closed
        
def meshSolidWithSegments(obj=None,delta=1.0,deltaX=0.0,deltaY=0.0,deltaZ=0.0,stayInside=False,generateSegs=True):
    ''' Mesh a solid object with a grid of segments
'''
    if obj == None:
        return
    if not hasattr(obj,"Shape"):
        return
    from FreeCAD import Vector
    import EM_FHNode
    import EM_FHSegment
    import numpy as np
    # if the user specified no deltaX
    if deltaX <= 0.0:
        deltaX = float(delta)
    # if the user specified no deltaY
    if deltaY <= 0.0:
        deltaY = float(delta)
    # if the user specified no deltaZ
    if deltaZ <= 0.0:
        deltaZ = float(delta)   
    bbox = obj.Shape.BoundBox
    stepsX = int(bbox.XLength/deltaX)
    deltaSideX = (bbox.XLength - deltaX * stepsX) / 2.0
    stepsY = int(bbox.YLength/deltaY)
    deltaSideY = (bbox.YLength - deltaY * stepsY) / 2.0
    stepsZ = int(bbox.ZLength/deltaZ)
    deltaSideZ = (bbox.ZLength - deltaZ * stepsZ) / 2.0
    # create the 3D array of nodes
    isNode=np.full((stepsX+1,stepsY+1,stepsZ+1), False, bool)
    # and now iterate to find which node is inside the object 'obj'
    pos_x = bbox.XMin + deltaSideX
    for step_x in range(0,stepsX+1):
        pos_y = bbox.YMin + deltaSideY
        for step_y in range(0,stepsY+1):
            pos_z = bbox.ZMin + deltaSideZ
            for step_z in range(0,stepsZ+1):
                # if the point is inside the object shape, or on the surface, flag it
                if obj.Shape.isInside(Vector(pos_x,pos_y,pos_z),0.0,True):
                    isNode[step_x,step_y,step_z] = True
                pos_z = pos_z + deltaZ
            pos_y = pos_y + deltaY
        pos_x = pos_x + deltaX
    # if we don't need to stay within the object shape boundaries,
    # the segment will overlap the shape contour (just like the uniform conductive planes)
    nodes=np.full((stepsX+1,stepsY+1,stepsZ+1), None, np.object)
    if stayInside == False:
        pos_x = bbox.XMin + deltaSideX
        for step_x in range(0,stepsX+1):
            pos_y = bbox.YMin + deltaSideY
            for step_y in range(0,stepsY+1):
                pos_z = bbox.ZMin + deltaSideZ
                for step_z in range(0,stepsZ+1):
                    # if the point is inside the object shape, or on the surface, flag it
                    if isNode[step_x,step_y,step_z] == True:
                        # create the node
                        node = EM_FHNode.makeFHNode(X=pos_x, Y=pos_y, Z=pos_z)
                        # store it in the array
                        nodes[step_x,step_y,step_z] = node
                    pos_z = pos_z + deltaZ
                pos_y = pos_y + deltaY
            pos_x = pos_x + deltaX  
    # if we must stay within the object shape boundaries (within the accuracy
    # of the point sampling)
    else:
        pos_x = bbox.XMin + deltaSideX
        for step_x in range(0,stepsX):
            pos_y = bbox.YMin + deltaSideY
            for step_y in range(0,stepsY):
                pos_z = bbox.ZMin + deltaSideZ
                for step_z in range(0,stepsZ):
                    # if all the eight cube corners are inside the object shape,
                    # we consider the center point well inside the object shape, i.e. also
                    # for a segment lying on a plane parallel to the plane xy,
                    # with width=deltaX, height=deltaY we are within the object
                    if (isNode[step_x,step_y,step_z] == True and isNode[step_x+1,step_y,step_z] == True and
                        isNode[step_x,step_y+1,step_z] == True and isNode[step_x+1,step_y+1,step_z] == True and
                        isNode[step_x,step_y,step_z+1] == True and isNode[step_x+1,step_y,step_z+1] == True and
                        isNode[step_x,step_y+1,step_z+1] == True and isNode[step_x+1,step_y+1,step_z+1] == True):
                            # create the node
                            node = EM_FHNode.makeFHNode(X=pos_x+deltaX/2.0, Y=pos_y+deltaY/2.0, Z=pos_z+deltaZ/2.0)
                            # store it in the array
                            nodes[step_x,step_y,step_z] = node
                    pos_z = pos_z + deltaZ
                pos_y = pos_y + deltaY
            pos_x = pos_x + deltaX  
    # now create the grid of segments
    # first along x
    for step_z in range(0,stepsZ+1):
        for step_y in range(0,stepsY+1):
            for step_x in range(0,stepsX):
                # if the node and the next are inside the object shape, create the segment
                if nodes[step_x,step_y,step_z] != None and nodes[step_x+1,step_y,step_z] != None:
                    segment = EM_FHSegment.makeFHSegment(nodeStart=nodes[step_x,step_y,step_z],nodeEnd=nodes[step_x+1,step_y,step_z],width=deltaX,height=deltaZ)
    # then along y
    for step_z in range(0,stepsZ+1):
        for step_x in range(0,stepsX+1):
            for step_y in range(0,stepsY):
                # if the node and the next are inside the object shape, create the segment
                if nodes[step_x,step_y,step_z] != None and nodes[step_x,step_y+1,step_z] != None:
                    segment = EM_FHSegment.makeFHSegment(nodeStart=nodes[step_x,step_y,step_z],nodeEnd=nodes[step_x,step_y+1,step_z],width=deltaY,height=deltaZ)
    # finally along z
    for step_x in range(0,stepsX+1):
        for step_y in range(0,stepsY+1):
            for step_z in range(0,stepsZ):
                # if the node and the next are inside the object shape, create the segment
                if nodes[step_x,step_y,step_z] != None and nodes[step_x,step_y,step_z+1] != None:
                    segment = EM_FHSegment.makeFHSegment(nodeStart=nodes[step_x,step_y,step_z],nodeEnd=nodes[step_x,step_y,step_z+1],width=deltaX,height=deltaY)

def meshSolidWithVoxels(obj=None,delta=1.0):
    ''' Voxelize a solid object
'''
    if obj == None:
        return
    if not hasattr(obj,"Shape"):
        return
    from FreeCAD import Vector
    import numpy as np
    bbox = obj.Shape.BoundBox
    stepsX = int(bbox.XLength/delta)
    deltaSideX = (bbox.XLength - delta * stepsX) / 2.0
    stepsY = int(bbox.YLength/delta)
    deltaSideY = (bbox.YLength - delta * stepsY) / 2.0
    stepsZ = int(bbox.ZLength/delta)
    deltaSideZ = (bbox.ZLength - delta * stepsZ) / 2.0
    print("X="+str(stepsX)+" Y="+str(stepsY)+" Z="+str(stepsZ)+" tot="+str(stepsX*stepsY*stepsZ))
    # create the 3D array of nodes
    isNode=np.full((stepsX+1,stepsY+1,stepsZ+1), False, bool)
    # and now iterate to find which point is inside the object 'obj'
    pos_x = bbox.XMin + deltaSideX
    for step_x in range(0,stepsX+1):
        pos_y = bbox.YMin + deltaSideY
        for step_y in range(0,stepsY+1):
            pos_z = bbox.ZMin + deltaSideZ
            for step_z in range(0,stepsZ+1):
                # if the point is inside the object shape, or on the surface, flag it
                if obj.Shape.isInside(Vector(pos_x,pos_y,pos_z),0.0,True):
                    isNode[step_x,step_y,step_z] = True
                pos_z = pos_z + delta
            pos_y = pos_y + delta
        pos_x = pos_x + delta
    return isNode

def getContainingBBox(objs):
    ''' Get the bounding box containing all the listed objects
    
        'objs' is the list of FreeCAD objects
        
        Returns the global bounding box.
        If the list is None, or is not a list, or if the object have no Shape,
        the returned BoundBox is None
'''
    # create an empty bbox
    gbbox = None
    isfirst = True
    # if 'objs' is not None
    if objs:
        if isinstance(objs,list):
            for obj in objs:
                if hasattr(obj,"Shape"):
                    if isfirst:
                        gbbox = obj.Shape.BoundBox
                        isfirst = False
                    else:
                        gbbox.add(obj.Shape.BoundBox)
    return gbbox

def createVoxelSpace(bbox,delta):
    ''' Creates the voxel tensor (3D array) in the given bounding box
    
        'bbox' is the overall FreeCAD.BoundBox bounding box
        'delta' is the voxels size length
        
        Returns a voxel tensor as a Numpy 3D array.
        If gbbox is None, returns None
'''
    if bbox == None:
        return None
    if delta == None:
        return None
    # add 1.0 to always cover the bbox space with the voxels
    stepsX = int(bbox.XLength/delta + 1.0)
    stepsY = int(bbox.YLength/delta + 1.0)
    stepsZ = int(bbox.ZLength/delta + 1.0)
    # debug
    print("X="+str(stepsX)+" Y="+str(stepsY)+" Z="+str(stepsZ)+" tot="+str(stepsX*stepsY*stepsZ))
    # create the 3D array of nodes as 16-bit integers (max 65k different conductivities)
    voxelSpace=np.full((stepsX+1,stepsY+1,stepsZ+1), 0, np.int16)
    return voxelSpace

def voxelizeConductor(obj,condIndex,gbbox,delta,voxelSpace):
    ''' Voxelize a solid object. The function will modify the 'voxelSpace'
        by marking with 'condIndex' all the voxels that sample the object 
        'obj' internal.

        'obj' is the object to voxelize
        'condIndex' (integer) is the index of the object. It defines the object conductivity.
        'gbbox' (FreeCAD.BoundBox) is the overall bounding box
        'delta' is the voxels size length
        'voxelSpace' (Numpy 3D array) is the voxel tensor of the overall space 
'''
    if obj == None:
        return
    if not hasattr(obj,"Shape"):
        return
    # get this object bbox
    bbox = obj.Shape.BoundBox
    # now must find the voxel set that contains the object bounding box
    # find the voxel that contains the bbox min point
    min_x = int((bbox.XMin - gbbox.XMin)/delta)
    min_y = int((bbox.YMin - gbbox.YMin)/delta)
    min_z = int((bbox.ZMin - gbbox.ZMin)/delta)
    # find the voxel that contains the bbox max point
    max_x = int((bbox.XMax - gbbox.XMin)/delta)
    max_y = int((bbox.YMax - gbbox.YMin)/delta)
    max_z = int((bbox.ZMax - gbbox.ZMin)/delta)
    # and now iterate to find which voxel is inside the object 'obj',
    # sampling based on the voxel centers
    pos_x = gbbox.XMin + min_x * delta + delta/2.0
    for step_x in range(min_x,max_x+1):
        pos_y = gbbox.YMin + min_y * delta + delta/2.0
        for step_y in range(min_y,max_y+1):
            pos_z = gbbox.ZMin + min_z * delta + delta/2.0
            for step_z in range(min_z,max_z+1):
                # if the point is inside the object shape, or on the surface, flag it
                if obj.Shape.isInside(Vector(pos_x,pos_y,pos_z),0.0,True):
                    # debug
                    #print("pos_x="+str(pos_x)+" pos_y="+str(pos_y)+" pos_z="+str(pos_z))
                    voxelSpace[step_x,step_y,step_z] = condIndex
                pos_z = pos_z + delta
            pos_y = pos_y + delta
        pos_x = pos_x + delta

def createVoxelShell(obj,condIndex,gbbox,delta,voxelSpace=None):
    ''' Creates a shell composed by the external faces of a voxelized object.
    
        'obj' is the object whose shell must be created
        'condIndex' (integer) is the index of the object. It defines the object conductivity.
        'gbbox' (FreeCAD.BoundBox) is the overall bounding box
        'delta' is the voxels size length
        'voxelSpace' (Numpy 3D array) is the voxel tensor of the overall space 
'''
    if voxelSpace == None:
        return
    if not hasattr(obj,"Shape"):
        return
    surfList = []
    # get the object's bbox
    bbox = obj.Shape.BoundBox
    # now must find the voxel set that contains the object bounding box
    # find the voxel that contains the bbox min point
    min_x = int((bbox.XMin - gbbox.XMin)/delta)
    min_y = int((bbox.YMin - gbbox.YMin)/delta)
    min_z = int((bbox.ZMin - gbbox.ZMin)/delta)
    # find the voxel that contains the bbox max point
    max_x = int((bbox.XMax - gbbox.XMin)/delta)
    max_y = int((bbox.YMax - gbbox.YMin)/delta)
    max_z = int((bbox.ZMax - gbbox.ZMin)/delta)
    # this is half the side of the voxel
    halfdelta = delta/2.0
    # array to find the six neighbour
    sides = [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]
    # vertexes of the six faces
    vertexes = [[Vector(delta,0,0), Vector(delta,delta,0), Vector(delta,delta,delta), Vector(delta,0,delta)],
                [Vector(0,0,0), Vector(0,0,delta), Vector(0,delta,delta), Vector(0,delta,0)],
                [Vector(0,delta,0), Vector(0,delta,delta), Vector(delta,delta,delta), Vector(delta,delta,0)],
                [Vector(0,0,0), Vector(delta,0,0), Vector(delta,0,delta), Vector(0,0,delta)],
                [Vector(0,0,delta), Vector(delta,0,delta), Vector(delta,delta,delta), Vector(0,delta,delta)],
                [Vector(0,0,0), Vector(0,delta,0), Vector(delta,delta,0), Vector(delta,0,0)]]
    # and now iterate to find which voxel is inside the object 'obj',
    # sampling based on the voxel centers
    vbase = Vector(gbbox.XMin + min_x * delta, gbbox.YMin + min_y * delta, gbbox.ZMin + min_z * delta)
    for step_x in range(min_x,max_x+1):
        vbase.y = gbbox.YMin + min_y * delta
        for step_y in range(min_y,max_y+1):
            vbase.z = gbbox.ZMin + min_z * delta
            for step_z in range(min_z,max_z+1):
                # check if voxel is belonging to the given object
                if voxelSpace[step_x,step_y,step_z] == condIndex:
                    # scan the six neighbour voxels, to see if they are belonging to the same conductor or not.
                    # If they are not belonging to the same conductor, or if the voxel space is finished, the current voxel
                    # side in the direction of the empty voxel is an external surface
                    for side, vertex in zip(sides,vertexes):
                        is_surface = False
                        nextVoxelIndexes = [step_x+side[0],step_y+side[1],step_z+side[2]]
                        if (nextVoxelIndexes[0] > max_x or nextVoxelIndexes[0] < 0 or
                           nextVoxelIndexes[1] > max_y or nextVoxelIndexes[1] < 0 or
                           nextVoxelIndexes[2] > max_z or nextVoxelIndexes[2] < 0):
                            is_surface = True
                        else:
                            if voxelSpace[nextVoxelIndexes[0],nextVoxelIndexes[1],nextVoxelIndexes[2]] != condIndex:
                                is_surface = True
                        if is_surface == True:
                            # debug
                            #print("pos_x="+str(vbase.x)+" pos_y="+str(vbase.y)+" pos_z="+str(vbase.z))
                            # create the face
                            # calculate the vertexes
                            v11 = vbase + vertex[0]
                            v12 = vbase + vertex[1]
                            v13 = vbase + vertex[2]
                            v14 = vbase + vertex[3]
                            # now make the face
                            poly = Part.makePolygon( [v11,v12,v13,v14,v11])
                            face = Part.Face(poly)
                            surfList.append(face)
                vbase.z += delta
            vbase.y += delta
        vbase.x += delta
    # create a shell. Does not need to be solid.
    objShell = Part.makeShell(surfList)
    return objShell   

def findContactVoxelSurfaces(face,condIndex,gbbox,delta,voxelSpace=None,createShell=False):
    ''' Find the voxel surface sides corresponding to the given contact surface
        (face) of an object. The object must have already been voxelized.
        
        'face' is the object face
        'condIndex' (integer) is the index of the object to which the face belongs.
                It defines the object conductivity.
        'gbbox' (FreeCAD.BoundBox) is the overall bounding box
        'delta' is the voxels size length
        'voxelSpace' (Numpy 3D array) is the voxel tensor of the overall space
        'createShell' (bool) creates a shell out of the contact faces
        
        Returns a list of surfaces in the format [x,y,z,voxside] where
        x, y, z are the voxel position indexes, while voxside is '+x', '-x',
        '+y', '-y', '+z', '-z' according the the impacted surface of the voxel
'''
    if voxelSpace == None:
        return
    surfList = []
    contactList = []
    # get the face's bbox
    bbox = face.BoundBox
    # now must find the voxel set that contains the face bounding box
    # with a certain slack - it could be the next voxel,
    # if the surface is at the boundary between voxels.
    # Find the voxel that contains the bbox min point
    min_x = int((bbox.XMin - gbbox.XMin)/delta)-1
    min_y = int((bbox.YMin - gbbox.YMin)/delta)-1
    min_z = int((bbox.ZMin - gbbox.ZMin)/delta)-1
    # find the voxel that contains the bbox max point
    max_x = int((bbox.XMax - gbbox.XMin)/delta)+1
    max_y = int((bbox.YMax - gbbox.YMin)/delta)+1
    max_z = int((bbox.ZMax - gbbox.ZMin)/delta)+1
    # debug
    #print(str(min_x)+" "+str(min_y)+" "+str(min_z)+" "+str(max_x)+" "+str(max_y)+" "+str(max_z))
    # create a Part.Vertex that we can use to test the distance
    # to the face (as it is a TopoShape)
    vec = FreeCAD.Vector(0,0,0)
    testVertex = Part.Vertex(vec)
    # this is half the side of the voxel
    halfdelta = delta/2.0
    # small displacement w.r.t. delta
    epsdelta = delta/100.0
    # array to find the six neighbour 
    sides = [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]
    # string describing the side
    sideStrs = ['+x', '-x', '+y', '-y', '+z', '-z']
    # centers of the sides, with respect to the lower corner (with the smallest coordinates)
    sideCenters = [Vector(delta,halfdelta,halfdelta), Vector(0.0,halfdelta,halfdelta),
                    Vector(halfdelta,delta,halfdelta), Vector(halfdelta,0.0,halfdelta),
                    Vector(halfdelta,halfdelta,delta), Vector(halfdelta,halfdelta,0.0)]
    # vertexes of the six faces (with a slight offset)
    vertexes = [[Vector(delta+epsdelta,0,0), Vector(delta+epsdelta,delta,0), Vector(delta+epsdelta,delta,delta), Vector(delta+epsdelta,0,delta)],
                [Vector(-epsdelta,0,0), Vector(-epsdelta,0,delta), Vector(-epsdelta,delta,delta), Vector(-epsdelta,delta,0)],
                [Vector(0,delta+epsdelta,0), Vector(0,delta+epsdelta,delta), Vector(delta,delta+epsdelta,delta), Vector(delta,delta+epsdelta,0)],
                [Vector(0,-epsdelta,0), Vector(delta,-epsdelta,0), Vector(delta,-epsdelta,delta), Vector(0,-epsdelta,delta)],
                [Vector(0,0,delta+epsdelta), Vector(delta,0,delta+epsdelta), Vector(delta,delta,delta+epsdelta), Vector(0,delta,delta+epsdelta)],
                [Vector(0,0,-epsdelta), Vector(0,delta,-epsdelta), Vector(delta,delta,-epsdelta), Vector(delta,0,-epsdelta)]]

    # and now iterate to find which voxel is inside the bounding box of the 'face',
    vbase = Vector(gbbox.XMin + min_x * delta, gbbox.YMin + min_y * delta, gbbox.ZMin + min_z * delta)
    for step_x in range(min_x,max_x+1):
        vbase.y = gbbox.YMin + min_y * delta
        for step_y in range(min_y,max_y+1):
            vbase.z = gbbox.ZMin + min_z * delta
            for step_z in range(min_z,max_z+1):
                # check if voxel is belonging to the given object
                if voxelSpace[step_x,step_y,step_z] == condIndex:
                    # scan the six neighbour voxels, to see if they are belonging to the same conductor or not.
                    # If they are not belonging to the same conductor, or if the voxel space is finished, the current voxel
                    # side in the direction of the empty voxel is an external surface
                    for side, sideStr, sideCenter, vertex in zip(sides,sideStrs,sideCenters,vertexes):
                        is_surface = False
                        nextVoxelIndexes = [step_x+side[0],step_y+side[1],step_z+side[2]]
                        if (nextVoxelIndexes[0] > max_x or nextVoxelIndexes[0] < 0 or
                           nextVoxelIndexes[1] > max_y or nextVoxelIndexes[1] < 0 or
                           nextVoxelIndexes[2] > max_z or nextVoxelIndexes[2] < 0):
                            is_surface = True
                        else:
                            if voxelSpace[nextVoxelIndexes[0],nextVoxelIndexes[1],nextVoxelIndexes[2]] != condIndex:
                                is_surface = True
                        if is_surface == True:
                            # debug
                            #print("pos_x="+str(vbase.x)+" pos_y="+str(vbase.y)+" pos_z="+str(vbase.z))
                            testVertex.Placement.Base = vbase + sideCenter
                            # if the point is close enough to the face, we consider
                            # the voxel surface as belonging to the voxelized face
                            dist = testVertex.distToShape(face)
                            # debug
                            #print(str(dist))
                            if abs(dist[0]) < halfdelta:
                                contactList.append([step_x,step_y,step_z,sideStr])
                                if createShell:
                                    # create the face
                                    # calculate the vertexes
                                    v11 = vbase + vertex[0]
                                    v12 = vbase + vertex[1]
                                    v13 = vbase + vertex[2]
                                    v14 = vbase + vertex[3]
                                    # now make the face
                                    poly = Part.makePolygon( [v11,v12,v13,v14,v11])
                                    contFace = Part.Face(poly)
                                    surfList.append(contFace)
                vbase.z += delta
            vbase.y += delta
        vbase.x += delta
    contactShell = None
    if createShell:
        if surfList != []:
            # create a shell. Does not need to be solid.
            contactShell = Part.makeShell(surfList)
    return [contactList,contactShell]
    
#bb = App.BoundBox();
#
#objects = App.ActiveDocument.findObjects("Part::Feature")
#for object in objects:
#	bb.add( object.Shape.BoundBox )
#
#print bb
