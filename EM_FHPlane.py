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


__title__="FreeCAD E.M. Workbench FastHenry uniform Plane Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
#
# default plane thickness
EMFHPLANE_DEF_THICKNESS = 0.1
# default number of segments along length
EMFHPLANE_DEF_SEG1 = 10
# default number of segments along width
EMFHPLANE_DEF_SEG2 = 10
# default plane node color
EMFHNODE_DEF_PLANENODECOLOR = (0.0,0.0,1.0)
# default plane node name extension
EMFHNODE_DEF_NODENAMEEXT = "p"

import FreeCAD, FreeCADGui, Mesh, Part, MeshPart, Draft, DraftGeomUtils, os
import numpy as np
from math import sqrt
from EM_Globals import EMFHNODE_DEF_NODECOLOR
from FreeCAD import Vector

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtGui
    from DraftTools import translate
    from PySide.QtCore import QT_TRANSLATE_NOOP
else:
    # \cond
    def translate(ctxt,txt, utf8_decode=False):
        return txt
    def QT_TRANSLATE_NOOP(ctxt,txt):
        return txt
    # \endcond

__dir__ = os.path.dirname(__file__)
iconPath = os.path.join( __dir__, 'Resources' )

def makeFHPlane(baseobj=None,thickness=None,seg1=None,seg2=None,nodes=[],holes=[],name='FHPlane'):
    ''' Creates a FastHenry uniform Plane ('G' statement in FastHenry)
    
        'baseobj' is the object on which the node is based.
            This can be a Part::Box or a Draft::Rectangle.
            If no 'baseobj' is given, the user must assign a base
            object later on, to be able to use this object.
        'thickness' is a float defining the plane thickness. If not defines,
            it defaults to EMFHPLANE_DEF_THICKNESS
        'seg1' is an integer defining the number of segments 
            along the x dimension of the plane
            ('seg1' parameter in FastHenry)
        'seg2' is an integer defining the number of segments
            along the y dimension of the plane
            ('seg2' parameter in FastHenry)
        'nodes' is an array of FHNode objects, specifying the nodes that
            will be adopted by the plane
        'holes' is an array of FHPlaneHole objects, specifying the holes that
            will be adopted by the plane
        'name' is the name of the object
    
    Example:
        plane = makeFHPlane(myDraftRect,thickness=1.0,seg1=15,seg2=15,[App.ActiveDocument.Node001])
'''
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    # this adds the relevant properties to the object 
    #'obj' (e.g. 'Base' property) making it a _FHSegment 
    _FHPlane(obj)
    # manage ViewProvider object
    if FreeCAD.GuiUp:
        _ViewProviderFHPlane(obj.ViewObject)
        # set base ViewObject properties to user-selected values (if any)
    # check if 'nodeStart' is a FHNode, and if so, assign it as segment start node
    # check if 'baseobj' is a wire (only base object allowed)
    if baseobj:
        if baseobj.TypeId == "Part::Box" or Draft.getType(baseobj) == "Rectangle":
            obj.Base = baseobj
            # if we have a Base object, we can also adopt children.
            # Not possible without, otherwise we don't have a valid placement
            #
            # verify the list of nodes, and link the actual nodes to the plane
            real_nodes = []
            if len(nodes) > 0:
                for node in nodes:
                    # get only the nodes out of the list (if this is a selection,
                    # it might contain other objects; we don't complain, but extract only the FHNodes)
                    if Draft.getType(node) == "FHNode":
                        real_nodes.append(node)
            obj.Nodes = real_nodes
            # verify the list of holes, and link the actual holes to the plane
            real_holes = []
            if len(holes) > 0:
                for hole in holes:
                    # get only the holes out of the list (if this is a selection,
                    # it might contain other objects; we don't complain, but extract only the FHHoles)
                    if Draft.getType(hole) == "FHPlaneHole":
                        real_holes.append(hole)
            obj.Holes = real_holes
        else:
            FreeCAD.Console.PrintWarning(translate("EM","FHPlane can only be based on Part::Box or Plane::Rectangle objects"))
    if thickness:
        if thickness > 0.0:
            # using a conversion and not catching errors, for input validation
            obj.Thickness = float(thickness)
        else:
            FreeCAD.Console.PrintWarning(translate("EM","FHPlane thickness parameter must be strictly positive"))
    if seg1:
        if seg1 > 0.0:
            # using a conversion and not catching errors, for input validation
            obj.seg1 = int(seg1)
        else:
            FreeCAD.Console.PrintWarning(translate("EM","FHPlane seg1 parameter must be strictly positive"))
    if seg2:
        if seg2 > 0.0:
            # using a conversion and not catching errors, for input validation
            obj.seg2 = int(seg2)
        else:
            FreeCAD.Console.PrintWarning(translate("EM","FHPlane seg2 parameter must be strictly positive"))
    # hide the base object
    if obj.Base and FreeCAD.GuiUp:
        obj.Base.ViewObject.hide()
    # return the newly created Python object
    return obj

