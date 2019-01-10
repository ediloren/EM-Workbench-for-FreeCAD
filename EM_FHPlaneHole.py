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


__title__="FreeCAD E.M. Workbench FastHenry Plane Hole Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
#
# default node color
EMFHPLANEHOLE_TYPES = ["Point", "Rect", "Circle"]
EMFHPLANEHOLE_DEFTYPE = "Point" 

import FreeCAD, FreeCADGui, Mesh, Part, MeshPart, Draft, DraftGeomUtils, os
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

def makeFHPlaneHole(baseobj=None,X=0.0,Y=0.0,Z=0.0,holetype=None,length=None,width=None,radius=None,name='FHPlaneHole'):
    ''' Creates a FastHenry conductive plane hole (within a uniform plane 'G' statement in FastHenry)
    
        'baseobj' is the point object whose position is used as base for the FNNode.
            It has priority over X,Y,Z.
            If no 'baseobj' is given, X,Y,Z are used as coordinates
        'X' x coordinate of the hole, in absolute coordinate system
        'Y' y coordinate of the hole, in absolute coordinate system
        'Z' z coordinate of the hole, in absolute coordinate system
        'holetype' is the type of hole. Allowed values are:
            "Point", "Rect", "Circle"
        'length' is the length of the hole (along the x dimension),
            in case of rectangular "Rect" hole
        'width' the width of the hole (along the y dimension),
            in case of rectangular "Rect" hole
        'radius' is the radius of the hole, in case of circular "Circle" hole
        'name' is the name of the object
    
        The FHPlaneHole has to be used only within a FHPlane object. The FHPlaneHole
        will be taken as child by the FHPlane.
    
    Example:
        hole = makeFHPlaneHole(X=1.0,Y=1.0,Z=0.0,holetype="Rect",length=1.0,width=2.0)
'''
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    # this adds the relevant properties to the object 
    #'obj' (e.g. 'Base' property) making it a _FHNode 
    _FHPlaneHole(obj)
    # manage ViewProvider object
    if FreeCAD.GuiUp:
        _ViewProviderFHPlaneHole(obj.ViewObject)
        # set base ViewObject properties to user-selected values (if any)
    # check if 'baseobj' is a point (only base object allowed)
    if baseobj:
        if Draft.getType(baseobj) == "Point":
            # get the absolute coordinates of the Point
            X = baseobj.Shape.Point.x
            Y = baseobj.Shape.Point.y
            Z = baseobj.Shape.Point.z
        else:
            FreeCAD.Console.PrintWarning(translate("EM","FHPlaneHole can only take the position from Point objects"))
    if holetype:
        if holetype in EMFHPLANEHOLE_TYPES:
            obj.Type = holetype
        else:
            FreeCAD.Console.PrintWarning(translate("EM","FHPlaneHole unknown hole type"))
    else:
        obj.Type = EMFHPLANEHOLE_DEFTYPE
    if length:
        # using a conversion and not catching errors, for input validation
        obj.Length = float(length)
    if width:
        # using a conversion and not catching errors, for input validation
        obj.Width = float(width)
    if radius:
        # using a conversion and not catching errors, for input validation
        obj.Radius = float(radius)
    # set the hole reference point coordinates
    obj.Proxy.setAbsCoord(Vector(X,Y,Z))
    # force recompute to show the Python object
    FreeCAD.ActiveDocument.recompute()
    # return the newly created Python object
    return obj

class _FHPlaneHole:
    '''The EM FastHenry plane hole object'''
    def __init__(self, obj):
        ''' Add properties '''
        obj.addProperty("App::PropertyDistance","X","EM",QT_TRANSLATE_NOOP("App::Property","X Location"))
        obj.addProperty("App::PropertyDistance","Y","EM",QT_TRANSLATE_NOOP("App::Property","Y Location"))
        obj.addProperty("App::PropertyDistance","Z","EM",QT_TRANSLATE_NOOP("App::Property","Z Location"))
        obj.addProperty("App::PropertyLength","Length","EM",QT_TRANSLATE_NOOP("App::Property","Rectangular hole length (along x from node base point)"))
        obj.addProperty("App::PropertyLength","Width","EM",QT_TRANSLATE_NOOP("App::Property","Rectangular hole width (along y from node base point)"))
        obj.addProperty("App::PropertyLength","Radius","EM",QT_TRANSLATE_NOOP("App::Property","Circular hole radius"))
        obj.addProperty("App::PropertyEnumeration","Type","EM",QT_TRANSLATE_NOOP("App::Property","The type of FastHenry plane hole"))
        obj.Proxy = self
        self.Type = "FHPlaneHole"
        # save the object in the class, to store or retrieve specific data from it
        # from within the class
        self.Object = obj
        obj.Type = EMFHPLANEHOLE_TYPES
        
    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute() 
