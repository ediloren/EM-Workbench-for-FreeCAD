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


__title__="FreeCAD E.M. Workbench FastHenry Path Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
#
EMFHPATH_DEF_SEGWIDTH = 0.2
EMFHPATH_DEF_SEGHEIGHT = 0.2
# default max number of segments into which a curve is discretized
EMFHPATH_DEF_DISCR = 3
# the coefficient to apply to the segment width (height) to get
# the minimum radius of curvature allowed
EMFHPATH_TIMESWIDTH = 3
# imported defines
from EM_Globals import EMFHSEGMENT_PARTOL, EMFHSEGMENT_LENTOL

import FreeCAD, FreeCADGui, Mesh, Part, MeshPart, Draft, DraftGeomUtils, os
import DraftVecUtils
from EM_Globals import getAbsCoordBodyPart, makeSegShape
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

def makeFHPath(baseobj=None,name='FHPath'):
    ''' Creates a FastHenry Path (a set connected 'E' FastHenry statements)
    
        'baseobj' is the object on which the path is based.
            If no 'baseobj' is given, the user must assign a base
            object later on, to be able to use this object.
            The 'baseobj' is mandatory, and can be any shape containing edges,
            even if the Path is designed to work best with the support of
            a sketch or a wire.
        'name' is the name of the object
    
    Example:
        path = makeFHPath(myWire)
'''
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    # this adds the relevant properties to the object 
    #'obj' (e.g. 'Base' property) making it a _FHPath 
    _FHPath(obj)
    # manage ViewProvider object
    if FreeCAD.GuiUp:
        _ViewProviderFHPath(obj.ViewObject)
        # set base ViewObject properties to user-selected values (if any)
    # check if 'baseobj' is a wire (only base object allowed), and only if not passed any node
    if baseobj:
        # if right type of base
        if not baseobj.isDerivedFrom("Part::Feature"):
            FreeCAD.Console.PrintWarning(translate("EM","FHPath can only be based on objects derived from Part::Feature"))
            return
        # check validity
        if baseobj.Shape.isNull():
            FreeCAD.Console.PrintWarning(translate("EM","FHPath base object shape is null"))
            return
        if not baseobj.Shape.isValid():
            FreeCAD.Console.PrintWarning(translate("EM","FHPath base object shape is invalid"))
            return
        obj.Base = baseobj
    # hide the base object
    if obj.Base and FreeCAD.GuiUp:
        obj.Base.ViewObject.hide()
    # return the newly created Python object
    return obj