class _FHPlane:
    '''The EM FastHenry uniform Plane object'''
    def __init__(self, obj):
        ''' Add properties '''
        obj.addProperty("App::PropertyLink", "Base", "EM", QT_TRANSLATE_NOOP("App::Property","The base object this component is built upon"))
        obj.addProperty("App::PropertyLength","Thickness","EM",QT_TRANSLATE_NOOP("App::Property","Plane thickness ('thick' plane parameter)"))
        obj.addProperty("App::PropertyInteger","seg1","EM",QT_TRANSLATE_NOOP("App::Property","Number of segments along the length direction ('seg1' plane parameter)"))
        obj.addProperty("App::PropertyInteger","seg2","EM",QT_TRANSLATE_NOOP("App::Property","Number of segments along the width direction ('seg2' plane parameter)"))
        obj.addProperty("App::PropertyInteger","nhinc","EM",QT_TRANSLATE_NOOP("App::Property","Number of filaments along the plane thickness ('nhinc' plane parameter)"))
        obj.addProperty("App::PropertyInteger","rh","EM",QT_TRANSLATE_NOOP("App::Property","Ratio of adjacent filaments along the thickness ('rh' plane parameter)"))
        obj.addProperty("App::PropertyFloat","Sigma","EM",QT_TRANSLATE_NOOP("App::Property","Plane conductivity ('sigma' plane parameter)"))
        obj.addProperty("App::PropertyLength","segwid1","EM",QT_TRANSLATE_NOOP("App::Property","Width of segments along the plane length direction ('segwid1' plane parameter)"))
        obj.addProperty("App::PropertyLength","segwid2","EM",QT_TRANSLATE_NOOP("App::Property","Width of segments along the plane width direction ('segwid2' plane parameter)"))
        obj.addProperty("App::PropertyLinkList","Nodes","EM",QT_TRANSLATE_NOOP("App::Property","Nodes for connections to the plane"))
        obj.addProperty("App::PropertyLinkList","Holes","EM",QT_TRANSLATE_NOOP("App::Property","Holes in the plane"))
        obj.addProperty("App::PropertyBool","FineMesh","Component",QT_TRANSLATE_NOOP("App::Property","Specifies if this the plane fine mesh is shown (i.e. composing segments)"))
        obj.addProperty("App::PropertyBool","ShowNodes","Component",QT_TRANSLATE_NOOP("App::Property","Show the internal node grid supporting the plane"))
        obj.Proxy = self
        self.Type = "FHPlane"
        self.FineMesh = False
        self.ShowNodes = True
        # save the object in the class, to store or retrieve specific data from it
        # from within the class
        self.Object = obj

    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute() 
    '''
        #FreeCAD.Console.PrintWarning("\n_FHPlane execute\n") #debug
        if obj.Thickness == None or obj.Thickness <= 0:
            obj.Thickness = EMFHPLANE_DEF_THICKNESS
        if obj.seg1 == None or obj.seg1 <= 0:
            obj.seg1 = EMFHPLANE_DEF_SEG1
        if obj.seg2 == None or obj.seg2 <= 0:
            obj.seg2 = EMFHPLANE_DEF_SEG2
        # check if we have a 'Base' object; if not, cannot assign a shape
        shape = None
        if obj.Base:
            # if right type of base
            if obj.Base.isDerivedFrom("Part::Feature"):
                # check validity
                if obj.Base.Shape.isNull():
                    return
                if not obj.Base.Shape.isValid():
                    return
                # ok, 'Base' is valid. Go on.
                #
                # Part::Box and Draft::Rectangle define the Plane width through
                # a different property. For the Box it is the Width, but for the
                # Rectangle this is the Height
                if obj.Base.TypeId == "Part::Box":
                    width = obj.Base.Width.Value
                    # Also, if Part::Box, set the Plane thickness
                    # to the Box thickness, no matter what the user entered as 'Thickness'
                    obj.Thickness = obj.Base.Height
                elif Draft.getType(obj.Base) == "Rectangle":
                    width = obj.Base.Height.Value
                else:
                    FreeCAD.Console.PrintWarning(translate("EM","Plane Base object is not a Part::Box nor a Draft::Rectangle"))
                    return
                # The length property is instead the same for the Box and the Rectangle alike
                length = obj.Base.Length.Value
                # And thickness has been set, can get it
                thickness = obj.Thickness.Value
                # Let's calculate the segments width
                segwid1 = width / obj.seg2
                segwid2 = length / obj.seg1
                # if the user specified a different segment width, assign it to the segments, unless
                # the specified width is larger than the segment width needed to completely 
                # fill up the plane. In this case reset 'segwid1' to this width.
                if obj.segwid1 > 0:
                    if obj.segwid1 < segwid1:
                        segwid1 = obj.segwid1.Value
                    else:
                        obj.segwid1 = segwid1
                        FreeCAD.Console.PrintWarning(translate("EM","Plane segwid1 would cause segments overlap, re-setting segwid1 to the maximum possible"))
                if obj.segwid2 > 0:
                    if obj.segwid2 < segwid2:
                        segwid2 = obj.segwid2.Value
                    else:
                        obj.segwid2 = segwid2
                        FreeCAD.Console.PrintWarning(translate("EM","Plane segwid2 would cause segments overlap, re-setting segwid2 to the maximum possible"))
                # if needed, apply the same Placement of the Base object to the FHPlane object
                if obj.Placement <> obj.Base.Placement:
                    obj.Placement = obj.Base.Placement
                # Start node and hole repositioning in relative coordinate system of the conductive plane
                #
                # These nodes have already been adopted by the plane, if they are in the obj.Nodes list;
                # therefore, must just make sure they track the plane placement. Also, this assures
                # that once a node is child of a plane, it cannot be moved independently by changing
                # its placement
                for node in obj.Nodes:
                    if node.Placement <> obj.Placement:
                        node.Placement = obj.Placement
                # These holes have already been adopted by the plane, if they are in the obj.Holes list;
                # therefore, must just make sure they track the plane placement. Also, this assures
                # that once a hole is child of a plane, it cannot be moved independently by changing
                # its placement
                for hole in obj.Holes:
                    if hole.Placement <> obj.Placement:
                        hole.Placement = obj.Placement
                # Check if the user selected a coarse or a fine mesh.
                if obj.FineMesh == False:
                    # Now we can define the coarse shape. A uniform plane will extend half-a-segment
                    # beyond the boundaries of the plane definition.
                    # Therefore, we'll make two box shapes, crossing over each other.
                    #
                    # Extend half segwid1 on both y sides
                    # makeBox(length, width, height, point, direction)
                    boxshape1 = Part.makeBox(length,width+segwid1,thickness,Vector(0,-segwid1/2,0))
                    # Extend half segwid2 on both x sides
                    # makeBox(length, width, height, point, direction)
                    boxshape2 = Part.makeBox(length+segwid2,width,thickness,Vector(-segwid2/2,0,0))
                    # create the compound object
                    shape = Part.makeCompound([boxshape1,boxshape2])
                else:
                    shape = self.makeFinePlane(obj,length,width,thickness,segwid1,segwid2)
        # and finally assign the shape
        if shape:
            obj.Shape = shape

    def adoptNode(self,node):
        ''' Adopt a node in the FHPlane

            'node': FHNode object
            
            The placement is changed to be relative to the plane coordinate system.
            The color of the node will be changed, to show that this is a FHPlane node
    '''
        # must now keep the node in the same absolute position, but making the position
        # relative to the plane coordinate system 
        abs_pos = node.Proxy.getAbsCoord()
        node.Proxy.setAbsCoord(abs_pos,self.Object.Base.Placement)
        # set the Z relative coordinate to zero (node will be on the plane)
        node.Z = 0.0
        # and change its color to mark that this is a plane node
        node.ViewObject.PointColor = EMFHNODE_DEF_PLANENODECOLOR

    def removeNode(self,node):
        ''' Remove a node from the FHPlane

            'node': FHNode object
            
            The color of the node will be reverted to the default node color
    '''
        node.ViewObject.PointColor = EMFHNODE_DEF_NODECOLOR

    def adoptHole(self,hole):
        ''' Adopt a hole in the FHPlane

            'hole': FHPlaneHole object
            
            The placement is changed to be relative to the plane coordinate system.
    '''
        # must now keep the node in the same absolute position, but making the position
        # relative to the plane coordinate system 
        abs_pos = hole.Proxy.getAbsCoord()
        hole.Proxy.setAbsCoord(abs_pos,self.Object.Base.Placement)
        # set the Z relative coordinate to zero (node will be on the plane)
        hole.Z = 0.0

    def removeHole(self,hole):
        ''' Remove a hole from the FHPlane

            'hole': FHPlaneHole object
    '''
        return
            
    def makeFinePlane(self,obj,length,width,thickness,segwid1,segwid2):
        ''' Compute a fine mesh plane shape given:
            
            'obj' the FHPlane object
            'length' the length of the plane (along the x dimension)
            'width' the width of the plane (along the y dimension)
            'thickness' the thickness of the plane (along the z dimension)
            'segwid1' the width of the segments along the x dimension
            'segwid2' the width of the segments along the y dimension
            
            The function returns a Shape object defining the plane.
            
            The plane is assumed to lie in the standard default position (default Placement)
            (with the Placement.Base in the origin, no rotation, and length along x, width along y, thickness along z)
            Its placement will be moved and rotated by the caller.
    '''
        shapes=[]
        # prepare the array of the internal nodes of the plane. 'True' means that the node 
        # exists, i.e. has not been removed due to holes in the plane.
        # The number of nodes is equal to the number of segments along the edge plus one;
        # (note that 'obj.seg1' refers to the # of segment parallel to the length, 'obj.seg2' parallel to the width)
        nodes=np.full((obj.seg1+1,obj.seg2+1), True, np.bool)
        # find segment lengths
        seg1len=length/obj.seg1
        seg2len=width/obj.seg2
        #
        if obj.ShowNodes == True:
            for seg1 in range(obj.seg1+1):
                for seg2 in range(obj.seg2+1):
                    shape = Part.Vertex(Vector(seg1len*seg1,seg2len*seg2,-0.1))
                    shapes.append(shape)
        # now process the holes
        for hole in obj.Holes:
            if hole.Type == 'Point':
                seg1seg2pos = self.findNearestNode(hole.X, hole.Y, obj, seg1len, seg2len)
                # mark the node as deleted
                nodes[seg1seg2pos] = False
            elif hole.Type == 'Rect':
                seg1seg2corner1 = self.findNearestNode(hole.X, hole.Y, obj, seg1len, seg2len)
                seg1seg2corner2 = self.findNearestNode(hole.X + hole.Length, hole.Y + hole.Width, obj, seg1len, seg2len)
                # hole.Length and hole.Width may be negative. Must check which comes first
                if seg1seg2corner1[0] <= seg1seg2corner2[0]:
                    xstart = seg1seg2corner1[0]
                    xend = seg1seg2corner2[0]
                else:
                    xstart = seg1seg2corner2[0]
                    xend = seg1seg2corner1[0]
                if seg1seg2corner1[1] <= seg1seg2corner2[1]:
                    ystart = seg1seg2corner1[1]
                    yend = seg1seg2corner2[1]
                else:
                    ystart = seg1seg2corner2[1]
                    yend = seg1seg2corner1[1]
                # mark the nodes as deleted
                nodes[xstart:xend+1,ystart:yend+1] = False
            elif hole.Type == 'Circle':
                seg1seg2pos = self.findNearestNode(hole.X, hole.Y, obj, seg1len, seg2len)
                # find the offset between the center of the circle and the actual nearest plane node node
                offsetX = seg1seg2pos[0]*seg1len - hole.X.Value
                offsetY = seg1seg2pos[1]*seg2len - hole.Y.Value
                # check if the offset is larger than the radius
                if abs(offsetX) > hole.Radius.Value or abs(offsetY) > hole.Radius.Value:
                    FreeCAD.Console.PrintWarning(translate("EM","Circular hole offset w.r.t. the nearest node plane is greater than hole radius. Hole not performed."))
                # 'nodes_up' and 'nodes_down' are the (relative) number of hole nodes along plane width
                # we will then step from 'nodes_down' to 'nodes_up' and for each of these values
                # we will calculate the (relative) extent from 'nodes_left' to 'node_right' along the length 
                # corresponding to the hole radius and we will remove all the contained nodes
                nodes_up = int( (hole.Radius.Value - offsetY)/seg2len)
                nodes_down = int( (-hole.Radius.Value - offsetY)/seg2len)
                for nodeY in range(nodes_down,nodes_up+1):
                    side = sqrt(hole.Radius.Value**2 - (offsetY+nodeY*seg2len)**2)
                    nodes_left = int( (-side - offsetX)/seg1len)
                    nodes_right = int( (side - offsetX)/seg1len)
                    for nodeX in range(nodes_left,nodes_right+1):
                        # delete node, but only if internal to the plane!
                        if nodeY+seg1seg2pos[1] >= 0 and nodeY+seg1seg2pos[1] <= obj.seg2 and nodeX+seg1seg2pos[0] >= 0 and nodeX+seg1seg2pos[1] <= obj.seg1:
                            nodes[nodeX+seg1seg2pos[0], nodeY+seg1seg2pos[1]] = False
            else:
                FreeCAD.Console.PrintWarning(translate("EM","Unknown hole type in the FHPlane!"))
        # layout segments along plane length
        for seg2 in range(obj.seg2+1):
            for seg1 in range(obj.seg1):
                # if both starting and ending nodes exist
                if nodes[seg1][seg2] and nodes[seg1+1][seg2]:
                    # makeBox(length, width, height, point, direction)
                    boxshape = Part.makeBox(seg1len,segwid1,thickness,Vector(seg1len*seg1,-segwid1/2+seg2len*seg2,0))
                    shapes.append(boxshape)
        # layout segments along plane width
        for seg1 in range(obj.seg1+1):
            for seg2 in range(obj.seg2):
                # if both starting and ending nodes exist
                if nodes[seg1][seg2] and nodes[seg1][seg2+1]:
                    # makeBox(length, width, height, point, direction)
                    boxshape = Part.makeBox(segwid2,seg2len,thickness,Vector(-segwid2/2+seg1len*seg1,seg2len*seg2,0))
                    shapes.append(boxshape)
        shape = Part.makeCompound(shapes)
        return shape
 
    def findNearestNode(self,x_coord,y_coord,obj,seg1len,seg2len):
        ''' Find the plane node nearest to the given point (in local plane coordinates)
        
            'x_coord' and 'y_coord' are the point coordinates, of type Base.Quantity
            'obj' is the FHPlane object
            'seg1len' and 'seg2len' are the lengths of the segments along the lenght and width, respectively

            The function returns a tuple containing two integers corresponding to the node
            position within the plane array of internal nodes.
    '''
        # as we cast to int, + 0.5 is used to approximate to the next larger int
        # if greater than x.5 and to the previous smaller int otherwise
        nodeX = int(x_coord.Value/seg1len + 0.5)
        nodeY = int(y_coord.Value/seg2len + 0.5)
        # assure that the node is on the plane
        if nodeX < 0:
            nodeX = 0
        elif nodeX > obj.seg1:
            nodeX = obj.seg1
        if nodeY < 0:
            nodeY = 0
        elif nodeY > obj.seg2:
            nodeY = obj.seg2
        return (nodeX,nodeY)
            
    def onBeforeChange(self, obj, prop):
        ''' take action before the 'obj' object 'prop' will change
    '''
        # save current list of nodes and holes, before the change,
        # to be able to see which nodes/holes have been added or removed
        self.Nodes = obj.Nodes
        self.Holes = obj.Holes
        
    def onChanged(self, obj, prop):
        ''' take action if an object property 'prop' changed
    '''
        #FreeCAD.Console.PrintWarning("\n_FHPlane onChanged(" + str(prop)+")\n") #debug
        if not hasattr(self,"Object"):
            # on restore, self.Object is not there anymore (JSON does not serialize complex objects
            # members of the class, so __getstate__() and __setstate__() skip them);
            # so we must "re-attach" (re-create) the 'self.Object'
            self.Object = obj
        if prop == "Nodes":
            # check for new nodes
            for node in obj.Nodes:
                # if the node has been just added to the plane, adopt it
                if not node in self.Nodes:
                    self.adoptNode(node)
            # check for removed nodes
            for node in self.Nodes:
                # if the node is not present any more in the plane, remove it
                if not node in obj.Nodes:
                    self.removeNode(node)
        if prop == "Holes":
            # check for new holes
            for hole in obj.Holes:
                # if the hole has been just added to the plane, adopt it
                if not hole in self.Holes:
                    self.adoptHole(hole)
            # check for removed holes
            for hole in self.Holes:
                # if the hole is not present any more in the plane, remove it
                if not hole in obj.Holes:
                    self.removeHole(hole)

    def serialize(self,fid):
        ''' Serialize the object to the 'fid' file descriptor
    '''
        if not self.Object.Base:
            FreeCAD.Console.PrintWarning(translate("EM","No Plane Base object set. Cannot serialize the object.\n"))
            return
        # must retrieve the three corners in clockwise order from the self.Object.Base
        # parameters (Position and dimensions)
        if self.Object.Base.TypeId == "Part::Box":
            width = self.Object.Base.Width.Value
        elif Draft.getType(self.Object.Base) == "Rectangle":
            width = self.Object.Base.Height.Value
        else:
            FreeCAD.Console.PrintWarning(translate("EM","Plane Base object is not a Part::Box nor a Draft::Rectangle. Cannot serialize the object.\n"))
            return
        # These two properties are instead the same for the Box and the Rectangle alike
        length = self.Object.Base.Length.Value
        placement = self.Object.Base.Placement
        # plus height (thickness)
        height = self.Object.Thickness.Value
        planeOrigin = placement.Base
        # plane versors. 'vx' is along length, 'vy' is along width, 'vz' is along height (thickness)
        vx = (placement.multVec(Vector(1,0,0))-planeOrigin).normalize()
        vy = (placement.multVec(Vector(0,1,0))-planeOrigin).normalize()
        vz = (placement.multVec(Vector(0,0,1))-planeOrigin).normalize()
        # compute the corners
        corner = []
        corner.append(planeOrigin + vz*(height/2))
        corner.append(corner[0] + vx*length)
        corner.append(corner[1] + vy*width)
        # now output plane parameters
        fid.write("G" + self.Object.Label + " x1=" + str(corner[0].x) + " y1=" + str(corner[0].y) + " z1=" + str(corner[0].z))
        fid.write(" x2=" + str(corner[1].x) + " y2=" + str(corner[1].y) + " z2=" + str(corner[1].z) + "\n")
        fid.write("+         x3=" + str(corner[2].x) + " y3=" + str(corner[2].y) + " z3=" + str(corner[2].z) + "\n")
        fid.write("+         thick=" + str(height) + " seg1=" + str(self.Object.seg1) + " seg2=" + str(self.Object.seg2) + "\n")
        if self.Object.segwid1 > 0:
            fid.write("+         segwid1=" + str(self.Object.segwid1) + "\n")
        if self.Object.segwid2 > 0:
            fid.write("+         segwid2=" + str(self.Object.segwid2) + "\n")
        if self.Object.Sigma > 0:
            fid.write("+         sigma=" + str(self.Object.Sigma) + "\n")
        if self.Object.nhinc > 0:
            fid.write("+         nhinc=" + str(self.Object.nhinc) + "\n")
        if self.Object.rh > 0:
            fid.write("+         rh=" + str(self.Object.rh) + "\n")
        # Output the plane exposed nodes
        # Nstr (x_val,y_val,z_val)
        if len(self.Object.Nodes) > 0:
            for node in self.Object.Nodes:
                # plane nodes are special nodes. We assume that a node 'N' definition already exist
                # with the 'node.Label'; so we define an internal plane node with the same name
                # but with an additional extension, and then we'll '.equiv' the two
                node.Proxy.serialize(fid, EMFHNODE_DEF_NODENAMEEXT)
        # hole <hole-type> (val1,val2,....)
        #   hole point (x,y,z)
        #   hole rect (x1,y1,z1,x2,y2,z2)
        #   hole circle (x,y,z,r)
        if len(self.Object.Holes) > 0:
            for hole in self.Object.Holes:
                hole.Proxy.serialize(fid)
        fid.write("\n")
        if len(self.Object.Nodes) > 0:
            fid.write("* Connecting internal plane nodes to actual nodes\n")
            for node in self.Object.Nodes:
                fid.write(".equiv N" + node.Label + " N" + node.Label + EMFHNODE_DEF_NODENAMEEXT + "\n")
            fid.write("\n")
        
    def __getstate__(self):
        return self.Type

    def __setstate__(self,state):
        if state:
            self.Type = state
  
class _ViewProviderFHPlane:
    def __init__(self, obj):
        ''' Set this object to the proxy object of the actual view provider '''
        obj.Proxy = self
        self.Object = obj.Object

    def attach(self, obj):
        ''' Setup the scene sub-graph of the view provider, this method is mandatory '''
        # on restore, self.Object is not there anymore (JSON does not serialize complex objects
        # members of the class, so __getstate__() and __setstate__() skip them);
        # so we must "re-attach" (re-create) the 'self.Object'
        self.Object = obj.Object
        return

    def updateData(self, fp, prop):
        ''' If a property of the handled feature has changed we have the chance to handle this here '''
        #FreeCAD.Console.PrintMessage("ViewProvider updateData(),  property: " + str(prop) + "\n") # debug
        return

    def getDefaultDisplayMode(self):
        ''' Return the name of the default display mode. It must be defined in getDisplayModes. '''
        return "Flat Lines"

    def onChanged(self, vp, prop):
        ''' If the 'prop' property changed for the ViewProvider 'vp' '''
        #FreeCAD.Console.PrintMessage("ViewProvider onChanged(), property: " + str(prop) + "\n") # debug

    def claimChildren(self):
        ''' Used to place other objects as childrens in the tree'''
        c = []
        if hasattr(self,"Object"):
            if hasattr(self.Object,"Base"):
                c.append(self.Object.Base)
            if hasattr(self.Object,"Nodes"):
                c.extend(self.Object.Nodes)
            if hasattr(self.Object,"Holes"):
                c.extend(self.Object.Holes)
        return c

    def getIcon(self):
        ''' Return the icon which will appear in the tree view. This method is optional
        and if not defined a default icon is shown.
        '''
        return os.path.join(iconPath, 'plane_icon.svg')

    def __getstate__(self):
        return None

    def __setstate__(self,state):
        return None

class _CommandFHPlane:
    ''' The EM FastHenry uniform Plane (FHPlane) command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'plane_icon.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_FHPlane","FHPlane"),
                'Accel': "E, P",
                'ToolTip': QT_TRANSLATE_NOOP("EM_FHPlane","Creates a FastHenry uniform Plane object from a selected base object (Part::Box or Draft::Rectangle)")}
                
    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        # init properties (future)
        #self.Length = None
        # preferences
        #p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/EM")
        #self.Width = p.GetFloat("Width",200)
        # get the selected object(s)
        selection = FreeCADGui.Selection.getSelectionEx()
        base = None
        nodes = []
        holes = []
        # if selection is not empty
        for selobj in selection:
            # automatic mode
            if selobj.Object.TypeId == "Part::Box" or Draft.getType(selobj.Object) == "Rectangle":
                if not base:
                    base = selobj.Object
                else:
                    FreeCAD.Console.PrintWarning(translate("EM","More than one Part::Box or Draft::Rectangle selected. Using the first one as FHPlane Base object.\n"))
            elif Draft.getType(selobj.Object) == "FHNode":
                nodes.append(selobj.Object)
            elif Draft.getType(selobj.Object) == "FHPlaneHole":
                holes.append(selobj.Object)
        if base:
            FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FHPlane"))
            FreeCADGui.addModule("EM")
            FreeCADGui.doCommand('nodeList=[]')
            for node in nodes:
                FreeCADGui.doCommand('nodeList.append(FreeCAD.ActiveDocument.'+node.Name+')')
            FreeCADGui.doCommand('holeList=[]')
            for hole in holes:
                FreeCADGui.doCommand('holeList.append(FreeCAD.ActiveDocument.'+hole.Name+')')
            FreeCADGui.doCommand('obj=EM.makeFHPlane(FreeCAD.ActiveDocument.'+base.Name+',nodes=nodeList,holes=holeList)')
            # autogrouping, for later on
            #FreeCADGui.addModule("Draft")
            #FreeCADGui.doCommand("Draft.autogroup(obj)")
            FreeCAD.ActiveDocument.commitTransaction()
            FreeCAD.ActiveDocument.recompute()
            # this is not a mistake. The double recompute() is needed to show the new FHNode positions
            # have been updated by the first execute(), called upon the first recompute()
            FreeCAD.ActiveDocument.recompute()
        # if no selection, or nothing good in the selected objects
        else:
            FreeCAD.Console.PrintWarning(translate("EM","No base Part::Box or Draft::Rectangle selected. Cannot create a FHPlane.\n"))