'''
        # create a shape corresponding to the type of hole
        shape = None
        if obj.Type == "Point":
            # set the shape as a Vertex at relative position obj.X, obj.Y, obj.Z
            # The shape will then be adjusted according to the object Placement
            ver = FreeCAD.Version()
            # need to work-around a pesky bug in FreeCAD 0.17(.13541 at the time of writing)
            # that impacts the save/reload when there is a shape with a single Vertex.
            # In this case, the .brep file inside the .FCStd file does NOT contain any
            # placement information. So the object Placement is restored from the
            # Document.xml but then it is overwritten by the Shape placement that
            # is then zero. This bug is not affecting FreeCAD version 0.18(.15593 at the time of writing).
            # As the shape is anyway recreated at recompute() time, the following w/a is valid
            # also between 0.17 and 0.18.
            if (int(ver[0])>0) or (int(ver[0])==0 and int(ver[1])>17):
                shape = Part.Vertex(self.getRelCoord())
            else:
                shape1 = Part.Vertex(self.getRelCoord())
                shape = Part.makeCompound([shape1])
        elif obj.Type == "Rect":
            if obj.Length <= 0 or obj.Width <= 0:
                FreeCAD.Console.PrintWarning(translate("EM","Cannot create a FHPlaneHole rectangular hole with zero length or width"))
            else:
                v0 = self.getRelCoord()
                v1 = v0 + Vector(obj.Length,0,0)
                v2 = v0 + Vector(obj.Length,obj.Width,0)
                v3 = v0 + Vector(0,obj.Width,0)
                # and create the rectangle
                poly = Part.makePolygon( [v0,v1,v2,v3,v0])
                shape = Part.Face(poly)
        elif obj.Type == "Circle":
            if obj.Radius <= 0:
                FreeCAD.Console.PrintWarning(translate("EM","Cannot create a FHPlaneHole circular hole with zero radius"))
            else:
                # create a circle in the x,y plane (axis is along z)
                circle = Part.Circle(self.getRelCoord(),Vector(0,0,1),obj.Radius)
                edge = circle.toShape()
                wire = Part.Wire(edge)
                shape = Part.Face(wire)
        if shape:
            obj.Shape = shape
        
    def onChanged(self, obj, prop):
        ''' take action if an object property 'prop' changed
'''
        #FreeCAD.Console.PrintWarning("\n_FHPlaneHole onChanged(" + str(prop)+")\n") #debug
        if not hasattr(self,"Object"):
            # on restore, self.Object is not there anymore (JSON does not serialize complex objects
            # members of the class, so __getstate__() and __setstate__() skip them);
            # so we must "re-attach" (re-create) the 'self.Object'
            self.Object = obj
        
    def serialize(self,fid):
        ''' Serialize the object to the 'fid' file descriptor
'''
        pos = self.getAbsCoord()
        if self.Object.Type == "Point":
            # hole point (x,y,z)
            fid.write("+         hole point (" + str(pos.x) + "," + str(pos.y) + "," + str(pos.z) + ")")
        elif self.Object.Type == "Rect":
            # calculate the position of the second point defining the rectangle
            #
            # if the hole is on a plane, its placement corresponds to the FHPlane placement
            # (it is assigned by the FHPlane, when it takes the FHPlaneHole as child)
            placement = self.Object.Placement
            planeOrigin = placement.Base
            # plane versors. 'vx' is along length, 'vy' is along width
            vx = (placement.multVec(Vector(1,0,0))-planeOrigin).normalize()
            vy = (placement.multVec(Vector(0,1,0))-planeOrigin).normalize()
            # compute the opposite corner position
            point2 = pos + vx*self.Object.Length.Value + vy*self.Object.Width.Value
            # hole rect (x1,y1,z1,x2,y2,z2)
            fid.write("+         hole rect (" + str(pos.x) + "," + str(pos.y) + "," + str(pos.z) + ",")
            fid.write(str(point2.x) + "," + str(point2.y) + "," + str(point2.z) + ")\n")
        elif self.Object.Type == "Circle":                    
            # hole circle (x,y,z,r)
            fid.write("+         hole circle (" + str(pos.x) + "," + str(pos.y) + "," + str(pos.z) + "," + str(self.Object.Radius.Value) + ")")
        fid.write("\n")

    def getAbsCoord(self):
        ''' Get a FreeCAD.Vector containing the reference point coordinates 
            in the absolute reference system