class _FHPath:
    '''The EM FastHenry Path object'''
    def __init__(self, obj):
        ''' Add properties '''
        obj.addProperty("App::PropertyLink", "Base", "EM", QT_TRANSLATE_NOOP("App::Property","The base object this component is built upon"))
        obj.addProperty("App::PropertyLinkList","Nodes","EM",QT_TRANSLATE_NOOP("App::Property","The list of FHNodes along the path. Not for direct user modification."))
        obj.addProperty("App::PropertyLength","Width","EM",QT_TRANSLATE_NOOP("App::Property","Path width ('w' segment parameter)"))
        obj.addProperty("App::PropertyLength","Height","EM",QT_TRANSLATE_NOOP("App::Property","Path height ('h' segment parameter)"))
        obj.addProperty("App::PropertyInteger","Discr","EM",QT_TRANSLATE_NOOP("App::Property","Max number of segments into which curves will be discretized"))
        obj.addProperty("App::PropertyFloat","Sigma","EM",QT_TRANSLATE_NOOP("App::Property","Path conductivity ('sigma' segment parameter)"))
        obj.addProperty("App::PropertyVector","ww","EM",QT_TRANSLATE_NOOP("App::Property","Path cross-section direction along width at the start of the path ('wx', 'wy', 'wz' segment parameter)"))
        obj.addProperty("App::PropertyInteger","nhinc","EM",QT_TRANSLATE_NOOP("App::Property","Number of filaments in the height direction ('nhinc' segment parameter)"))
        obj.addProperty("App::PropertyInteger","nwinc","EM",QT_TRANSLATE_NOOP("App::Property","Number of filaments in the width direction ('nwinc' segment parameter)"))
        obj.addProperty("App::PropertyInteger","rh","EM",QT_TRANSLATE_NOOP("App::Property","Ratio of adjacent filaments in the height direction ('rh' segment parameter)"))
        obj.addProperty("App::PropertyInteger","rw","EM",QT_TRANSLATE_NOOP("App::Property","Ratio of adjacent filaments in the width direction ('rw' segment parameter)"))
        obj.Proxy = self
        self.Type = "FHPath"
        obj.Discr = EMFHPATH_DEF_DISCR
        # save the object in the class, to store or retrieve specific data from it
        # from within the class
        self.Object = obj

    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute() 
    '''
        #FreeCAD.Console.PrintWarning("_FHPath execute()\n") #debug
        # the Path needs a 'Base' object
        if not obj.Base:
            return
        # if right type of base
        if not obj.Base.isDerivedFrom("Part::Feature"):
            FreeCAD.Console.PrintWarning(translate("EM","FHPath can only be based on objects derived from Part::Feature"))
            return
        # check validity
        if obj.Base.Shape.isNull():
            FreeCAD.Console.PrintWarning(translate("EM","FHPath base object shape is null"))
            return
        if not obj.Base.Shape.isValid():
            FreeCAD.Console.PrintWarning(translate("EM","FHPath base object shape is invalid"))
            return
        if obj.Width == None or obj.Width <= 0:
            obj.Width = EMFHPATH_DEF_SEGWIDTH
        if obj.Height == None or obj.Height <= 0:
            obj.Height = EMFHPATH_DEF_SEGHEIGHT
        # the FHPath has no Placement in itself; nodes positions will be in absolute
        # coordinates, as this is what FastHenry understands.
        # The FHSPath Placement is kept at zero, and the 'Base'
        # object Position will be used to find the absolute coordinates
        # of the vertexes, and the segments cross-section orientation will be
        # calculated in absolute coordinates from the Positions rotations.
        # This last part is different from FHSegment.
        if obj.Placement <> FreeCAD.Placement():
            obj.Placement = FreeCAD.Placement()
        # define nodes and segments
        edges_raw = []
        # checking TypeId; cannot check type(obj), too generic
        if obj.Base.TypeId == "Sketcher::SketchObject":
            if obj.Base.Shape.ShapeType == "Wire":
                edges_raw.extend(obj.Base.Shape.Edges)
        # compound
        elif obj.Base.TypeId == "Part::Compound":
            edges_raw.extend(obj.Base.Shape.Edges)
        # line or DWire (Draft Wire)
        elif obj.Base.TypeId == "Part::Part2DObjectPython":
            if obj.Base.Shape.ShapeType == "Wire" or obj.Base.Shape.ShapeType == "Edge":
                edges_raw.extend(obj.Base.Shape.Edges)
        # wire created by upgrading a set of (connected) edges
        elif obj.Base.TypeId == "Part::Feature":
            if obj.Base.Shape.ShapeType == "Wire":
                edges_raw.extend(obj.Base.Shape.Edges)
        # any other part, provided it has a 'Shape' attribute
        else:
            if hasattr(obj.Base, "Shape"):
                edges_raw.extend(obj.Base.Shape.Edges)
            else:
                FreeCAD.Console.PrintWarning(translate("EM","Unsupported base object type for FHPath"))
                return
        # sort the edges. Remark: the edge list might be disconnected (e.g. can happen with a compound
        # containing different edges / wires / sketches). We will join the dangling endpoints with segments later on
        edges = Part.__sortEdges__(edges_raw)
        if edges == []:
            return
        # get the max between the 'obj.Width' and the 'obj.Height'
        if obj.Width > obj.Height:
            geodim = obj.Width
        else:
            geodim = obj.Height
        # scan edges and derive node positions
        self.nodeCoords = []
        # initialize 'lastvertex' to the position of the first vertex,
        # (as if we had a previous segment)
        lastvertex = edges[0].valueAt(edges[0].FirstParameter)
        self.nodeCoords.append(lastvertex)
        for edge in edges:
            # might also rely on "edge.Curve.discretize(Deflection=geodim)"
            # where Deflection is the max distance between any point on the curve,
            # and the polygon approximating the curve
            if type(edge.Curve) == Part.Circle:
                # discretize only if required by the user, and if the curvature radius is not too small
                # vs. the max between the 'obj.Width' and the 'obj.Height'
                if obj.Discr <= 1 or edge.Curve.Radius < geodim*EMFHPATH_TIMESWIDTH:
                    ddisc = 1
                else:
                    ddisc = obj.Discr
            elif type(edge.Curve) == Part.Ellipse:
                # discretize
                if obj.Discr <= 1 or edge.Curve.MajorRadius < geodim*EMFHPATH_TIMESWIDTH or edge.Curve.MinorRadius < geodim*EMFHPATH_TIMESWIDTH:
                    ddisc = 1
                else:
                    ddisc = obj.Discr
            elif type(edge.Curve) == Part.Line:
                # if Part.Line, do not discretize
                ddisc = 1
            else:
                # if any other type of curve, discretize, no matter what.
                # It will be up to the user to decide if the discretization is ok.
                if obj.Discr <= 1:
                    ddisc = 1
                else:
                    ddisc = obj.Discr
            # check if the edge is not too short (could happen e.g. for Part.Line)
            # Note that we calculate the length from 'lastvertex', as we may have skipped also
            # some previous edges, if too short in their turn
            if edge.Length < geodim*EMFHPATH_TIMESWIDTH:
                FreeCAD.Console.PrintWarning(translate("EM","An edge of the Base object supporting the FHPath is too short. FastHenry simulation may fail."))
            step = (edge.LastParameter - edge.FirstParameter) / ddisc
            # if same the last vertex of the previous edge is coincident 
            # with the first vertex of the next edge, skip the vertex
            if (lastvertex-edge.valueAt(edge.FirstParameter)).Length < EMFHSEGMENT_LENTOL:
                start = 1
            else:
                start = 0
            for i in range(start, ddisc):
                # always skip last vertex, will add this at the end
                self.nodeCoords.append(edge.valueAt(edge.FirstParameter + i*step))
            # now add the very last vertex ('LastParameter' provides the exact position)
            lastvertex = edge.valueAt(edge.LastParameter)
            self.nodeCoords.append(lastvertex)
        if len(self.nodeCoords) < 2:
            FreeCAD.Console.PrintWarning(translate("EM","Less than two nodes found, cannot create the FHPath"))
            return
        # find the cross-section orientation of the first segment, according to the 'Base' object Placement.
        # If 'obj.ww' is not defined,  use the FastHenry default (see makeSegShape() )
        self.ww = []
        if obj.ww.Length < EMFHSEGMENT_LENTOL:
            # this is zero anyway (i.e. below 'EMFHSEGMENT_LENTOL')
            self.ww = [Vector(0,0,0)]
        else:
            # transform 'obj.ww' according to the 'Base' Placement
            # (transation is don't care, we worry about rotation)
            self.ww = [obj.Base.Placement.multVec(obj.ww)]
        shapes = []
        # get node positions in absolute coordinates (at least two nodes exist, checked above)
        n1 = getAbsCoordBodyPart(obj.Base,self.nodeCoords[0])
        n2 = getAbsCoordBodyPart(obj.Base,self.nodeCoords[1])
        vNext = n2-n1
        for i in range(1, len(self.nodeCoords)):
            vPrev = vNext
            shape = makeSegShape(n1,n2,obj.Width,obj.Height,self.ww[-1])
            shapes.append(shape)
            # now we must calculate the cross-section orientation 
            # of the next segment, i.e. update 'ww'
            if i < len(self.nodeCoords)-1:
                n1 = n2
                n2 = getAbsCoordBodyPart(obj.Base,self.nodeCoords[i+1])
                vNext = n2-n1
                # get angle in radians
                angle = vPrev.getAngle(vNext)
                # if the angle is actually greater than EMFHSEGMENT_PARTOL (i.e. the segments are not co-linear
                # or almost co-linear)
                if angle*FreeCAD.Units.Radian > EMFHSEGMENT_PARTOL:
                    normal = vPrev.cross(vNext)
                    # rotate 'ww'
                    ww = DraftVecUtils.rotate(self.ww[-1],angle,normal)
                else:
                    # otherwise, keep the previous orientation
                    ww = self.ww[-1]
                self.ww.append(ww)
        shape = Part.makeCompound(shapes)
        # now create or assign FHNodes
        nodes = obj.Nodes
        numnodes = len(nodes)
        modified = False
        import EM_FHNode
        # if there are less FHNodes than required, extend them
        if numnodes < len(self.nodeCoords):
            modified = True
            for index in range(0,len(self.nodeCoords)-numnodes):
                # create a new FHNode at the nodeCoords position
                node = EM_FHNode.makeFHNode(X=self.nodeCoords[numnodes+index].x, Y=self.nodeCoords[numnodes+index].y, Z=self.nodeCoords[numnodes+index].z)
                # insert the new node before the last (the last node always stays the same,
                # to preserve FHPath attachments to other structures, if the FHPath shape changes)
                nodes.insert(-1,node)
        # if instead there are more FHNodes than required, must remove some of them
        elif numnodes > len(self.nodeCoords):
            # but do it only if there are more than two nodes left in the FHPath,
            # otherwise we assume this is a temporary change of FHPath shape,
            # and we preserve the end nodes (do not remove them)
            if numnodes > 2:
                modified = True
                # scan backwards, skipping the last node (last element is 'numnodes-1',
                # and range scans up to the last element before 'numnodes-len(self.nodeCoords)-1'
                for index in range(numnodes-2,len(self.nodeCoords)-2,-1):
                    # remove the node from the 'nodes' list, but keeping the last node
                    node = nodes[index]
                    nodes.pop(index)
                    # check if we can safely remove the extra nodes from the Document;
                    # this can be done only if they do not belong to any other object.
                    # So if the 'InList' member contains one element only, this is
                    # the parent FHPath (we actually check for zero as well, even if 
                    # this should never happen), so we can remove the FHNode 
                    if len(node.InList) <= 1:
                        node.Document.removeObject(node.Name)
        # and finally correct node positions
        for node, nodeCoord in zip(nodes, self.nodeCoords):
            # only if node position is not correct, change it
            if (node.Proxy.getAbsCoord()-nodeCoord).Length > EMFHSEGMENT_LENTOL:
                node.Proxy.setAbsCoord(nodeCoord)
        # only if we modified the list of nodes, re-assign it to the FHPath
        if modified:
            obj.Nodes = nodes
        # shape may be None, e.g. if endpoints coincide. Do not assign in this case
        if shape:
            obj.Shape = shape
        #FreeCAD.Console.PrintWarning("_FHPath execute() ends\n") #debug
    
    def onChanged(self, obj, prop):
        ''' take action if an object property 'prop' changed
    '''
        #FreeCAD.Console.PrintWarning("_FHPath onChanged(" + str(prop)+")\n") #debug
        if not hasattr(self,"Object"):
            # on restore, self.Object is not there anymore (JSON does not serialize complex objects
            # members of the class, so __getstate__() and __setstate__() skip them);
            # so we must "re-attach" (re-create) the 'self.Object'
            self.Object = obj
        if not hasattr(self,"ww"):
            # on restore, self.ww is not there anymore; must recreate through execute(),
            # but first check we have all the needed attributes
            if hasattr(obj,"Base"):
                if hasattr(obj.Base,"Shape"):
                    if not obj.Base.Shape.isNull():
                        if obj.Base.Shape.isValid():
                            self.execute(obj)
        #FreeCAD.Console.PrintWarning("_FHPath onChanged(" + str(prop)+") ends\n") #debug
            
    def serialize(self,fid):
        ''' Serialize the object to the 'fid' file descriptor
    '''
        if len(self.Object.Nodes) > 1:
            if len(self.Object.Nodes) == len(self.ww)+1:
                for index in range(0,len(self.Object.Nodes)-1):
                    fid.write("E" + self.Object.Label + str(index) + " N" + self.Object.Nodes[index].Label + " N" + self.Object.Nodes[index+1].Label)
                    fid.write(" w=" + str(self.Object.Width.Value) + " h=" + str(self.Object.Height.Value))
                    if self.Object.Sigma > 0:
                        fid.write(" sigma=" + str(self.Object.Sigma))
                    if self.ww[index].Length >= EMFHSEGMENT_LENTOL:
                        fid.write(" wx=" + str(self.ww[index].x) + " wy=" + str(self.ww[index].y) + " wz=" + str(self.ww[index].z))
                    if self.Object.nhinc > 0:
                        fid.write(" nhinc=" + str(self.Object.nhinc))
                    if self.Object.nwinc > 0:
                        fid.write(" nwinc=" + str(self.Object.nwinc))
                    if self.Object.rh > 0:
                        fid.write(" rh=" + str(self.Object.rh))
                    if self.Object.rw > 0:
                        fid.write(" rw=" + str(self.Object.rw))
                    fid.write("\n")
            else:
                FreeCAD.Console.PrintError(translate("EM","Error when serializing FHPath. Number of nodes does not match number of segments + 1"))
        else:
            FreeCAD.Console.PrintWarning(translate("EM","Cannot serialize FHPath. Less than two nodes found."))

    def __getstate__(self):
        return self.Type

    def __setstate__(self,state):
        if state:
            self.Type = state
  
class _ViewProviderFHPath:
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
        ''' Used to place other objects as children in the tree'''
        c = []
        if hasattr(self,"Object"):
            if hasattr(self.Object,"Base"):
                c.append(self.Object.Base)
            if hasattr(self.Object,"Nodes"):
                c.extend(self.Object.Nodes)
        return c

    def getIcon(self):
        ''' Return the icon which will appear in the tree view. This method is optional
        and if not defined a default icon is shown.
        '''
        return os.path.join(iconPath, 'EM_FHPath.svg')

    def __getstate__(self):
        return None

    def __setstate__(self,state):
        return None

class _CommandFHPath:
    ''' The EM FastHenry Path (FHPath) command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'EM_FHPath.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_FHPath","FHPath"),
                'Accel': "E, T",
                'ToolTip': QT_TRANSLATE_NOOP("EM_FHPath","Creates a Path object (set of connected FastHenry segments) from a selected base object (sketch, wire or any shape containing edges)")}
                
    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        # preferences
        #p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/EM")
        #self.Width = p.GetFloat("Width",200)
        # get the selected object(s)
        selection = FreeCADGui.Selection.getSelectionEx()
        # if selection is not empty
        done = False
        for selobj in selection:
            # automatic mode
            if selobj.Object.isDerivedFrom("Part::Feature"):
                FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FHPath"))
                FreeCADGui.addModule("EM")
                FreeCADGui.doCommand('obj=EM.makeFHPath(FreeCAD.ActiveDocument.'+selobj.Object.Name+')')
                # autogrouping, for later on
                #FreeCADGui.addModule("Draft")
                #FreeCADGui.doCommand("Draft.autogroup(obj)")
                FreeCAD.ActiveDocument.commitTransaction()
                FreeCAD.ActiveDocument.recompute()
                # this is not a mistake. The double recompute() is needed to show the new FHNode object
                # that have been created by the first execute(), called upon the first recompute()
                FreeCAD.ActiveDocument.recompute()
                done = True
        if done == False:
            FreeCAD.Console.PrintWarning(translate("EM","No valid object found in the selection for the creation of a FHPath. Nothing done."))

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_FHPath',_CommandFHPath())

