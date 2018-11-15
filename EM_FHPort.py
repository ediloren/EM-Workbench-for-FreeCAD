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


__title__="FreeCAD E.M. Workbench FastHenry Port Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
#
# tolerance in distance between nodes to define a port
EMFHPORT_LENTOL = 1e-12

import FreeCAD, FreeCADGui, Mesh, Part, MeshPart, Draft, DraftGeomUtils, os
import EM
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

def makeFHPort(nodeStart=None,nodeEnd=None,name='FHPort'):
    ''' Creates a FastHenry port ('.external' statement in FastHenry)
    
        'nodeStart' is the positive node
        'nodeEnd' is the negative node
        
    Example:
    TBD
'''
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    # this adds the relevant properties to the object 
    #'obj' (e.g. 'Base' property) making it a _FHPort 
    _FHPort(obj)
    # manage ViewProvider object
    if FreeCAD.GuiUp:
        _ViewProviderFHPort(obj.ViewObject)
        # set base ViewObject properties to user-selected values (if any)
    # check if 'nodeStart' is a FHNode, and if so, assign it as port start (positive) node
    if nodeStart:
        if Draft.getType(nodeStart) == "FHNode":
            obj.NodeStart = nodeStart
    # check if 'nodeEnd' is a FHNode, and if so, assign it as port end (negative) node
    if nodeEnd:
        if Draft.getType(nodeEnd) == "FHNode":
            obj.NodeEnd = nodeEnd            
    # return the newly created Python object
    return obj

class _FHPort:
    '''The EM FastHenry Port object'''
    def __init__(self, obj):
        ''' Add properties '''
        obj.addProperty("App::PropertyLink","NodeStart","EM",QT_TRANSLATE_NOOP("App::Property","Starting FHNode"))
        obj.addProperty("App::PropertyLink","NodeEnd","EM",QT_TRANSLATE_NOOP("App::Property","Ending FHNode"))
        obj.Proxy = self
        self.Type = "FHPort"
        # save the object in the class, to store or retrieve specific data from it
        # from within the class
        self.Object = obj

    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute() 
    '''
        if obj.NodeStart == None:
            return
        elif Draft.getType(obj.NodeStart) <> "FHNode":
            FreeCAD.Console.PrintWarning(translate("EM","NodeStart is not a FHNode"))
            return
        if obj.NodeEnd == None:
            return
        elif Draft.getType(obj.NodeEnd) <> "FHNode":
            FreeCAD.Console.PrintWarning(translate("EM","NodeEnd is not a FHNode"))
            return
        if obj.NodeStart == obj.NodeEnd:
            FreeCAD.Console.PrintWarning(translate("EM","NodeStart and NodeEnd coincide. Cannot create a port."))
            return            
        # and finally, if everything is ok, make and assing the shape
        self.assignShape(obj)    

    def assignShape(self, obj):
        ''' Compute and assign the shape to the object 'obj' '''
        n1 = obj.NodeStart.Shape.Point
        n2 = obj.NodeEnd.Shape.Point
        shape = self.makePortShape(n1,n2)
        # shape may be None, e.g. if endpoints coincide. Do not assign in this case.
        # Port is still valid, but not visible.
        if shape:
            obj.Shape = shape

    def makePortShape(self,n1,n2):
        ''' Compute a port shape given:

            'n1': start node position (Vector)
            'n2': end node position (Vector)
    '''
        # do not accept coincident nodes
        if (n2-n1).Length < EMFHPORT_LENTOL:
            return None
        line = Part.makeLine(n1, n2)
        # calculate arrow head base
        direction = n1 - n2
        length = direction.Length
        base = Vector(direction)
        base.normalize()
        base.multiply(length * 0.8)
        base = n2 + base
        # radius2 is calculated for a fixed arrow head angle tan(15deg)=0.27
        cone = Part.makeCone(0.2 * length * 0.27, 0.0, 0.2 * length, base, direction, 360)
        # add the compound representing the arrow
        arrow = Part.makeCompound([line, cone])
        return arrow   
    
    def onChanged(self, obj, prop):
        ''' take action if an object property 'prop' changed
    '''
        #FreeCAD.Console.PrintWarning("\n_FHSegment onChanged(" + str(prop)+")\n") #debug
        if not hasattr(self,"Object"):
            # on restore, self.Object is not there anymore
            self.Object = obj
        return
            
    def serialize(self,fid):
        ''' Serialize the object to the 'fid' file descriptor
    '''
        fid.write(".external N" + self.Object.NodeStart.Label + " N" + self.Object.NodeEnd.Label + "\n")
        
class _ViewProviderFHPort:
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
            if hasattr(self.Object,"NodeStart"):
                c.append(self.Object.NodeStart)
            if hasattr(self.Object,"NodeEnd"):
                c.append(self.Object.NodeEnd)
        return c

    def getIcon(self):
        ''' Return the icon in XMP format which will appear in the tree view. This method is optional
        and if not defined a default icon is shown.
        '''
        return os.path.join(iconPath, 'port_icon.svg')

class _CommandFHPort:
    ''' The EM FastHenry Port (FHPort) command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'port_icon.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_FHPort","FHPort"),
                'Accel': "E, P",
                'ToolTip': QT_TRANSLATE_NOOP("EM_FHPort","Creates a FastHenry Port object from two FHNodes")}
                
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
        startNode = None
        endNode = None
        # if selection is not empty
        for selobj in selection:
            if Draft.getType(selobj.Object) == "FHNode":
                if startNode == None:
                    startNode = selobj.Object
                elif endNode == None:
                    endNode = selobj.Object
                else:
                    FreeCAD.Console.PrintWarning(translate("EM","More than two FHNodes selected when creating a FHPort. Using only the first two."))
        if startNode <> None and endNode <> None:
            FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FHPort"))
            FreeCADGui.addModule("EM")
            FreeCADGui.doCommand('obj=EM.makeFHPort(nodeStart=FreeCAD.ActiveDocument.'+startNode.Name+',nodeEnd=FreeCAD.ActiveDocument.'+endNode.Name+')')
            # autogrouping, for later on
            #FreeCADGui.addModule("Draft")
            #FreeCADGui.doCommand("Draft.autogroup(obj)")
            FreeCAD.ActiveDocument.commitTransaction()
            FreeCAD.ActiveDocument.recompute()
        else:
            FreeCAD.Console.PrintWarning(translate("EM","Select two FHNodes for creating a FHPort"))

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_FHPort',_CommandFHPort())