class _CommandFHPlaneAddRemoveNodeHole:
    ''' The EM FastHenry uniform Plane (FHPlane) add, or remove, Node, or Hole, command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'plane_addremovenodehole_icon.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_FHPlaneAddRemoveNodeHole","FHPlaneAddRemoveNodeHole"),
                'Accel': "E, A",
                'ToolTip': QT_TRANSLATE_NOOP("EM_FHPlaneAddRemoveNodeHole","Add/remove FHNodes or FHPlaneHoles to/from a FastHenry uniform Plane object")}
                
    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        # preferences
        #p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/EM")
        #self.Width = p.GetFloat("Width",200)
        # get the selected object(s)
        selection = FreeCADGui.Selection.getSelectionEx()
        plane = None
        nodes = []
        holes = []
        # if selection is not empty
        for selobj in selection:
            # find the FHPlane
            if Draft.getType(selobj.Object) == "FHPlane":
                plane = selobj.Object
            elif Draft.getType(selobj.Object) == "FHNode":
                nodes.append(selobj.Object)
            elif Draft.getType(selobj.Object) == "FHPlaneHole":
                holes.append(selobj.Object)
        # whether or not a plane is selected, nodes/holes to be removed belong to a plane.
        # Let's start with them.
        addnodes = []
        for node in nodes:
            found = False
            for parent in node.InList:
                if Draft.getType(parent) == "FHPlane":
                    # parent found, now remove the node
                    FreeCAD.ActiveDocument.openTransaction(translate("EM","Remove FHPlane Node"))
                    FreeCADGui.addModule("EM")
                    FreeCADGui.doCommand('nodes = FreeCAD.ActiveDocument.'+parent.Name+'.Nodes')
                    FreeCADGui.doCommand('nodes.remove(FreeCAD.ActiveDocument.'+node.Name+')')
                    FreeCADGui.doCommand('FreeCAD.ActiveDocument.'+parent.Name+'.Nodes = nodes')
                    FreeCAD.ActiveDocument.commitTransaction()
                    found = True
            if found == False:
                addnodes.append(node)
        addholes = []
        for hole in holes:
            found = False
            for parent in hole.InList:
                if Draft.getType(parent) == "FHPlane":
                    # parent found, now remove the hole
                    FreeCAD.ActiveDocument.openTransaction(translate("EM","Remove FHPlane Hole"))
                    FreeCADGui.addModule("EM")
                    FreeCADGui.doCommand('holes = FreeCAD.ActiveDocument.'+parent.Name+'.Holes')
                    FreeCADGui.doCommand('holes.remove(FreeCAD.ActiveDocument.'+hole.Name+')')
                    FreeCADGui.doCommand('FreeCAD.ActiveDocument.'+parent.Name+'.Holes = holes')
                    FreeCAD.ActiveDocument.commitTransaction()
                    found = True
            if found == False:
                addholes.append(hole)
        # the remaining nodes/holes can only be added to a plane. For this we need a plane
        # in the selection
        if plane:
            FreeCAD.ActiveDocument.openTransaction(translate("EM","Add nodes / holes to the FHPlane"))
            FreeCADGui.addModule("EM")
            FreeCADGui.doCommand('nodeList = FreeCAD.ActiveDocument.'+plane.Name+'.Nodes')
            for node in addnodes:
                FreeCADGui.doCommand('nodeList.append(FreeCAD.ActiveDocument.'+node.Name+')')
            FreeCADGui.doCommand('FreeCAD.ActiveDocument.'+plane.Name+'.Nodes = nodeList')
            FreeCADGui.doCommand('holeList = FreeCAD.ActiveDocument.'+plane.Name+'.Holes')
            for hole in addholes:
                FreeCADGui.doCommand('holeList.append(FreeCAD.ActiveDocument.'+hole.Name+')')
            FreeCADGui.doCommand('FreeCAD.ActiveDocument.'+plane.Name+'.Holes = holeList')
            FreeCAD.ActiveDocument.commitTransaction()
        # recompute the document (assuming something has changed; otherwise this is dummy)
        FreeCAD.ActiveDocument.recompute()
        
if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_FHPlane',_CommandFHPlane())
    FreeCADGui.addCommand('EM_FHPlaneAddRemoveNodeHole',_CommandFHPlaneAddRemoveNodeHole())
