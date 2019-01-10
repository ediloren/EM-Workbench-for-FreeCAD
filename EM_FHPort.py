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

__title__="FreeCAD E.M. Workbench FastHenry Port Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
#
# tolerance in distance between nodes to define a port
EMFHPORT_LENTOL = 1e-12

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

def makeFHPort(nodePos=None,nodeNeg=None,name='FHPort'):
    ''' Creates a FastHenry port ('.external' statement in FastHenry)
    
        'nodePos' is the positive node FHNode object
        'nodeNeg' is the negative node FHNode object
        'name' is the name of the object
        
    Example:
        port = makeFHPort(App.ActiveDocument.FHNode,App.ActiveDocument.FHNode001)
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
    # check if 'nodePos' is a FHNode, and if so, assign it as port start (positive) node
    if nodePos:
        if Draft.getType(nodePos) == "FHNode":
            obj.NodePos = nodePos
    # check if 'nodeNeg' is a FHNode, and if so, assign it as port end (negative) node
    if nodeNeg:
        if Draft.getType(nodeNeg) == "FHNode":
            obj.NodeNeg = nodeNeg            
    # return the newly created Python object
    return obj

class _FHPort:
    '''The EM FastHenry Port object'''
    def __init__(self, obj):
        ''' Add properties '''
        obj.addProperty("App::PropertyLink","NodePos","EM",QT_TRANSLATE_NOOP("App::Property","Positive FHNode"))
        obj.addProperty("App::PropertyLink","NodeNeg","EM",QT_TRANSLATE_NOOP("App::Property","Negative FHNode"))
        obj.Proxy = self
        self.Type = "FHPort"
        # save the object in the class, to store or retrieve specific data from it
        # from within the class
        self.Object = obj

    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute() 
    '''
        if obj.NodePos == None:
            return
        elif Draft.getType(obj.NodePos) <> "FHNode":
            FreeCAD.Console.PrintWarning(translate("EM","NodePos is not a FHNode"))
            return
        if obj.NodeNeg == None:
            return
        elif Draft.getType(obj.NodeNeg) <> "FHNode":
            FreeCAD.Console.PrintWarning(translate("EM","NodeNeg is not a FHNode"))
            return
        if obj.NodePos == obj.NodeNeg:
            FreeCAD.Console.PrintWarning(translate("EM","NodePos and NodeNeg coincide. Cannot create a port."))
            return            
        # and finally, if everything is ok, make and assign the shape
        self.assignShape(obj)    

    def assignShape(self, obj):
        ''' Compute and assign the shape to the object 'obj' '''
        n1 = obj.NodePos.Proxy.getAbsCoord()
        n2 = obj.NodeNeg.Proxy.getAbsCoord()
        shape = self.makePortShape(n1,n2)
        # shape may be None, e.g. if endpoints coincide. Do not assign in this case.
        # Port is still valid, but not visible.
        if shape:
            obj.Shape = shape

    def makePortShape(self,n1,n2):
        ''' Compute a port shape given:

            'n1': start node position (FreeCAD.Vector)
            'n2': end node position (FreeCAD.Vector)
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
        #FreeCAD.Console.PrintWarning("\n_FHPort onChanged(" + str(prop)+")\n") #debug
        if not hasattr(self,"Object"):
            # on restore, self.Object is not there anymore (JSON does not serialize complex objects
            # members of the class, so __getstate__() and __setstate__() skip them);
            # so we must "re-attach" (re-create) the 'self.Object'
            self.Object = obj
            
    def serialize(self,fid):
        ''' Serialize the object to the 'fid' file descriptor
    '''
        fid.write(".external N" + self.Object.NodePos.Label + " N" + self.Object.NodeNeg.Label + "\n")

    def __getstate__(self):
        return self.Type

    def __setstate__(self,state):
        if state:
            self.Type = state

class _ViewProviderFHPort:
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
            if hasattr(self.Object,"NodePos"):
                c.append(self.Object.NodePos)
            if hasattr(self.Object,"NodeNeg"):
                c.append(self.Object.NodeNeg)
        return c

    def getIcon(self):
        ''' Return the icon which will appear in the tree view. This method is optional
        and if not defined a default icon is shown.
         '''
        return os.path.join(iconPath, 'EM_FHPort.svg')

    def __getstate__(self):
        return None

    def __setstate__(self,state):
        return None
        
class _CommandFHPort:
    ''' The EM FastHenry Port (FHPort) command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'EM_FHPort.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_FHPort","FHPort"),
                'Accel': "E, P",
                'ToolTip': QT_TRANSLATE_NOOP("EM_FHPort","Creates a FastHenry Port object from two FHNodes")}
                
    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
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
            FreeCADGui.doCommand('obj=EM.makeFHPort(nodePos=FreeCAD.ActiveDocument.'+startNode.Name+',nodeNeg=FreeCAD.ActiveDocument.'+endNode.Name+')')
            # autogrouping, for later on
            #FreeCADGui.addModule("Draft")
            #FreeCADGui.doCommand("Draft.autogroup(obj)")
            FreeCAD.ActiveDocument.commitTransaction()
            FreeCAD.ActiveDocument.recompute()
        else:
            FreeCAD.Console.PrintWarning(translate("EM","Select two FHNodes for creating a FHPort"))

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_FHPort',_CommandFHPort())
