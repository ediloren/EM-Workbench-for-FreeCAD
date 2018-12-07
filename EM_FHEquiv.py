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



__title__="FreeCAD E.M. Workbench FastHenry node Equivalence Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
#
# tolerance in distance between nodes to define a port
EMFHEQUIV_LENTOL = 1e-12

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

def makeFHEquiv(node1=None,node2=None,name='FHEquiv'):
    ''' Creates a FastHenry node equivalence ('.equiv' statement in FastHenry)
    
        'node1' is the first node to shortcut
        'node2' is the second node to shortcut
        
    Example:
    TBD
'''
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    # this adds the relevant properties to the object 
    #'obj' (e.g. 'Base' property) making it a _FHEquiv 
    _FHEquiv(obj)
    # manage ViewProvider object
    if FreeCAD.GuiUp:
        _ViewProviderFHEquiv(obj.ViewObject)
        # set base ViewObject properties to user-selected values (if any)
    # check if 'nodeStart' is a FHNode, and if so, assign it as first node
    if node1:
        if Draft.getType(node2) == "FHNode":
            obj.Node1 = node1
    # check if 'nodeEnd' is a FHNode, and if so, assign it as second node
    if node2:
        if Draft.getType(node2) == "FHNode":
            obj.Node2 = node2            
    # return the newly created Python object
    return obj

class _FHEquiv:
    '''The EM FastHenry node Equivalence object'''
    def __init__(self, obj):
        ''' Add properties '''
        obj.addProperty("App::PropertyLink","Node1","EM",QT_TRANSLATE_NOOP("App::Property","First FHNode to shortcut"))
        obj.addProperty("App::PropertyLink","Node2","EM",QT_TRANSLATE_NOOP("App::Property","Second FHNode to shortcut"))
        obj.Proxy = self
        self.Type = "FHEquiv"
        # save the object in the class, to store or retrieve specific data from it
        # from within the class
        self.Object = obj

    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute() 
    '''
        if obj.Node1 == None:
            return
        elif Draft.getType(obj.Node1) <> "FHNode":
            FreeCAD.Console.PrintWarning(translate("EM","Node1 is not a FHNode"))
            return
        if obj.Node2 == None:
            return
        elif Draft.getType(obj.Node2) <> "FHNode":
            FreeCAD.Console.PrintWarning(translate("EM","Node2 is not a FHNode"))
            return      
        # and finally, if everything is ok, make and assign the shape
        self.assignShape(obj)    

    def assignShape(self, obj):
        ''' Compute and assign the shape to the object 'obj' '''
        n1 = obj.Node1.Proxy.getAbsCoord()
        n2 = obj.Node1.Proxy.getAbsCoord()
        shape = self.makeEquivShape(n1,n2)
        # shape may be None, e.g. if endpoints coincide. Do not assign in this case.
        # FHEquiv is still valid, but not visible.
        if shape:
            obj.Shape = shape

    def makeEquivShape(self,n1,n2):
        ''' Compute a node equivalence shape given:

            'n1': start node position (Vector)
            'n2': end node position (Vector)
    '''
        # do not accept coincident nodes
        if (n2-n1).Length < EMFHEQUIV_LENTOL:
            return None
        line = Part.makeLine(n1, n2)
        return line   
    
    def onChanged(self, obj, prop):
        ''' take action if an object property 'prop' changed
    '''
        #FreeCAD.Console.PrintWarning("\n_FHEquiv onChanged(" + str(prop)+")\n") #debug
        if not hasattr(self,"Object"):
            # on restore, self.Object is not there anymore (JSON does not serialize complex objects
            # members of the class, so __getstate__() and __setstate__() skip them);
            # so we must "re-attach" (re-create) the 'self.Object'
            self.Object = obj
            
    def serialize(self,fid):
        ''' Serialize the object to the 'fid' file descriptor
    '''
        fid.write(".equiv N" + self.Object.Node1.Label + " N" + self.Object.Node2.Label + "\n")

    def __getstate__(self):
        return self.Type

    def __setstate__(self,state):
        if state:
            self.Type = state

class _ViewProviderFHEquiv:
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
            if hasattr(self.Object,"Node1"):
                c.append(self.Object.Node1)
            if hasattr(self.Object,"Node2"):
                c.append(self.Object.Node2)
        return c

    def getIcon(self):
        ''' Return the icon in XMP format which will appear in the tree view. This method is optional
        and if not defined a default icon is shown.
        '''
        return os.path.join(iconPath, 'equiv_icon.svg')

    def __getstate__(self):
        return None

    def __setstate__(self,state):
        return None
        
class _CommandFHEquiv:
    ''' The EM FastHenry equivalent node (FHEquiv) command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'equiv_icon.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_FHEquiv","FHEquiv"),
                'Accel': "E, E",
                'ToolTip': QT_TRANSLATE_NOOP("EM_FHEquiv","Creates a FastHenry equivalent node object from two FHNodes")}
                
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
        nodes = []
        # if selection is not empty
        for selobj in selection:
            if Draft.getType(selobj.Object) == "FHNode":
                nodes.append(selobj.Object)                    
        if len(nodes) <= 1:
            FreeCAD.Console.PrintWarning(translate("EM","Less than FHNodes selected when creating a FHEquiv. Nothing created."))
        else:
            FreeCAD.ActiveDocument.openTransaction(translate("EM","Create FHEquiv"))
            FreeCADGui.addModule("EM")
            for node_num in range(len(nodes)-1):
                FreeCADGui.doCommand('obj=EM.makeFHEquiv(node1=FreeCAD.ActiveDocument.'+nodes[node_num].Name+',node2=FreeCAD.ActiveDocument.'+nodes[node_num+1].Name+')')
            # autogrouping, for later on
            #FreeCADGui.addModule("Draft")
            #FreeCADGui.doCommand("Draft.autogroup(obj)")
            FreeCAD.ActiveDocument.commitTransaction()
            FreeCAD.ActiveDocument.recompute()

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_FHEquiv',_CommandFHEquiv())
