#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2019                                                    *
#*   FastFieldSolvers S.R.L., http://www.fastfieldsolvers.com              *
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


__title__="FreeCAD E.M. Workbench VoxHenry Port Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# default port colors
EMVHPORT_DEF_POSPORTCOLOR = (1.0,0.0,0.0)
EMVHPORT_DEF_NEGPORTCOLOR = (0.0,0.0,0.0)
EMVHPORT_DEF_LINECOLOR = (0.25, 0.25, 0.25)
# displacement percentage fraction of the voxel dimension
EMVHPORT_EPSDELTA = 10.0
# side strings
EMVHPORT_SIDESTRS = ['+x', '-x', '+y', '-y', '+z', '-z']

import FreeCAD, FreeCADGui, Part, Draft, DraftGeomUtils, os
import DraftVecUtils
from FreeCAD import Vector
import time
from pivy import coin
import EM

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtGui
    from DraftTools import translate
    from PySide.QtCore import QT_TRANSLATE_NOOP
else:
    # \cond
    def translate(ctxt,txt):
        return txt
    def QT_TRANSLATE_NOOP(ctxt,txt):
        return txt
    # \endcond

__dir__ = os.path.dirname(__file__)
iconPath = os.path.join( __dir__, 'Resources' )

def makeVHPortFromSel(selection=[]):
    ''' Creates a VoxHenry Port from the selection

        'selection' is a selection object (from getSelectionEx() )
            The selection object must contain at least two faces

    Example:
        port = makeVHPortFromSel(FreeCADGui.Selection.getSelectionEx())
'''
    port = None
    # if selection is not empty
    if len(selection) > 0:
        real_faces = []
        # get all the subobjects of the selection (faces, edges, etc.)
        for selobj in selection:
            if selobj.HasSubObjects:
                # screen out the faces
                for sobj in selobj.SubElementNames:
                    if "Face" in sobj:
                        real_faces.append((selobj.Object, (sobj,)))
                real_faces_len = len(real_faces)
                # need at least two faces to make a port
        if real_faces_len > 1:
            mid = int(real_faces_len / 2)
            port = makeVHPort(real_faces[0:mid],real_faces[mid:real_faces_len])
    if port is None:
       FreeCAD.Console.PrintWarning(translate("EM","No faces selected for the creation of a VHPort (need at least two). Nothing done."))
    return port

def makeVHPort(posFaces=None,negFaces=None,name='VHPort'):
    ''' Creates a VoxHenry Port (a set of two voxelized faces, representing the positive and negative contacts)

        'posFaces' is a list of faces of a 3D solid object that is forming the positive
            contact of the port. If no 'posFace' is given, the user must assign a list
            later on, to be able to use this object.
        'negFaces' is a list of faces of a 3D solid object that is forming the negative
            contact of the port. If no 'negFace' is given, the user must assign a list
            later on, to be able to use this object.
        'name' is the name of the object

    Example:
        port = makeVHPort(myPosFaces, myNegFaces)
'''
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    # this adds the relevant properties to the object
    #'obj' (e.g. 'Base' property) making it a _VHPort
    _VHPort(obj)
    # manage ViewProvider object
    if FreeCAD.GuiUp:
        _ViewProviderVHPort(obj.ViewObject)
        # set base ViewObject properties to user-selected values (if any)
    # check if 'posFaces' contains valid faces
    real_faces = obj.PosFaces
    if posFaces != []:
        # screen out the faces
        for face in posFaces:
            if "Face" in face[1][0]:
                real_faces.append(face)
        # cannot directly append to 'obj.PosFaces' as this is a PropertyLinkSubList object,
        # that automatically detect multiple instances of the same Part::Feature,
        # and merges the sub-object lists (e.g. faces)
        obj.PosFaces = real_faces
    # check if 'negFaces' contains valid faces
    real_faces = obj.NegFaces
    if negFaces != []:
        # screen out the faces
        for face in negFaces:
            if "Face" in face[1][0]:
                real_faces.append(face)
        # cannot directly append to 'obj.PosFaces' as this is a PropertyLinkSubList object,
        # that automatically detect multiple instances of the same Part::Feature,
        # and merges the sub-object lists (e.g. faces)
        obj.NegFaces = real_faces
    # return the newly created Python object
    return obj

