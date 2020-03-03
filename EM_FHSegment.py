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


__title__="FreeCAD E.M. Workbench FastHenry Segment Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
#
EMFHSEGMENT_DEF_SEGWIDTH = 0.2
EMFHSEGMENT_DEF_SEGHEIGHT = 0.2
# imported defines
from EM_Globals import EMFHSEGMENT_PARTOL, EMFHSEGMENT_LENTOL

import FreeCAD, FreeCADGui, Mesh, Part, MeshPart, Draft, DraftGeomUtils, os
from EM_Globals import makeSegShape
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

def makeFHSegment(baseobj=None,nodeStart=None,nodeEnd=None,width=None,height=None,name='FHSegment'):
    ''' Creates a FastHenry segment ('E' statement in FastHenry)
    
        'baseobj' is the line object on which the node is based.
            If no 'baseobj' is given, the user must provide the
            'nodeStart' and 'nodeEnd' parameters.
        'nodeStart' is the segment starting node FHNode object
        'nodeEnd' is the segment ending node FHNode object
        'width' is the segment width
        'height' is the segment height
        'name' is the name of the object
     
    Example:
        segment = makeFHSegment(nodeStart=App.ActiveDocument.FHNode002,nodeEnd=App.ActiveDocument.FHNode003)
'''
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    # this adds the relevant properties to the object 
    #'obj' (e.g. 'Base' property) making it a _FHSegment 
    _FHSegment(obj)
    # manage ViewProvider object
    if FreeCAD.GuiUp:
        _ViewProviderFHSegment(obj.ViewObject)
        # set base ViewObject properties to user-selected values (if any)
    # check if 'nodeStart' is a FHNode, and if so, assign it as segment start node
    if nodeStart is not None:
        if Draft.getType(nodeStart) == "FHNode":
            obj.NodeStart = nodeStart
    # check if 'nodeEnd' is a FHNode, and if so, assign it as segment end node
    if nodeEnd is not None:
        if Draft.getType(nodeEnd) == "FHNode":
            obj.NodeEnd = nodeEnd            
    # check if 'baseobj' is a wire (only base object allowed), and only if not passed any node
    if (baseobj is not None) and (obj.NodeStart is None and obj.NodeEnd is None):
        if Draft.getType(baseobj) == "Wire":
            if len(baseobj.Shape.Vertexes) == 2:
                import EM_FHNode
                obj.Base = baseobj
                obj.NodeStart = EM_FHNode.makeFHNode(X=obj.Base.Start.x, Y=obj.Base.Start.y, Z=obj.Base.Start.z)
                obj.NodeEnd = EM_FHNode.makeFHNode(X=obj.Base.End.x, Y=obj.Base.End.y, Z=obj.Base.End.z)
            else:
                FreeCAD.Console.PrintWarning(translate("EM","FHSegments can only be based on Line objects (not multi-segment wires)"))
        else:
            FreeCAD.Console.PrintWarning(translate("EM","FHSegments can only be based on Line objects"))
    if width:
        obj.Width = float(width)            
    if height:
        obj.Height = float(height)            
    # hide the base object
    if obj.Base and FreeCAD.GuiUp:
        obj.Base.ViewObject.hide()
    # return the newly created Python object
    return obj

