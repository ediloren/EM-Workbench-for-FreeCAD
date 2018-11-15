#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2018                                                    *  
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

__title__="FreeCAD E.M. Workbench FastHenry Node Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
#
# default node color
EMFHNODE_DEF_NODECOLOR = (1.0,0.0,0.0)
EMFHNODE_DEF_NODESIZE = 10

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

def makeFHNode(baseobj=None,color=None,size=None,name='FHNode'):
    '''Creates a FastHenry node ('N' statement in FastHenry)
    
    'baseobj' is the point object on which the node is based.
        If no 'baseobj' is given, the user must assign a base
        object later on, to be able to use this object.
    
    Example:
    TBD
'''
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    # this adds the relevant properties to the object 
    #'obj' (e.g. 'Base' property) making it a _FHNode 
    _FHNode(obj)
    # manage ViewProvider object
    if FreeCAD.GuiUp:
        _ViewProviderFHNode(obj.ViewObject)
        # set base ViewObject properties to user-selected values (if any)
        if color:
            obj.ViewObject.PointColor = color
        else:
            obj.ViewObject.PointColor = EMFHNODE_DEF_NODECOLOR
        if size:
            obj.ViewObject.PointSize = size
        else:
            obj.ViewObject.PointSize = EMFHNODE_DEF_NODESIZE
    # check if 'baseobj' is a point (only base object allowed)
    if baseobj:
        if Draft.getType(baseobj) == "Point":
            obj.Base = baseobj
        else:
            FreeCAD.Console.PrintWarning(translate("EM","FHNodes can only be based on Point objects"))
    # hide the base object
    if obj.Base and FreeCAD.GuiUp:
        obj.Base.ViewObject.hide()
    # force recompute to show the Python object
    FreeCAD.ActiveDocument.recompute()
    # return the newly created Python object
    return obj

class _FHNode:
    '''The EM FastHenry Node object'''
    def __init__(self, obj):
        ''' Add properties '''
        obj.addProperty("App::PropertyLink", "Base", "EM", QT_TRANSLATE_NOOP("App::Property","The base object this component is built upon"))
        obj.Proxy = self
        self.Type = "FHNode"
        # save the object in the class, to store or retrieve specific data from it
        # from within the class
        self.Object = obj
        
    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute() 
'''
        # check if we have a 'Base' object
        if obj.Base:
            # computing a shape from a base object
            if obj.Base.isDerivedFrom("Part::Feature"):
                # check validity
                if obj.Base.Shape.isNull():
                    return
                if not obj.Base.Shape.isValid():
                    return
                # ok, it's valid. Let's verify if this is a Point.
                if Draft.getType(obj.Base) == "Point":
                    shape = Part.Vertex(obj.Base.Shape)
                    obj.Shape = shape
        
    def onChanged(self, obj, prop):
        ''' take action if an object property 'prop' changed
'''
        #FreeCAD.Console.PrintWarning("\n_FHNode onChanged(" + str(prop)+")\n") #debug
        if not hasattr(self,"Object"):
            # on restore, self.Object is not there anymore
            self.Object = obj
        # if the user changed the base object
        if prop == "Base":
            # check if we have a 'Base' object
            if obj.Base:
                # computing a shape from a base object
                if obj.Base.isDerivedFrom("Part::Feature"):
                    # check validity
                    if obj.Base.Shape.isNull():
                        return
                    if not obj.Base.Shape.isValid():
                        return
                    # ok, it's valid. Let's verify if this is a Point.
                    if Draft.getType(obj.Base) == "Point":
                        shape = Part.Vertex(obj.Base.Shape)
                        obj.Shape = shape

    def serialize(self,fid):
        ''' Serialize the object to the 'fid' file descriptor
'''
        # check if we have a 'Base' object
        if self.Object.Base:
            # ok, it's valid. Let's verify if this is a Point.
            if Draft.getType(self.Object.Base) == "Point":
                fid.write("N" + self.Object.Label)
                fid.write(" x=" + str(self.Object.Base.X.Value) + " y=" + str(self.Object.Base.Y.Value) + " z=" + str(self.Object.Base.Z.Value))
                fid.write("\n")
                
class _ViewProviderFHNode:
    def __init__(self, obj):
        ''' Set this object to the proxy object of the actual view provider '''
        obj.Proxy = self
        self.Object = obj.Object

    def attach(self, obj):
        ''' Setup the scene sub-graph of the view provider, this method is mandatory '''
        return

    def updateData(self, fp, prop):
        ''' Print the name of the property that has changed '''
        #FreeCAD.Console.PrintMessage("ViewProvider updateData(),  property: " + str(prop) + "\n")
        ''' If a property of the handled feature has changed we have the chance to handle this here '''
        return

    def getDefaultDisplayMode(self):
        ''' Return the name of the default display mode. It must be defined in getDisplayModes. '''
        return "Flat Lines"

    def onChanged(self, vp, prop):
        ''' Print the name of the property that has changed '''
        #FreeCAD.Console.PrintMessage("ViewProvider onChanged(), property: " + str(prop) + "\n")

    def claimChildren(self):
        ''' Used to place other objects as childrens in the tree'''
        c = []
        if hasattr(self,"Object"):
            if hasattr(self.Object,"Base"):
                c = [self.Object.Base]
        return c

    def getIcon(self):
        ''' Return the icon in XMP format which will appear in the tree view. This method is optional
        and if not defined a default icon is shown.
        '''
        return os.path.join(iconPath, 'node_icon.svg')

class _CommandFHNode:
    ''' The EM FastHenry Node (FHNode) command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'node_icon.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_FHNode","FHNode"),
                'Accel': "E, N",
                'ToolTip': QT_TRANSLATE_NOOP("EM_FHNode","Creates a FastHenry Node object from scratch or from a selected object (point)")}
                
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
            if Draft.getType(sel[0].Object) != "FHNode":
                FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FHNode"))
                FreeCADGui.addModule("EM")
                for selobj in sel:
                    FreeCADGui.doCommand('obj=EM.makeFHNode(FreeCAD.ActiveDocument.'+selobj.Object.Name+')')
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
        "this function is called by the snapper when it has a 3D point"
        if point == None:
            return
        coord = FreeCAD.DraftWorkingPlane.getLocalCoords(point)
        FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FHNode"))
        FreeCADGui.addModule("EM")
        FreeCADGui.doCommand('import Draft')
        FreeCADGui.doCommand('base=Draft.makePoint('+str(coord.x)+','+str(coord.y)+','+str(coord.z)+')')
        FreeCADGui.doCommand('obj=EM.makeFHNode(base)')
        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()
        # might improve in the future with continue command
        #if self.continueCmd:
        #    self.Activated()

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_FHNode',_CommandFHNode())