class _VHPort:
    '''The EM VoxHenry Port object'''
    def __init__(self, obj):
        # save the object in the class, to store or retrieve specific data from it
        # from within the class
        self.Object = obj
        ''' Add properties '''
        obj.addProperty("App::PropertyLinkSubList", "PosFaces", "EM", QT_TRANSLATE_NOOP("App::Property","The list of faces forming the positive contact of the port"))
        obj.addProperty("App::PropertyLinkSubList", "NegFaces", "EM", QT_TRANSLATE_NOOP("App::Property","The list of faces forming the negative contact of the port"))
        obj.addProperty("App::PropertyBool","ShowVoxels","EM",QT_TRANSLATE_NOOP("App::Property","Show the voxelization"))
        obj.addProperty("App::PropertyInteger","DeltaDist","EM",QT_TRANSLATE_NOOP("App::Property","Distance as percentage of the delta voxel dimension to consider a port face as belonging to a voxel"))
        obj.addProperty("App::PropertyBool","isVoxelized","EM",QT_TRANSLATE_NOOP("App::Property","Flags if the port has been voxelized (read only)"),1)
        obj.addProperty("App::PropertyIntegerList","PosVoxelContacts","EM",QT_TRANSLATE_NOOP("App::Property","Positive Contacts (hidden)"),4)
        obj.addProperty("App::PropertyIntegerList","NegVoxelContacts","EM",QT_TRANSLATE_NOOP("App::Property","Negative Contacts (hidden)"),4)
        obj.ShowVoxels = False
        obj.Proxy = self
        obj.DeltaDist = int(50 + 50/EMVHPORT_EPSDELTA)
        obj.isVoxelized = False
        obj.PosVoxelContacts = []
        obj.NegVoxelContacts = []
        self.posContactShapePoints = []
        self.negContactShapePoints = []
        self.Type = "VHPort"

    def onChanged(self, obj, prop):
        ''' take action if an object property 'prop' changed
    '''
        #FreeCAD.Console.PrintWarning("\n_VHPort onChanged(" + str(prop)+")\n") #debug
        # on restore, some self.Objects are not there anymore (JSON does not serialize complex objects
        # members of the class, so __getstate__() and __setstate__() skip them);
        # so we must "re-attach" (re-create) the 'self.Objects'
        if not hasattr(self,"Object"):
            self.Object = obj
        if prop == "DeltaDist":
            self.flagVoxelizationInvalid()

    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute()
    '''
        #FreeCAD.Console.PrintWarning("_VHPort execute()\n") #debug
        # if no faces were assigned to the port, exit
        if len(obj.PosFaces) == 0 and len(obj.NegFaces) == 0:
            return
        shape = None
        # Check if the user selected to see the voxelization, and if the voxelization exists
        if obj.ShowVoxels == True:
            # get the VHSolver object
            solver = EM.getVHSolver()
            if solver is not None:
                gbbox = solver.Proxy.getGlobalBBox()
                delta = solver.Proxy.getDelta()
                # getting the voxel space may cause the voxelization of this VHConductor to become invalid,
                # if the global bounding box is found to have changed, or VHSolver 'Delta' changed over time, etc.
                voxelSpace = solver.Proxy.getVoxelSpace()
                if obj.isVoxelized == False:
                    FreeCAD.Console.PrintWarning(translate("EM","Cannot fulfill 'ShowVoxels', VHPort objects has not been voxelized, or voxelization is invalid (e.g. change in voxel space dimensions or no voxelized conductor). Voxelize it first.\n"))
                else:
                    self.posContactShapePoints = []
                    posContact = self.createVoxelShellFastCoin(self.posContactShapePoints, obj.PosVoxelContacts,gbbox,delta,voxelSpace)
                    self.negContactShapePoints = []
                    negContact = self.createVoxelShellFastCoin(self.negContactShapePoints, obj.NegVoxelContacts,gbbox,delta,voxelSpace)
                    if posContact and negContact:
                        shape = True
                    else:
                        FreeCAD.Console.PrintWarning(translate("EM","Cannot create VHPort shell, voxelized pos or neg contact shell creation failed"))
        if shape is None:
            # if we don't show the voxelized view of the object, let's show the faces
            self.posContactShapePoints = []
            self.negContactShapePoints = []
            faces = self.getFaces(obj.PosFaces)
            posContact = Part.makeCompound(faces)
            faces = self.getFaces(obj.NegFaces)
            negContact = Part.makeCompound(faces)
            shape = Part.makeCompound([posContact,negContact])
            # and finally assign the shape (but only if we were able to create any)
            obj.Shape = shape
            # force the color, if FreeCAD has a GUI and therefore the object has a ViewObject.
            # must do it from here, as from within the ViewObject we cannot force the reconstruction of the coin3D
            # scenegraph representation, that is using the ShapeColor
            if FreeCAD.GuiUp:
                obj.ViewObject.DiffuseColor = [obj.ViewObject.PosPortColor for x in range(0,len(obj.PosFaces))] + [obj.ViewObject.NegPortColor for x in range(0,len(obj.NegFaces))]
        else:
            # make a dummy empty shape. Representation is through custom coin3d scenegraph.
            obj.Shape = Part.makeShell([])
        #FreeCAD.Console.PrintWarning("_VHPort execute() ends\n") #debug

    def getFaces(self,faceSubObjs):
        ''' Get the face objects from an App::PropertyLinkSubList

            'faceSubObjs' an App::PropertyLinkSubList list of objects and face names. Each element of the list
                has the format (Part::Feature, ('FaceXXX',)) where XXX is the face number.
                The tuple ('FaceXXX',) may also contain multiple face names.

            Returns a list of face objects
    '''
        faces = []
        for obj in faceSubObjs:
            if obj[0].isDerivedFrom("Part::Feature"):
                for sub in obj[1]:
                        if "Face" in sub:
                            fn = int(sub[4:])-1
                            faces.append(obj[0].Shape.Faces[fn])
        return faces


    def createVoxelShell(self,contacts,gbbox,delta,voxelSpace=None):
        ''' Creates a shell composed by the external faces of a voxelized port.

            'contacts' is the list of contacts (see voxelizeContact() for the format)
            'gbbox' (FreeCAD.BoundBox) is the overall bounding box
            'delta' is the voxels size length
            'voxelSpace' (Numpy 3D array) is the voxel tensor of the overall space

            Remark: the VHPort must have already been voxelized
    '''
        if voxelSpace is None:
            return
        # small displacement w.r.t. delta
        epsdelta = delta/EMVHPORT_EPSDELTA
        # vertexes of the six faces (with a slight offset)
        vertexes = [[Vector(delta+epsdelta,0,0), Vector(delta+epsdelta,delta,0), Vector(delta+epsdelta,delta,delta), Vector(delta+epsdelta,0,delta)],
                    [Vector(-epsdelta,0,0), Vector(-epsdelta,0,delta), Vector(-epsdelta,delta,delta), Vector(-epsdelta,delta,0)],
                    [Vector(0,delta+epsdelta,0), Vector(0,delta+epsdelta,delta), Vector(delta,delta+epsdelta,delta), Vector(delta,delta+epsdelta,0)],
                    [Vector(0,-epsdelta,0), Vector(delta,-epsdelta,0), Vector(delta,-epsdelta,delta), Vector(0,-epsdelta,delta)],
                    [Vector(0,0,delta+epsdelta), Vector(delta,0,delta+epsdelta), Vector(delta,delta,delta+epsdelta), Vector(0,delta,delta+epsdelta)],
                    [Vector(0,0,-epsdelta), Vector(0,delta,-epsdelta), Vector(delta,delta,-epsdelta), Vector(delta,0,-epsdelta)]]
        surfList = []
        # and now iterate through all the contact faces, and create FreeCAD Part.Faces
        for contact in contacts:
            vbase = Vector(gbbox.XMin + contact[0] * delta, gbbox.YMin + contact[1] * delta, gbbox.ZMin + contact[2] * delta)
            # the third element of 'contact' is the
            # index of the sides, order is ['+x', '-x', '+y', '-y', '+z', '-z']
            vertex = vertexes[contact[3]]
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
        # create the shell out of the list of faces
        contactShell = None
        if len(surfList) > 0:
            # create a shell. Does not need to be solid.
            contactShell = Part.makeShell(surfList)
        return contactShell

    def createVoxelShellFastCoin(self,shapePoints,contacts,gbbox,delta,voxelSpace=None):
        ''' Creates a shell composed by the external faces of a voxelized port.

            'contacts' is the list of contacts (see voxelizeContact() for the format)
            'gbbox' (FreeCAD.BoundBox) is the overall bounding box
            'delta' is the voxels size length
            'voxelSpace' (Numpy 3D array) is the voxel tensor of the overall space

            Remark: the VHPort must have already been voxelized
    '''
        if voxelSpace is None:
            return None
        # small displacement w.r.t. delta
        epsdelta = delta/EMVHPORT_EPSDELTA
        # vertexes of the six faces (with a slight offset)
        vertexes = [[Vector(delta+epsdelta,0,0), Vector(delta+epsdelta,delta,0), Vector(delta+epsdelta,delta,delta), Vector(delta+epsdelta,0,delta)],
                    [Vector(-epsdelta,0,0), Vector(-epsdelta,0,delta), Vector(-epsdelta,delta,delta), Vector(-epsdelta,delta,0)],
                    [Vector(0,delta+epsdelta,0), Vector(0,delta+epsdelta,delta), Vector(delta,delta+epsdelta,delta), Vector(delta,delta+epsdelta,0)],
                    [Vector(0,-epsdelta,0), Vector(delta,-epsdelta,0), Vector(delta,-epsdelta,delta), Vector(0,-epsdelta,delta)],
                    [Vector(0,0,delta+epsdelta), Vector(delta,0,delta+epsdelta), Vector(delta,delta,delta+epsdelta), Vector(0,delta,delta+epsdelta)],
                    [Vector(0,0,-epsdelta), Vector(0,delta,-epsdelta), Vector(delta,delta,-epsdelta), Vector(delta,0,-epsdelta)]]
        # and now iterate through all the contact faces, and create FreeCAD Part.Faces
        # The contact list is flat (to be able to store it as a PropertyIntegerList) so must go in steps of 4
        for contactIndex in range(0,len(contacts),4):
            vbase = Vector(gbbox.XMin + contacts[contactIndex] * delta, gbbox.YMin + contacts[contactIndex+1] * delta, gbbox.ZMin + contacts[contactIndex+2] * delta)
            # the third element of 'contact' is the
            # index of the sides, order is ['+x', '-x', '+y', '-y', '+z', '-z']
            vertex = vertexes[contacts[contactIndex+3]]
            # create the face
            # calculate the vertexes
            v11 = vbase + vertex[0]
            v12 = vbase + vertex[1]
            v13 = vbase + vertex[2]
            v14 = vbase + vertex[3]
            # now make the face
            shapePoints.extend([v11,v12,v13,v14])
        # create the shell out of the list of faces
        if len(shapePoints) > 0:
            return True
        else:
            return None

    def voxelizePort(self):
        ''' Voxelize the port object, i.e. find all the voxel faces belonging to the port

            The two list of voxel faces are assigned to internal variables
    '''
        if len(self.Object.PosFaces) == 0 and len(self.Object.NegFaces) == 0:
            FreeCAD.Console.PrintWarning(translate("EM","Cannot voxelize port, no faces assigned to the port\n"))
            return
        # get the VHSolver object
        solver = EM.getVHSolver()
        if solver is None:
             return
        FreeCAD.Console.PrintMessage(translate("EM","Starting voxelization of port ") + self.Object.Label + "...\n")
        # get global parameters from the VHSolver object
        gbbox = solver.Proxy.getGlobalBBox()
        delta = solver.Proxy.getDelta()
        voxelSpace = solver.Proxy.getVoxelSpace()
        if voxelSpace is None:
            FreeCAD.Console.PrintWarning(translate("EM","VoxelSpace not valid, cannot voxelize port\n"))
            return
        self.PosVoxelFaces = None
        self.NegVoxelFaces = None
        if len(self.Object.PosFaces) > 0:
            self.Object.PosVoxelContacts = self.voxelizeContact(self.Object.PosFaces,gbbox,delta,self.Object.DeltaDist/100.0,voxelSpace)
        if len(self.Object.NegFaces) > 0:
            self.Object.NegVoxelContacts = self.voxelizeContact(self.Object.NegFaces,gbbox,delta,self.Object.DeltaDist/100.0,voxelSpace)
        if len(self.Object.PosVoxelContacts) == 0 or len(self.Object.NegVoxelContacts) == 0:
            FreeCAD.Console.PrintWarning(translate("EM","No voxelized contacts created, could not voxelize port. Is there any voxelized conductor in the space by the port?\n"))
        else:
            self.Object.isVoxelized = True
            # if just voxelized, cannot show voxels; and if there was an old shell representing
            # the previoius voxelization, must clear it
            self.Object.ShowVoxels = False
        FreeCAD.Console.PrintMessage(translate("EM","Voxelization of the port completed.\n"))

    def voxelizeContact(self,faceSubobjs,gbbox,delta,deltadist,voxelSpace=None):
        ''' Find the voxel surface sides corresponding to the given contact surface
            (face) of an object. The object must have already been voxelized.

            'face' is the object face
            'condIndex' (integer) is the index of the object to which the face belongs.
                    It defines the object conductivity.
            'gbbox' (FreeCAD.BoundBox) is the overall bounding box
            'delta' is the voxels size length
            'voxelSpace' (Numpy 3D array) is the voxel tensor of the overall space
            'createShell' (bool) creates a shell out of the contact faces

            Returns a list of surfaces in the format x,y,z,voxside (all integers) repeated n times where
            x, y, z are the voxel position indexes, while voxside is '+x', '-x',
            '+y', '-y', '+z', '-z' according the the impacted surface of the voxel.
            The list is flat to allow it to be stored in a PropertyIntegerList
    '''
        if voxelSpace is None:
            return []
        contactList = []
        # get the faces bbox
        faces = self.getFaces(faceSubobjs)
        if len(faces) == 0:
            return []
        bbox = FreeCAD.BoundBox()
        for face in faces:
            bbox.add(face.BoundBox)
        if not bbox.isValid():
            return []
        # check if we are still within the global bbox
        if not gbbox.isInside(bbox):
            FreeCAD.Console.PrintWarning(translate("EM","Port faces bounding box is larger than the global bounding box. Cannot voxelize port.\n"))
            return []
        # now must find the voxel set that contains the faces bounding box
        # with a certain slack - it could be the next voxel,
        # if the surface is at the boundary between voxels.
        # Find the voxel that contains the bbox min point
        # (if negative, take zero)
        min_x = max(int((bbox.XMin - gbbox.XMin)/delta)-2, 0)
        min_y = max(int((bbox.YMin - gbbox.YMin)/delta)-2, 0)
        min_z = max(int((bbox.ZMin - gbbox.ZMin)/delta)-2, 0)
        # find the voxel that contains the bbox max point
        # (if larger than the voxelSpace, set to voxelSpace max dim,
        # we already verified that 'bbox' fits into 'gbbox')
        vs_size = voxelSpace.shape
        max_x = min(int((bbox.XMax - gbbox.XMin)/delta)+2, vs_size[0]-1)
        max_y = min(int((bbox.YMax - gbbox.YMin)/delta)+2, vs_size[1]-1)
        max_z = min(int((bbox.ZMax - gbbox.ZMin)/delta)+2, vs_size[2]-1)
        # create a Part.Vertex that we can use to test the distance
        # to the face (as it is a TopoShape)
        vec = FreeCAD.Vector(0,0,0)
        testVertex = Part.Vertex(vec)
        # this is half the side of the voxel
        halfdelta = delta/2.0
        # array to find the six neighbors
        sides = [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]
        # index of the sides, order is ['+x', '-x', '+y', '-y', '+z', '-z']
        sideStrs = range(6)
        # centers of the sides, with respect to the lower corner (with the smallest coordinates)
        sideCenters = [Vector(delta,halfdelta,halfdelta), Vector(0.0,halfdelta,halfdelta),
                        Vector(halfdelta,delta,halfdelta), Vector(halfdelta,0.0,halfdelta),
                        Vector(halfdelta,halfdelta,delta), Vector(halfdelta,halfdelta,0.0)]
        # and now iterate to find which voxel is inside the bounding box of the 'face',
        vbase = Vector(gbbox.XMin + min_x * delta, gbbox.YMin + min_y * delta, gbbox.ZMin + min_z * delta)
        for step_x in range(min_x,max_x+1):
            vbase.y = gbbox.YMin + min_y * delta
            for step_y in range(min_y,max_y+1):
                vbase.z = gbbox.ZMin + min_z * delta
                for step_z in range(min_z,max_z+1):
                    # check if voxel is belonging to an object
                    if voxelSpace[step_x,step_y,step_z] != 0:
                        # scan the six neighbor voxels, to see if they are belonging to the conductor or not.
                        # If they are not belonging to the conductor, or if the voxel space is finished, the current voxel
                        # side in the direction of the empty voxel is an external surface
                        for side, sideStr, sideCenter in zip(sides,sideStrs,sideCenters):
                            is_surface = False
                            nextVoxelIndexes = [step_x+side[0],step_y+side[1],step_z+side[2]]
                            if (nextVoxelIndexes[0] > max_x or nextVoxelIndexes[0] < 0 or
                               nextVoxelIndexes[1] > max_y or nextVoxelIndexes[1] < 0 or
                               nextVoxelIndexes[2] > max_z or nextVoxelIndexes[2] < 0):
                                is_surface = True
                            else:
                                if voxelSpace[nextVoxelIndexes[0],nextVoxelIndexes[1],nextVoxelIndexes[2]] == 0:
                                    is_surface = True
                            if is_surface == True:
                                testVertex.Placement.Base = vbase + sideCenter
                                # if the point is close enough to the face(s), we consider
                                # the voxel surface as belonging to the voxelized face(s);
                                # to this goal, take the shortest distance from any of the faces
                                mindist = bbox.DiagonalLength
                                for face in faces:
                                    dist = abs(testVertex.distToShape(face)[0])
                                    if dist < mindist:
                                        mindist = dist
                                if mindist < (delta*deltadist):
                                    contactList.extend([step_x,step_y,step_z,sideStr])
                    vbase.z += delta
                vbase.y += delta
            vbase.x += delta
        return contactList

    def flagVoxelizationInvalid(self):
        ''' Flags the voxelization as invalid
    '''
        self.Object.isVoxelized = False
        self.Object.ShowVoxels = False

    def getBaseObj(self):
        ''' Retrieves the Base object.

            Returns the Base object.
    '''
        return self.Object.Base

    def getCondIndex(self):
        ''' Retrieves the conductor index.

            Returns the int16 conductor index.
    '''
        return self.Object.CondIndex

    def setVoxelState(self,isVoxelized):
        ''' Sets the voxelization state.
    '''
        self.Object.isVoxelized = isVoxelized

    def serialize(self,fid):
        ''' Serialize the object to the 'fid' file descriptor
    '''
        # index of the sides, order is ['+x', '-x', '+y', '-y', '+z', '-z']
        sideStrs = range(6)

        if self.Object.isVoxelized == True:
            fid.write("* Port " + str(self.Object.Label) + "\n")
            name = "N " + str(self.Object.Label) + " P "
            self.serializeContact(fid,name,self.Object.PosVoxelContacts)
            name = "N " + str(self.Object.Label) + " N "
            self.serializeContact(fid,name,self.Object.NegVoxelContacts)
        else:
            FreeCAD.Console.PrintWarning(translate("EM","Object not voxelized, cannot serialize ") + str(self.Object.Label) + "\n")

    def serializeContact(self,fid,name,contacts):
        ''' Serialize the contact to the 'fid' file descriptor

        'contacts' is the list of contacts (see voxelizeContact() for the format)

    '''
        for contactIndex in range(0,len(contacts),4):
            # remark: VoxHenry voxel tensor is 1-based, not 0-based. Must add 1
            fid.write(name + " " + str(contacts[contactIndex+0]+1) + " " + str(contacts[contactIndex+1]+1) + " " + str(contacts[contactIndex+2]+1) + " " + EMVHPORT_SIDESTRS[contacts[contactIndex+3]] + "\n")

    def __getstate__(self):
        # JSON does not understand FreeCAD.Vector, so need to convert to tuples
        negConShapePointsJSON = [(x[0],x[1],x[2]) for x in self.negContactShapePoints]
        posConShapePointsJSON = [(x[0],x[1],x[2]) for x in self.posContactShapePoints]
        dictForJSON = {'nsp':negConShapePointsJSON,'psp':posConShapePointsJSON,'type':self.Type}
        #FreeCAD.Console.PrintMessage("Save\n"+str(dictForJSON)+"\n") #debug
        return dictForJSON

    def __setstate__(self,dictForJSON):
        if dictForJSON:
            #FreeCAD.Console.PrintMessage("Load\n"+str(dictForJSON)+"\n") #debug
            # no need to convert back to FreeCAD.Vectors, 'shapePoints' can also be tuples
            self.negContactShapePoints = dictForJSON['nsp']
            self.posContactShapePoints = dictForJSON['psp']
            self.Type = dictForJSON['type']

class _ViewProviderVHPort:
    def __init__(self, vobj):
        ''' Set this object to the proxy object of the actual view provider '''
        vobj.addProperty("App::PropertyColor","PosPortColor","Base","")
        vobj.addProperty("App::PropertyColor","NegPortColor","Base","")
        vobj.PosPortColor = EMVHPORT_DEF_POSPORTCOLOR
        vobj.NegPortColor = EMVHPORT_DEF_NEGPORTCOLOR
        # set also default LineColor
        vobj.LineColor = EMVHPORT_DEF_LINECOLOR
        # remark: these associations must *follow* the addition of the custom properties,
        # or attach() will be called before the properties are created
        vobj.Proxy = self
        self.VObject = vobj
        self.Object = vobj.Object

    def attach(self, vobj):
        ''' Setup the scene sub-graph of the view provider, this method is mandatory '''
        # on restore, self.Object is not there anymore (JSON does not serialize complex objects
        # members of the class, so __getstate__() and __setstate__() skip them);
        # so we must "re-attach" (re-create) the 'self.Object'
        self.Object = vobj.Object
        self.VObject = vobj
        # actual representation
        self.switch = coin.SoSwitch()
        self.hints = coin.SoShapeHints()
        self.style1 = coin.SoDrawStyle()
        self.style2 = coin.SoDrawStyle()
        self.materialPos = coin.SoMaterial()
        self.materialNeg = coin.SoMaterial()
        self.linecolor = coin.SoBaseColor()
        self.dataPos = coin.SoCoordinate3()
        self.dataNeg = coin.SoCoordinate3()
        self.facePos = coin.SoFaceSet()
        self.faceNeg = coin.SoFaceSet()
        # init
        # A shape hints tells the ordering of polygons.
        # This ensures double-sided lighting.
        self.hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        self.hints.faceType = coin.SoShapeHints.CONVEX
        # init styles
        self.style1.style = coin.SoDrawStyle.FILLED
        self.style2.style = coin.SoDrawStyle.LINES
        self.style2.lineWidth = self.VObject.LineWidth
        # init color
        self.materialPos.diffuseColor.setValue(self.VObject.PosPortColor[0],self.VObject.PosPortColor[1],self.VObject.PosPortColor[2])
        self.materialPos.transparency = self.VObject.Transparency/100.0
        self.materialNeg.diffuseColor.setValue(self.VObject.NegPortColor[0],self.VObject.NegPortColor[1],self.VObject.NegPortColor[2])
        self.materialNeg.transparency = self.VObject.Transparency/100.0
        self.linecolor.rgb.setValue(self.VObject.LineColor[0],self.VObject.LineColor[1],self.VObject.LineColor[2])
        # instructs to visit the first child (this is used to toggle visiblity)
        self.switch.whichChild = coin.SO_SWITCH_ALL
        #  scene
        #sep = coin.SoSeparator()
        # not using a separator, but a FreeCAD Selection node
        sep = coin.SoType.fromName("SoFCSelection").createInstance()
        sep.documentName.setValue(self.Object.Document.Name)
        sep.objectName.setValue(self.Object.Name)
        sep.subElementName.setValue("Face")
        # now adding the common children
        sep.addChild(self.hints)
        sep.addChild(self.switch)
        # and finally the two groups, the first is the contour lines,
        # the second is the filled faces, so we can switch between
        # "Flat Lines", "Shaded" and "Wireframe". Note: not implementing "Points"
        group0Line = coin.SoGroup()
        self.switch.addChild(group0Line)
        group0Line.addChild(self.style2)
        group0Line.addChild(self.linecolor)
        group0Line.addChild(self.dataPos)
        group0Line.addChild(self.facePos)
        group0Line.addChild(self.dataNeg)
        group0Line.addChild(self.faceNeg)
        group1Face = coin.SoGroup()
        self.switch.addChild(group1Face)
        group1Face.addChild(self.materialPos)
        group1Face.addChild(self.style1)
        group1Face.addChild(self.dataPos)
        group1Face.addChild(self.facePos)
        group1Face.addChild(self.materialNeg)
        group1Face.addChild(self.style1)
        group1Face.addChild(self.dataNeg)
        group1Face.addChild(self.faceNeg)
        self.VObject.RootNode.addChild(sep)
        #FreeCAD.Console.PrintMessage("ViewProvider attach() completed\n")
        return

    def updateData(self, fp, prop):
        ''' If a property of the data object has changed we have the chance to handle this here
            'fp' is the handled feature (the object)
            'prop' is the name of the property that has changed
    '''
        #FreeCAD.Console.PrintMessage("ViewProvider updateData(),  property: " + str(prop) + "\n") # debug
        if prop == "Shape":
            numpointsPos = len(self.Object.Proxy.posContactShapePoints)
            numpointsNeg = len(self.Object.Proxy.negContactShapePoints)
            # this can be used to reset the number of points to the value actually needed
            # (e.g. shorten the array, or pre-allocate it). However setValue() will automatically
            # increase the array size if needed, and will NOT shorten it if less values are inserted
            # This is less memory efficient, but faster; and in using the points in the SoFaceSet,
            # we specify how many points (vertices) we want out of the total array, so no issue
            # if the array is longer
            #self.data.point.setNum(numpoints)
            self.dataPos.point.setValues(0,numpointsPos,self.Object.Proxy.posContactShapePoints)
            self.dataNeg.point.setValues(0,numpointsNeg,self.Object.Proxy.negContactShapePoints)
            # 'numvertices' contains the number of vertices used for each face.
            # Here all faces are quadrilaterals, so this is a long array of number '4's
            numverticesPos = [4 for i in range(int(numpointsPos/4))]
            numverticesNeg = [4 for i in range(int(numpointsNeg/4))]
            # set the number of vertices per each face, for a total of len(numvertices) faces, starting from 0
            # but must first delete all the old values, otherwise the remaining panels with vertices from
            # 'numvertices+1' will still be shown
            self.facePos.numVertices.deleteValues(0,-1)
            self.facePos.numVertices.setValues(0,len(numverticesPos),numverticesPos)
            self.faceNeg.numVertices.deleteValues(0,-1)
            self.faceNeg.numVertices.setValues(0,len(numverticesNeg),numverticesNeg)
            #FreeCAD.Console.PrintMessage("numpoints " + str(numpoints) + "; numvertices " + str(numvertices) + "\n") # debug
            #FreeCAD.Console.PrintMessage("self.Object.Proxy.shapePoints " + str(self.Object.Proxy.shapePoints) + "\n") # debug
            #FreeCAD.Console.PrintMessage("self.data.point " + str(self.data.point.get()) + "\n") # debug
            #FreeCAD.Console.PrintMessage("updateData() shape!\n") # debug
        return

    def onChanged(self, vp, prop):
        ''' If the 'prop' property changed for the ViewProvider 'vp' '''
        #FreeCAD.Console.PrintMessage("ViewProvider onChanged(), property: " + str(prop) + "\n") # debug
        if not hasattr(self,"VObject"):
            self.VObject = vp
         # if there is a coin3d custom representation
        if self.Object.isVoxelized and self.Object.ShowVoxels:
            if prop == "PosPortColor" or prop == "NegPortColor":
                self.materialPos.diffuseColor.setValue(self.VObject.PosPortColor[0],self.VObject.PosPortColor[1],self.VObject.PosPortColor[2])
                self.materialNeg.diffuseColor.setValue(self.VObject.NegPortColor[0],self.VObject.NegPortColor[1],self.VObject.NegPortColor[2])
            if prop == "Visibility" or prop=="DisplayMode":
                if not vp.Visibility:
                    self.switch.whichChild = coin.SO_SWITCH_NONE
                else:
                    if self.VObject.DisplayMode == "Wireframe":
                        self.switch.whichChild = 0
                    elif self.VObject.DisplayMode == "Shaded":
                        self.switch.whichChild = 1
                    else:
                        self.switch.whichChild = coin.SO_SWITCH_ALL
            if prop == "LineColor":
                self.linecolor.rgb.setValue(self.VObject.LineColor[0],self.VObject.LineColor[1],self.VObject.LineColor[2])
            if prop == "LineWidth":
                self.style2.lineWidth = self.VObject.LineWidth
            if prop == "Transparency":
                self.materialPos.transparency = self.VObject.Transparency/100.0
                self.materialNeg.transparency = self.VObject.Transparency/100.0
        # otherwise the VHPort is based on a Shape containing the faces composing the port
        else:
            if prop == "PosPortColor" or prop == "NegPortColor":
                if vp.Object.Shape is not None:
                    # only if this is not a direct coin3d representation but a compound
                    # of faces, color them according to which port they are
                    if type(vp.Object.Shape) == Part.Compound:
                        if len(vp.Object.Shape.Faces) >= 2:
                            self.VObject.DiffuseColor = [self.VObject.PosPortColor for x in range(0,len(vp.Object.PosFaces))] + [self.VObject.NegPortColor for x in range(0,len(vp.Object.NegFaces))]

    def getDefaultDisplayMode(self):
        ''' Return the name of the default display mode. It must be defined in getDisplayModes. '''
        return "Flat Lines"

    def getIcon(self):
        ''' Return the icon which will appear in the tree view. This method is optional
        and if not defined a default icon is shown.
        '''
        return os.path.join(iconPath, 'EM_VHPort.svg')

    def __getstate__(self):
        return None

    def __setstate__(self,state):
        return None

class _CommandVHPort:
    ''' The EM VoxHenry Conductor (VHPort) command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'EM_VHPort.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_VHPort","VHPort"),
                'Accel': "E, O",
                'ToolTip': QT_TRANSLATE_NOOP("EM_VHPort","Creates a VoxHenry Port object from a set of faces")}

    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        # preferences
        #p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/EM")
        #self.Width = p.GetFloat("Width",200)
        # get the selected object(s)
        selection = FreeCADGui.Selection.getSelectionEx()
        if len(selection) > 0:
            FreeCAD.ActiveDocument.openTransaction(translate("EM","Create VHPort"))
            FreeCADGui.addModule("EM")
            FreeCADGui.doCommand('obj=EM.makeVHPortFromSel(FreeCADGui.Selection.getSelectionEx())')
            # autogrouping, for later on
            #FreeCADGui.addModule("Draft")
            #FreeCADGui.doCommand("Draft.autogroup(obj)")
            FreeCAD.ActiveDocument.commitTransaction()
            FreeCAD.ActiveDocument.recompute()
        else:
            FreeCAD.Console.PrintWarning(translate("EM","No face selected for the creation of a VHPort (need at least two). Nothing done."))

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_VHPort',_CommandVHPort())