class _FHSegment:
    '''The EM FastHenry Segment object'''
    def __init__(self, obj):
        ''' Add properties '''
        obj.addProperty("App::PropertyLink", "Base", "EM", QT_TRANSLATE_NOOP("App::Property","The base object this component is built upon"))
        obj.addProperty("App::PropertyLink","NodeStart","EM",QT_TRANSLATE_NOOP("App::Property","Starting FHNode"))
        obj.addProperty("App::PropertyLink","NodeEnd","EM",QT_TRANSLATE_NOOP("App::Property","Ending FHNode"))
        obj.addProperty("App::PropertyLength","Width","EM",QT_TRANSLATE_NOOP("App::Property","Segment width ('w' segment parameter)"))
        obj.addProperty("App::PropertyLength","Height","EM",QT_TRANSLATE_NOOP("App::Property","Segment height ('h' segment parameter)"))
        obj.addProperty("App::PropertyFloat","Sigma","EM",QT_TRANSLATE_NOOP("App::Property","Segment conductivity ('sigma' segment parameter)"))
        obj.addProperty("App::PropertyVector","ww","EM",QT_TRANSLATE_NOOP("App::Property","Segment cross-section direction along width ('wx', 'wy', 'wz' segment parameter)"))
        obj.addProperty("App::PropertyInteger","nhinc","EM",QT_TRANSLATE_NOOP("App::Property","Number of filaments in the height direction ('nhinc' segment parameter)"))
        obj.addProperty("App::PropertyInteger","nwinc","EM",QT_TRANSLATE_NOOP("App::Property","Number of filaments in the width direction ('nwinc' segment parameter)"))
        obj.addProperty("App::PropertyInteger","rh","EM",QT_TRANSLATE_NOOP("App::Property","Ratio of adjacent filaments in the height direction ('rh' segment parameter)"))
        obj.addProperty("App::PropertyInteger","rw","EM",QT_TRANSLATE_NOOP("App::Property","Ratio of adjacent filaments in the width direction ('rw' segment parameter)"))
        obj.Proxy = self
        self.Type = "FHSegment"
        # save the object in the class, to store or retrieve specific data from it
        # from within the class
        self.Object = obj

    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute() 
    '''
        #FreeCAD.Console.PrintWarning("_FHSegment execute()\n") #debug
        if obj.NodeStart == None:
            return
        elif Draft.getType(obj.NodeStart) != "FHNode":
            FreeCAD.Console.PrintWarning(translate("EM","NodeStart is not a FHNode"))
            return
        if obj.NodeEnd == None:
            return
        elif Draft.getType(obj.NodeEnd) != "FHNode":
            FreeCAD.Console.PrintWarning(translate("EM","NodeEnd is not a FHNode"))
            return
        # the FHSegment has no Placement in itself:
        # 1) either it has the same placement of the Base object
        #    (FHSegment will track the Base object, if present)
        #     However, since the Base object is a Draft::Wire, the 'Start' and 'End' points
        #     are in absolute coordinates. 
        # 2) or it has a position defined by the endpoint nodes
        # So let's keep the FHSegment placement at zero, and use the FHNodes to move the segment position.
        # This is also necessary as we should not change the segment cross-section orientation
        # using the Placement, otherwise it will not be relative to the global axis system
        if obj.Placement != FreeCAD.Placement():
            obj.Placement = FreeCAD.Placement()
        # check if we have a 'Base' object; if so, if segment end nodes
        # were already defined, re-set them according to the 'Base' object;
        # this means that the user cannot move freely the end nodes, if
        # there is a base object
        if obj.Base:
            # if right type of base
            if obj.Base.isDerivedFrom("Part::Feature"):
                # check validity
                if obj.Base.Shape.isNull():
                    return
                if not obj.Base.Shape.isValid():
                    return
                # ok, it's valid. Let's verify if this is a Wire.
                if Draft.getType(obj.Base) == "Wire":
                    if obj.NodeStart != None:
                        abs_pos = obj.NodeStart.Proxy.getAbsCoord()
                        # 'obj.Base.Start' is an absolute position
                        # if 'NodeStart' is not in that position, move it
                        if (abs_pos-obj.Base.Start).Length > EMFHSEGMENT_LENTOL:
                            obj.NodeStart.Proxy.setAbsCoord(obj.Base.Start)
                    if obj.NodeEnd != None:
                        abs_pos = obj.NodeEnd.Proxy.getAbsCoord()
                        # 'obj.Base.Start' is an absolute position
                        # if 'NodeStart' is not in that position, move it
                        if (abs_pos-obj.Base.End).Length > EMFHSEGMENT_LENTOL:
                            obj.NodeEnd.Proxy.setAbsCoord(obj.Base.End)
        if obj.Width == None or obj.Width <= 0:
            obj.Width = EMFHSEGMENT_DEF_SEGWIDTH
        if obj.Height == None or obj.Height <= 0:
            obj.Height = EMFHSEGMENT_DEF_SEGHEIGHT
        # and finally, if everything is ok, make and assign the shape
        self.assignShape(obj)    
        #FreeCAD.Console.PrintWarning("_FHSegment execute() ends\n") #debug

    def assignShape(self, obj):
        ''' Compute and assign the shape to the object 'obj' '''
        n1 = obj.NodeStart.Proxy.getAbsCoord()
        n2 = obj.NodeEnd.Proxy.getAbsCoord()
        shape = makeSegShape(n1,n2,obj.Width,obj.Height,obj.ww)
        # shape may be None, e.g. if endpoints coincide. Do not assign in this case
        if shape:
            obj.Shape = shape
    
    def onChanged(self, obj, prop):
        ''' take action if an object property 'prop' changed
    '''
        #FreeCAD.Console.PrintWarning("_FHSegment onChanged(" + str(prop)+")\n") #debug
        if not hasattr(self,"Object"):
            # on restore, self.Object is not there anymore (JSON does not serialize complex objects
            # members of the class, so __getstate__() and __setstate__() skip them);
            # so we must "re-attach" (re-create) the 'self.Object'
            self.Object = obj
        #FreeCAD.Console.PrintWarning("_FHSegment onChanged(" + str(prop)+") ends\n") #debug
            
    def serialize(self,fid):
        ''' Serialize the object to the 'fid' file descriptor
    '''
        fid.write("E" + self.Object.Label + " N" + self.Object.NodeStart.Label + " N" + self.Object.NodeEnd.Label)
        fid.write(" w=" + str(self.Object.Width.Value) + " h=" + str(self.Object.Height.Value))
        if self.Object.Sigma > 0:
            fid.write(" sigma=" + str(self.Object.Sigma))
        if self.Object.ww.Length >= EMFHSEGMENT_LENTOL:
            fid.write(" wx=" + str(self.Object.ww.x) + " wy=" + str(self.Object.ww.y) + " wz=" + str(self.Object.ww.z))
        if self.Object.nhinc > 0:
            fid.write(" nhinc=" + str(self.Object.nhinc))
        if self.Object.nwinc > 0:
            fid.write(" nwinc=" + str(self.Object.nwinc))
        if self.Object.rh > 0:
            fid.write(" rh=" + str(self.Object.rh))
        if self.Object.rw > 0:
            fid.write(" rw=" + str(self.Object.rw))
        fid.write("\n")

    def __getstate__(self):
        return self.Type

    def __setstate__(self,state):
        if state:
            self.Type = state
  
class _ViewProviderFHSegment:
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
            if hasattr(self.Object,"NodeStart"):
                c.append(self.Object.NodeStart)
            if hasattr(self.Object,"NodeEnd"):
                c.append(self.Object.NodeEnd)
        return c

    def getIcon(self):
        ''' Return the icon which will appear in the tree view. This method is optional
        and if not defined a default icon is shown.
        '''
        return os.path.join(iconPath, 'EM_FHSegment.svg')

    def __getstate__(self):
        return None

    def __setstate__(self,state):
        return None

class _CommandFHSegment:
    ''' The EM FastHenry Segment (FHSegment) command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'EM_FHSegment.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_FHSegment","FHSegment"),
                'Accel': "E, S",
                'ToolTip': QT_TRANSLATE_NOOP("EM_FHSegment","Creates a FastHenry Segment object from scratch, from a selected base object (wire), or from two FHNodes")}
                
    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        # preferences
        #p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/EM")
        #self.Width = p.GetFloat("Width",200)
        # get the selected object(s)
        selection = FreeCADGui.Selection.getSelectionEx()
        done = False
        startNode = None
        endNode = None
        # if selection is not empty
        for selobj in selection:
            # automatic mode
            if Draft.getType(selobj.Object) == "Wire":
                FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FHSegment"))
                FreeCADGui.addModule("EM")
                FreeCADGui.doCommand('obj=EM.makeFHSegment(FreeCAD.ActiveDocument.'+selobj.Object.Name+')')
                # autogrouping, for later on
                #FreeCADGui.addModule("Draft")
                #FreeCADGui.doCommand("Draft.autogroup(obj)")
                FreeCAD.ActiveDocument.commitTransaction()
                FreeCAD.ActiveDocument.recompute()
                done = True
            if Draft.getType(selobj.Object) == "FHNode":
                if startNode == None:
                    startNode = selobj.Object
                elif endNode == None:
                    endNode = selobj.Object
                else:
                    FreeCAD.Console.PrintWarning(translate("EM","More than two FHNodes selected when creating a FHSegment. Using only the first two."))
        if startNode != None and endNode != None:
            FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FHSegment"))
            FreeCADGui.addModule("EM")
            FreeCADGui.doCommand('obj=EM.makeFHSegment(nodeStart=FreeCAD.ActiveDocument.'+startNode.Name+',nodeEnd=FreeCAD.ActiveDocument.'+endNode.Name+')')
            # autogrouping, for later on
            #FreeCADGui.addModule("Draft")
            #FreeCADGui.doCommand("Draft.autogroup(obj)")
            FreeCAD.ActiveDocument.commitTransaction()
            FreeCAD.ActiveDocument.recompute()
            done = True
        # if no selection, or nothing good in the selected objects
        if not done:
            FreeCAD.DraftWorkingPlane.setup()
            # get two 3D point via Snapper, setting the callback functions
            self.points = []
            FreeCADGui.Snapper.getPoint(callback=self.getPoint)

    def getPoint(self,point=None,obj=None):
        "this function is called by the snapper when it has a 3D point"
        if point == None:
            return
        self.points.append(point)
        if len(self.points) == 1:
            # get the second point
            FreeCADGui.Snapper.getPoint(last=self.points[0],callback=self.getPoint,movecallback=self.move)
        elif len(self.points) >= 2:
            coord1 = self.points[0]
            coord2 = self.points[1]
            FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FHNode"))
            FreeCADGui.addModule("EM")
            FreeCADGui.doCommand('import Draft')
            FreeCADGui.doCommand('from FreeCAD import Vector')
            FreeCADGui.doCommand('node1 = EM.makeFHNode(X='+str(coord1.x)+',Y='+str(coord1.y)+',Z='+str(coord1.z)+')')
            FreeCADGui.doCommand('node2 = EM.makeFHNode(X='+str(coord2.x)+',Y='+str(coord2.y)+',Z='+str(coord2.z)+')')
            FreeCADGui.doCommand('obj=EM.makeFHSegment(nodeStart=node1,nodeEnd=node2)')
            FreeCAD.ActiveDocument.commitTransaction()
            FreeCAD.ActiveDocument.recompute()
            # might improve in the future with continue command
            #if self.continueCmd:
            #    self.Activated()

    # this is used to display the global point position information
    # in the Snapper user interface. By default it would display the relative
    # point position on the DraftWorkingPlane (see DraftSnap.py, move() member).
    # This would be different from the behavior of Draft.Point command.
    def move(self,point=None,snapInfo=None):
        if FreeCADGui.Snapper.ui:
            FreeCADGui.Snapper.ui.displayPoint(point)
            
if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_FHSegment',_CommandFHSegment())