'''
        return self.Object.Placement.multVec(Vector(self.Object.X, self.Object.Y, self.Object.Z))

    def getRelCoord(self):
        ''' Get a FreeCAD.Vector containing the hole coordinates relative to the FHPlaneHole Placement
        
        These coordinates correspond to (self.Object.X, self.Object.Y, self.Object.Z),
        that are the same as self.Object.Placement.inverse().multVec(reference_point_pos))
'''
        return Vector(self.Object.X,self.Object.Y,self.Object.Z)

    def setRelCoord(self,rel_coord,placement=None):
        ''' Sets the hole position relative to the placement
        
        'rel_coord': FreeCAD.Vector containing the hole coordinates relative to the FHPlaneHole Placement
        'placement': a new FHPlaneHole placement. If 'None', the placement is not changed
        
        Remark: the function will not recalculate() the object (i.e. change of position is not visible
        just by calling this function)
'''
        if placement:
            # validation of the parameter
            if isinstance(placement, FreeCAD.Placement):
                self.Object.Placement = placement
        self.Object.X = rel_coord.x
        self.Object.Y = rel_coord.y
        self.Object.Z = rel_coord.z

    def setAbsCoord(self,abs_coord,placement=None):
        ''' Sets the absolute reference point position, considering the object placement, and in case forcing a new placement
        
        'abs_coord': FreeCAD.Vector containing the hole coordinates in the absolute reference system
        'placement': a new placement. If 'None', the placement is not changed

        Remark: the function will not recalculate() the object (i.e. change of position is not visible
        just by calling this function)
'''
        if placement:
            # validation of the parameter
            if isinstance(placement, FreeCAD.Placement):
                self.Object.Placement = placement
        rel_coord = self.Object.Placement.inverse().multVec(abs_coord)
        self.Object.X = rel_coord.x
        self.Object.Y = rel_coord.y
        self.Object.Z = rel_coord.z

    def __getstate__(self):
        return self.Type

    def __setstate__(self,state):
        if state:
            self.Type = state
                  
class _ViewProviderFHPlaneHole:
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

    def getIcon(self):
        ''' Return the icon which will appear in the tree view. This method is optional
        and if not defined a default icon is shown.
        '''
        return os.path.join(iconPath, 'EM_FHPlaneHole.svg')

    def __getstate__(self):
        return None

    def __setstate__(self,state):
        return None

class _CommandFHPlaneHole:
    ''' The EM FastHenry conductive plane hole (FHPlaneHole) command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'EM_FHPlaneHole.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_FHPlaneHole","FHPlaneHole"),
                'Accel': "E, H",
                'ToolTip': QT_TRANSLATE_NOOP("EM_FHPlaneHole","Creates a FastHenry conductive plane Hole object from scratch or from a selected object (point)")}
                
    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        # get the selected object(s)
        sel = FreeCADGui.Selection.getSelectionEx()
        done = False
        # if selection is not empty
        if sel:
            # automatic mode
            import Draft
            if Draft.getType(sel[0].Object) == "Point":
                FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FHPlaneHole"))
                FreeCADGui.addModule("EM")
                for selobj in sel:
                    if Draft.getType(selobj) == "Point":
                        FreeCADGui.doCommand('obj=EM.makeFHPlaneHole(FreeCAD.ActiveDocument.'+selobj.Object.Name+')')
                # autogrouping, for later on
                #FreeCADGui.addModule("Draft")
                #FreeCADGui.doCommand("Draft.autogroup(obj)")
                FreeCAD.ActiveDocument.commitTransaction()
                FreeCAD.ActiveDocument.recompute()
                done = True
        # if no selection, or nothing good in the selected objects
        if not done:
            FreeCAD.DraftWorkingPlane.setup()
            # get a 3D point via Snapper, setting the callback functions
            FreeCADGui.Snapper.getPoint(callback=self.getPoint)

    def getPoint(self,point=None,obj=None):
        '''This function is called by the Snapper when it has a 3D point'''
        if point == None:
            return
        coord = FreeCAD.DraftWorkingPlane.getLocalCoords(point)
        FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FHPlaneHole"))
        FreeCADGui.addModule("EM")
        FreeCADGui.doCommand('obj=EM.makeFHPlaneHole(X='+str(coord.x)+',Y='+str(coord.y)+',Z='+str(coord.z)+')')
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
    FreeCADGui.addCommand('EM_FHPlaneHole',_CommandFHPlaneHole())

