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


__title__="FreeCAD E.M. Workbench VoxHenry Conductor Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# copper conductivity 1/(m*Ohms)
EMVHSOLVER_DEF_SIGMA = 5.8e7

import FreeCAD, FreeCADGui, Part, Draft, DraftGeomUtils, os
import DraftVecUtils
import Mesh
from EM_Globals import getVHSolver
from FreeCAD import Vector
import numpy as np
import time
from pivy import coin

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

def makeVHConductor(baseobj=None,name='VHConductor'):
    ''' Creates a VoxHenry Conductor (a voxelized solid object)

        'baseobj' is the 3D solid object on which the conductor is based.
            If no 'baseobj' is given, the user must assign a base
            object later on, to be able to use this object.
            The 'baseobj' is mandatory, and can be any 3D solid object
        'name' is the name of the object

    Example:
        cond = makeVHConductor(mySolid)
'''
    # to check if the object fits into the VHSolver bbox, we must retrieve
    # the global bbox *before* the new VHConductor is created.
    # get the VHSolver object; if not existing, create it
    solver = getVHSolver(True)
    if solver is not None:
        gbbox = solver.Proxy.getGlobalBBox()
        condIndex = solver.Proxy.getNextCondIndex()
    else:
        FreeCAD.Console.PrintWarning(translate("EM","As we found no valid VHSolver object, conductor index is set to 1. This may create issues in simulation (multiple VHConductors with the same conductor index)"))
        condIndex = 1
    # now create the object
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    # this adds the relevant properties to the object
    #'obj' (e.g. 'Base' property) making it a _VHConductor
    _VHConductor(obj)
    # now we have the properties, init condIndex
    obj.CondIndex = condIndex
    # manage ViewProvider object
    if FreeCAD.GuiUp:
        _ViewProviderVHConductor(obj.ViewObject)
        # set base ViewObject properties to user-selected values (if any)
    # check if 'baseobj' is a solid object
    if baseobj is not None:
        # if right type of base
        if not baseobj.isDerivedFrom("Part::Feature"):
            FreeCAD.Console.PrintWarning(translate("EM","VHConductor can only be based on objects derived from Part::Feature"))
            return
        # check validity
        if baseobj.Shape.isNull():
            FreeCAD.Console.PrintWarning(translate("EM","VHConductor base object shape is null"))
            return
        if not baseobj.Shape.isValid():
            FreeCAD.Console.PrintWarning(translate("EM","VHConductor base object shape is invalid"))
            return
        obj.Base = baseobj
        # check if the object fits into the VHSolver bbox, otherwise must flag the voxel space as invalid
        if solver is not None:
            bbox = baseobj.Shape.BoundBox
            if gbbox.isValid() and bbox.isValid():
                if not gbbox.isInside(bbox):
                    # invalidate voxel space
                    solver.Proxy.flagVoxelSpaceInvalid()
        # hide the base object
        if FreeCAD.GuiUp:
            obj.Base.ViewObject.hide()
    # return the newly created Python object
    return obj

class _VHConductor:
    '''The EM VoxHenry Conductor object'''
    def __init__(self, obj):
        # save the object in the class, to store or retrieve specific data from it
        # from within the class
        self.Object = obj
        ''' Add properties '''
        obj.addProperty("App::PropertyLink", "Base", "EM", QT_TRANSLATE_NOOP("App::Property","The base object this component is built upon"))
        obj.addProperty("App::PropertyFloat","Sigma","EM",QT_TRANSLATE_NOOP("App::Property","Conductor conductivity (S/m)"))
        obj.addProperty("App::PropertyLength","Lambda","EM",QT_TRANSLATE_NOOP("App::Property","Superconductor London penetration depth (m)"))
        obj.addProperty("App::PropertyBool","ShowVoxels","EM",QT_TRANSLATE_NOOP("App::Property","Show the voxelization"))
        obj.addProperty("App::PropertyInteger","CondIndex","EM",QT_TRANSLATE_NOOP("App::Property","Voxel space VHConductor index number (read-only)"),1)
        obj.addProperty("App::PropertyBool","isVoxelized","EM",QT_TRANSLATE_NOOP("App::Property","Flags if the conductor has been voxelized (read only)"),1)
        obj.ShowVoxels = False
        obj.Proxy = self
        obj.isVoxelized = False
        obj.Sigma = EMVHSOLVER_DEF_SIGMA
        self.shapePoints = []
        self.Type = "VHConductor"

    def onChanged(self, obj, prop):
        ''' take action if an object property 'prop' changed
    '''
        #FreeCAD.Console.PrintWarning("\n_VHConductor onChanged(" + str(prop)+")\n") #debug
        # on restore, self.Object is not there anymore (JSON does not serialize complex objects
        # members of the class, so __getstate__() and __setstate__() skip them);
        # so we must "re-attach" (re-create) the 'self.Object'
        if not hasattr(self,"Object"):
            self.Object = obj
        # if just changed non-shape affecting properties, clear the recompute flag (not needed)
        #if prop == "Sigma" or prop == "Lambda":
        #    obj.purgeTouched()

    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute()
    '''
        #FreeCAD.Console.PrintWarning("_VHConductor execute()\n") #debug
        # the class needs a 'Base' object
        if obj.Base is None:
            return
        # if right type of base
        if not obj.Base.isDerivedFrom("Part::Feature"):
            FreeCAD.Console.PrintWarning(translate("EM","VHConductor can only be based on objects derived from Part::Feature"))
            return
        # check validity
        if obj.Base.Shape.isNull():
            FreeCAD.Console.PrintWarning(translate("EM","VHConductor base object shape is null"))
            return
        if not obj.Base.Shape.isValid():
            FreeCAD.Console.PrintWarning(translate("EM","VHConductor base object shape is invalid"))
            return
        shape = None
        # Check if the user selected to see the voxelization, and if the voxelization exists
        if obj.ShowVoxels == True:
            # get the VHSolver object
            solver = getVHSolver()
            if solver is not None:
                gbbox = solver.Proxy.getGlobalBBox()
                delta = solver.Proxy.getDelta()
                # getting the voxel space may cause the voxelization of this VHConductor to become invalid,
                # if the global bounding box is found to have changed, or VHSolver 'Delta' changed over time, etc.
                voxelSpace = solver.Proxy.getVoxelSpace()
                if obj.isVoxelized == False:
                    FreeCAD.Console.PrintWarning(translate("EM","Cannot fulfill 'ShowVoxels', VHConductor object has not been voxelized, or voxelization is now invalid (e.g. change in voxel space dimensions). Voxelize it first."))
                else:
                    shape = self.createVoxelShellFastCoin(obj.Base,obj.CondIndex,gbbox,delta,voxelSpace)
        if shape is None:
            # if we don't show the voxelized view of the object, let's show the bounding box
            self.shapePoints = []
            bbox = obj.Base.Shape.BoundBox
            if bbox.isValid():
                shape = Part.makeBox(bbox.XLength,bbox.YLength,bbox.ZLength,Vector(bbox.XMin,bbox.YMin,bbox.ZMin))
                # and finally assign the shape (but only if we were able to create any)
                obj.Shape = shape
        else:
            # make a dummy empty shape. Representation is through custom coin3d scenegraph.
            obj.Shape = Part.makeShell([])
        #if FreeCAD.GuiUp:
            # force shape recompute (even if we are using directly coin here)
        #    _ViewProviderVHConductor.updateData(obj.ViewObject.Proxy,obj.ViewObject,"Shape")
        #FreeCAD.Console.PrintWarning("_VHConductor execute() ends\n") #debug

    def createVoxelShell(self,obj,condIndex,gbbox,delta,voxelSpace=None):
        ''' Creates a shell composed by the external faces of a voxelized object.

            'obj' is the object whose shell must be created
            'condIndex' (int16) is the index of the object. It defines the object conductivity.
            'gbbox' (FreeCAD.BoundBox) is the overall bounding box
            'delta' is the voxels size length
            'voxelSpace' (Numpy 3D array) is the voxel tensor of the overall space
            
            This version uses a standard Part::Shell

            Remark: the VHConductor must have already been voxelized
    '''
        if voxelSpace is None:
            return None
        if not hasattr(obj,"Shape"):
            return None
        if self.Object.isVoxelized == False:
            return None
        surfList = []
        # get the object's bbox
        bbox = obj.Shape.BoundBox
        if not gbbox.isInside(bbox):
            FreeCAD.Console.PrintError(translate("EM","Conductor bounding box is larger than the global bounding box. Cannot voxelize conductor shell.\n"))
            return
        # now must find the voxel set that contains the object bounding box
        # find the voxel that contains the bbox min point
        min_x = int((bbox.XMin - gbbox.XMin)/delta)
        min_y = int((bbox.YMin - gbbox.YMin)/delta)
        min_z = int((bbox.ZMin - gbbox.ZMin)/delta)
        # find the voxel that contains the bbox max point
        # (if larger than the voxelSpace, set to voxelSpace max dim,
        # we already verified that 'bbox' fits into 'gbbox')
        vs_size = voxelSpace.shape
        max_x = min(int((bbox.XMax - gbbox.XMin)/delta), vs_size[0]-1)
        max_y = min(int((bbox.YMax - gbbox.YMin)/delta), vs_size[1]-1)
        max_z = min(int((bbox.ZMax - gbbox.ZMin)/delta), vs_size[2]-1)
        # array to find the six neighbour
        sides = [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]
        # vertexes of the six faces
        vertexes = [[Vector(delta,0,0), Vector(delta,delta,0), Vector(delta,delta,delta), Vector(delta,0,delta)],
                    [Vector(0,0,0), Vector(0,0,delta), Vector(0,delta,delta), Vector(0,delta,0)],
                    [Vector(0,delta,0), Vector(0,delta,delta), Vector(delta,delta,delta), Vector(delta,delta,0)],
                    [Vector(0,0,0), Vector(delta,0,0), Vector(delta,0,delta), Vector(0,0,delta)],
                    [Vector(0,0,delta), Vector(delta,0,delta), Vector(delta,delta,delta), Vector(0,delta,delta)],
                    [Vector(0,0,0), Vector(0,delta,0), Vector(delta,delta,0), Vector(delta,0,0)]]
        # get the base point
        vbase = Vector(gbbox.XMin + min_x * delta, gbbox.YMin + min_y * delta, gbbox.ZMin + min_z * delta)
        FreeCAD.Console.PrintMessage(translate("EM","Starting voxel shell creation for object ") + obj.Label + "...\n")
        # make a progress bar - commented out as not working properly
        # total number of voxels to scan is
        #totalVox = (max_x-min_x) * (max_y-min_y) * (max_z-min_z)
        #stepProg = totalVox / 100.0
        #progIndex = 0
        #progBar = FreeCAD.Base.ProgressIndicator()
        #progBar.start(translate("EM","Voxelizing object ") + obj.Label ,100)
        for step_x in range(min_x,max_x+1):
            vbase.y = gbbox.YMin + min_y * delta
            for step_y in range(min_y,max_y+1):
                # advancing the progress bar. Doing it only in the y loop for optimization
                #if (step_x-min_x)*(max_y-min_y)*(max_z-min_z) + (step_y-min_y)*(max_z-min_z) > stepProg * progIndex:
                #    progBar.next()
                #    progIndex = progIndex + 1
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
        #progBar.stop()
        FreeCAD.Console.PrintMessage(translate("EM","Voxelization of the shell completed.\n"))
        # create a shell. Does not need to be solid.
        objShell = Part.makeShell(surfList)
        return objShell

    def createVoxelShellFast(self,obj,condIndex,gbbox,delta,voxelSpace=None):
        ''' Creates a shell composed by the external faces of a voxelized object.

            'obj' is the object whose shell must be created
            'condIndex' (int16) is the index of the object. It defines the object conductivity.
            'gbbox' (FreeCAD.BoundBox) is the overall bounding box
            'delta' is the voxels size length
            'voxelSpace' (Numpy 3D array) is the voxel tensor of the overall space

            This version uses a standard Part::Shell, but calculates the VHConductor
            boundaries by finite differences over the voxel conductor space,
            for speed in Python. However the speed bottleneck is still the
            use of the Part::Shell via OpenCascade

            Remark: the VHConductor must have already been voxelized
    '''
        if voxelSpace is None:
            return None
        if not hasattr(obj,"Shape"):
            return None
        if self.Object.isVoxelized == False:
            return None
        surfList = []
        # get the object's bbox
        bbox = obj.Shape.BoundBox
        if not gbbox.isInside(bbox):
            FreeCAD.Console.PrintError(translate("EM","Conductor bounding box is larger than the global bounding box. Cannot voxelize conductor shell.\n"))
            return
        # now must find the voxel set that contains the object bounding box
        # find the voxel that contains the bbox min point
        min_x = int((bbox.XMin - gbbox.XMin)/delta)
        min_y = int((bbox.YMin - gbbox.YMin)/delta)
        min_z = int((bbox.ZMin - gbbox.ZMin)/delta)
        # find the voxel that contains the bbox max point
        # (if larger than the voxelSpace, set to voxelSpace max dim,
        # we already verified that 'bbox' fits into 'gbbox')
        vs_size = voxelSpace.shape
        max_x = min(int((bbox.XMax - gbbox.XMin)/delta), vs_size[0]-1)
        max_y = min(int((bbox.YMax - gbbox.YMin)/delta), vs_size[1]-1)
        max_z = min(int((bbox.ZMax - gbbox.ZMin)/delta), vs_size[2]-1)
        # get the base point
        vbase = Vector(gbbox.XMin + min_x * delta, gbbox.YMin + min_y * delta, gbbox.ZMin + min_z * delta)
        # now get a sub-tensor out of the voxel space, containing the obj.Shape; but make it one (empty) voxel
        # larger in every direction (that's the '+2': one voxel in the - direction, one in the +),
        # so we can check if the object shape span up to the border
        dim_x = max_x+1-min_x
        dim_y = max_y+1-min_y
        dim_z = max_z+1-min_z
        # create the sub-tensor
        voxSubSpace = np.full((dim_x+2,dim_y+2,dim_z+2),0,np.int32)
        # copy the sub-tensor out of the full voxel space, after selecting the elements
        # corresponding to 'condIndex' and converting (casting with astype() )
        # to a matrix composed only of zeros and ones (True -> 1, False -> 0)
        voxSubSpace[1:dim_x+1,1:dim_y+1,1:dim_z+1] = (voxelSpace[min_x:max_x+1,min_y:max_y+1,min_z:max_z+1] == condIndex).astype(np.int8)
        # now we must find the boundaries in the three x,y,z directions. We differentiate.
        # start from dx
        diff = voxSubSpace[1:dim_x+2,:,:] - voxSubSpace[0:dim_x+1,:,:]
        # and extract the non-zero elements positions
        voxelIndices = [ [step_x,step_y,step_z] for step_x in range(0,dim_x+1) for step_y in range(0,dim_y+2) for step_z in range(0,dim_z+2) if diff[step_x,step_y,step_z] != 0]
        # cube x side vertex points
        vertex = [Vector(0,0,0), Vector(0,0,delta), Vector(0,delta,delta), Vector(0,delta,0)]
        # now we can create the faces orthogonal to the current direction
        for index in voxelIndices:
            # calculate the base point of the vector pointed to by 'index' (remark: 'index' is not the index
            # of the voxel, but of the surface between two voxels, for the direction along which we are operating)
            vbaseRel = vbase + Vector(index[0]*delta,(index[1]-1)*delta,(index[2]-1)*delta)
            # create the face
            # calculate the vertexes
            v11 = vbaseRel + vertex[0]
            v12 = vbaseRel + vertex[1]
            v13 = vbaseRel + vertex[2]
            v14 = vbaseRel + vertex[3]
            # now make the face
            poly = Part.makePolygon( [v11,v12,v13,v14,v11])
            face = Part.Face(poly)
            surfList.append(face)
        # then dy
        diff = voxSubSpace[:,1:dim_y+2,:] - voxSubSpace[:,0:dim_y+1,:]
        # and extract the non-zero elements positions
        voxelIndices = [ [step_x,step_y,step_z] for step_x in range(0,dim_x+2) for step_y in range(0,dim_y+1) for step_z in range(0,dim_z+2) if diff[step_x,step_y,step_z] != 0]
        # cube y side vertex points
        vertex = [Vector(0,0,0), Vector(delta,0,0), Vector(delta,0,delta), Vector(0,0,delta)]
        # now we can create the faces orthogonal to the current direction
        for index in voxelIndices:
            # calculate the base point of the vector pointed to by 'index' (remark: 'index' is not the index
            # of the voxel, but of the surface between two voxels, for the direction along which we are operating)
            vbaseRel = vbase + Vector((index[0]-1)*delta,index[1]*delta,(index[2]-1)*delta)
            # create the face
            # calculate the vertexes
            v11 = vbaseRel + vertex[0]
            v12 = vbaseRel + vertex[1]
            v13 = vbaseRel + vertex[2]
            v14 = vbaseRel + vertex[3]
            # now make the face
            poly = Part.makePolygon( [v11,v12,v13,v14,v11])
            face = Part.Face(poly)
            surfList.append(face)
        # then dz
        diff = voxSubSpace[:,:,1:dim_z+2] - voxSubSpace[:,:,0:dim_z+1]
        # and extract the non-zero elements positions
        voxelIndices = [ [step_x,step_y,step_z] for step_x in range(0,dim_x+2) for step_y in range(0,dim_y+2) for step_z in range(0,dim_z+1) if diff[step_x,step_y,step_z] != 0]
        # cube z side vertex points
        vertex = [Vector(0,0,0), Vector(0,delta,0), Vector(delta,delta,0), Vector(delta,0,0)]
        # now we can create the faces orthogonal to the current direction
        for index in voxelIndices:
            # calculate the base point of the vector pointed to by 'index' (remark: 'index' is not the index
            # of the voxel, but of the surface between two voxels, for the direction along which we are operating)
            vbaseRel = vbase + Vector((index[0]-1)*delta,(index[1]-1)*delta,index[2]*delta)
            # create the face
            # calculate the vertexes
            v11 = vbaseRel + vertex[0]
            v12 = vbaseRel + vertex[1]
            v13 = vbaseRel + vertex[2]
            v14 = vbaseRel + vertex[3]
            # now make the face
            poly = Part.makePolygon( [v11,v12,v13,v14,v11])
            face = Part.Face(poly)
            surfList.append(face)
        #progBar.stop()
        FreeCAD.Console.PrintMessage(translate("EM","Voxelization of the shell completed.\n"))
        # create a shell. Does not need to be solid.
        objShell = Part.makeShell(surfList)
        return objShell

    def createVoxelShellFastCoin(self,obj,condIndex,gbbox,delta,voxelSpace=None):
        ''' Creates a shell composed by the external faces of a voxelized object.

            'obj' is the object whose shell must be created
            'condIndex' (int16) is the index of the object. It defines the object conductivity.
            'gbbox' (FreeCAD.BoundBox) is the overall bounding box
            'delta' is the voxels size length
            'voxelSpace' (Numpy 3D array) is the voxel tensor of the overall space

            This version uses a direct coin3d / pivy representation of the VHConductor
            boundaries ('shell'), and calculates the VHConductor
            boundaries by finite differences over the voxel conductor space,
            for speed in Python.

            Remark: the VHConductor must have already been voxelized
    '''
        if voxelSpace is None:
            return None
        if not hasattr(obj,"Shape"):
            return None
        if self.Object.isVoxelized == False:
            return None
        self.shapePoints = []
        # get the object's bbox
        bbox = obj.Shape.BoundBox
        if not gbbox.isInside(bbox):
            FreeCAD.Console.PrintError(translate("EM","Conductor bounding box is larger than the global bounding box. Cannot voxelize conductor shell.\n"))
            return
        # now must find the voxel set that contains the object bounding box
        # find the voxel that contains the bbox min point
        min_x = int((bbox.XMin - gbbox.XMin)/delta)
        min_y = int((bbox.YMin - gbbox.YMin)/delta)
        min_z = int((bbox.ZMin - gbbox.ZMin)/delta)
        # find the voxel that contains the bbox max point
        # (if larger than the voxelSpace, set to voxelSpace max dim,
        # we already verified that 'bbox' fits into 'gbbox')
        vs_size = voxelSpace.shape
        max_x = min(int((bbox.XMax - gbbox.XMin)/delta), vs_size[0]-1)
        max_y = min(int((bbox.YMax - gbbox.YMin)/delta), vs_size[1]-1)
        max_z = min(int((bbox.ZMax - gbbox.ZMin)/delta), vs_size[2]-1)
        # get the base point
        vbase = Vector(gbbox.XMin + min_x * delta, gbbox.YMin + min_y * delta, gbbox.ZMin + min_z * delta)
        # now get a sub-tensor out of the voxel space, containing the obj.Shape; but make it one (empty) voxel
        # larger in every direction (that's the '+2': one voxel in the - direction, one in the +),
        # so we can check if the object shape span up to the border
        dim_x = max_x+1-min_x
        dim_y = max_y+1-min_y
        dim_z = max_z+1-min_z
        # create the sub-tensor
        voxSubSpace = np.full((dim_x+2,dim_y+2,dim_z+2),0,np.int32)
        # copy the sub-tensor out of the full voxel space, after selecting the elements
        # corresponding to 'condIndex' and converting (casting with astype() )
        # to a matrix composed only of zeros and ones (True -> 1, False -> 0)
        voxSubSpace[1:dim_x+1,1:dim_y+1,1:dim_z+1] = (voxelSpace[min_x:max_x+1,min_y:max_y+1,min_z:max_z+1] == condIndex).astype(np.int8)
        # now we must find the boundaries in the three x,y,z directions. We differentiate.
        # start from dx
        diff = voxSubSpace[1:dim_x+2,:,:] - voxSubSpace[0:dim_x+1,:,:]
        # and extract the non-zero elements positions
        voxelIndices = [ [step_x,step_y,step_z] for step_x in range(0,dim_x+1) for step_y in range(0,dim_y+2) for step_z in range(0,dim_z+2) if diff[step_x,step_y,step_z] != 0]
        # cube x side vertex points
        vertex = [Vector(0,0,0), Vector(0,0,delta), Vector(0,delta,delta), Vector(0,delta,0)]
        # now we can create the faces orthogonal to the current direction
        for index in voxelIndices:
            # calculate the base point of the vector pointed to by 'index' (remark: 'index' is not the index
            # of the voxel, but of the surface between two voxels, for the direction along which we are operating)
            vbaseRel = vbase + Vector(index[0]*delta,(index[1]-1)*delta,(index[2]-1)*delta)
            # create the face
            # calculate the vertexes
            v11 = vbaseRel + vertex[0]
            v12 = vbaseRel + vertex[1]
            v13 = vbaseRel + vertex[2]
            v14 = vbaseRel + vertex[3]
            # now make the face
            self.shapePoints.extend([v11,v12,v13,v14])
        # then dy
        diff = voxSubSpace[:,1:dim_y+2,:] - voxSubSpace[:,0:dim_y+1,:]
        # and extract the non-zero elements positions
        voxelIndices = [ [step_x,step_y,step_z] for step_x in range(0,dim_x+2) for step_y in range(0,dim_y+1) for step_z in range(0,dim_z+2) if diff[step_x,step_y,step_z] != 0]
        # cube y side vertex points
        vertex = [Vector(0,0,0), Vector(delta,0,0), Vector(delta,0,delta), Vector(0,0,delta)]
        # now we can create the faces orthogonal to the current direction
        for index in voxelIndices:
            # calculate the base point of the vector pointed to by 'index' (remark: 'index' is not the index
            # of the voxel, but of the surface between two voxels, for the direction along which we are operating)
            vbaseRel = vbase + Vector((index[0]-1)*delta,index[1]*delta,(index[2]-1)*delta)
            # create the face
            # calculate the vertexes
            v11 = vbaseRel + vertex[0]
            v12 = vbaseRel + vertex[1]
            v13 = vbaseRel + vertex[2]
            v14 = vbaseRel + vertex[3]
            # now make the face
            self.shapePoints.extend([v11,v12,v13,v14])
        # then dz
        diff = voxSubSpace[:,:,1:dim_z+2] - voxSubSpace[:,:,0:dim_z+1]
        # and extract the non-zero elements positions
        voxelIndices = [ [step_x,step_y,step_z] for step_x in range(0,dim_x+2) for step_y in range(0,dim_y+2) for step_z in range(0,dim_z+1) if diff[step_x,step_y,step_z] != 0]
        # cube z side vertex points
        vertex = [Vector(0,0,0), Vector(0,delta,0), Vector(delta,delta,0), Vector(delta,0,0)]
        # now we can create the faces orthogonal to the current direction
        for index in voxelIndices:
            # calculate the base point of the vector pointed to by 'index' (remark: 'index' is not the index
            # of the voxel, but of the surface between two voxels, for the direction along which we are operating)
            vbaseRel = vbase + Vector((index[0]-1)*delta,(index[1]-1)*delta,index[2]*delta)
            # create the face
            # calculate the vertexes
            v11 = vbaseRel + vertex[0]
            v12 = vbaseRel + vertex[1]
            v13 = vbaseRel + vertex[2]
            v14 = vbaseRel + vertex[3]
            # now make the face
            self.shapePoints.extend([v11,v12,v13,v14])
        #progBar.stop()
        #FreeCAD.Console.PrintMessage(translate("EM","Voxelization of the shell completed.\n"))
        return True
        
    def voxelizeConductor(self):
        ''' Voxelize the Base (solid) object. The function will modify the 'voxelSpace'
            by marking with 'CondIndex' all the voxels that sample the Base object
            as internal.
    '''
        if self.Object.Base is None:
            return
        if not hasattr(self.Object.Base,"Shape"):
            return
        # get the VHSolver object
        solver = getVHSolver()
        if solver is None:
             return
        FreeCAD.Console.PrintMessage(translate("EM","Starting voxelization of conductor ") + self.Object.Label + "...\n")
        # get global parameters from the VHSolver object
        gbbox = solver.Proxy.getGlobalBBox()
        delta = solver.Proxy.getDelta()
        voxelSpace = solver.Proxy.getVoxelSpace()
        if voxelSpace is None:
            FreeCAD.Console.PrintWarning(translate("EM","VoxelSpace not valid, cannot voxelize conductor\n"))
            return
        # get this object bbox
        bbox = self.Object.Base.Shape.BoundBox
        if not gbbox.isInside(bbox):
            FreeCAD.Console.PrintError(translate("EM","Internal error: conductor bounding box is larger than the global bounding box. Cannot voxelize conductor.\n"))
            return
        # first of all, must remove all previous instances of the conductor in the voxel space
        voxelSpace[voxelSpace==self.Object.CondIndex] = 0
        # now must find the voxel set that contains the object bounding box
        # find the voxel that contains the bbox min point
        min_x = int((bbox.XMin - gbbox.XMin)/delta)
        min_y = int((bbox.YMin - gbbox.YMin)/delta)
        min_z = int((bbox.ZMin - gbbox.ZMin)/delta)
        # find the voxel that contains the bbox max point
        # (if larger than the voxelSpace, set to voxelSpace max dim,
        # we already verified that 'bbox' fits into 'gbbox')
        vs_size = voxelSpace.shape
        max_x = min(int((bbox.XMax - gbbox.XMin)/delta), vs_size[0]-1)
        max_y = min(int((bbox.YMax - gbbox.YMin)/delta), vs_size[1]-1)
        max_z = min(int((bbox.ZMax - gbbox.ZMin)/delta), vs_size[2]-1)
        # if the Base object is a Part::Box, just mark all the voxels
        # inside the bounding box as belonging to the conductor
        if self.Object.Base.TypeId == "Part::Box":
            voxelSpace[min_x:max_x,min_y:max_y,min_z:max_z] = self.Object.CondIndex
        else:
            # and now find which voxel is inside the object 'self.Object.Base',
            # sampling based on the voxel centers
            voxelIndices = [ (step_x,step_y,step_z) for step_x in range(min_x,max_x+1)
                                for step_y in range(min_y,max_y+1)
                                for step_z in range(min_z,max_z+1)
                                if self.Object.Base.Shape.isInside(Vector(gbbox.XMin + step_x * delta + delta/2.0,
                                gbbox.YMin + step_y * delta + delta/2.0,
                                gbbox.ZMin + step_z * delta + delta/2.0),0.0,True)]
            # mark the relevant voxels with the 'CondIndex'
            # note that as Python3 zip() returns an iterator, need to build the list of indices explicitly,
            # but then we need to move this to a tuple to avoid a Python3 warning
            voxelSpace[tuple([x for x in zip(*voxelIndices)])] = self.Object.CondIndex
        # flag as voxelized
        self.Object.isVoxelized = True
        # if just voxelized, cannot show voxeld; and if there was an old shell representing
        # the previoius voxelization, must clear it
        self.Object.ShowVoxels = False
        FreeCAD.Console.PrintMessage(translate("EM","Voxelization of the conductor completed.\n"))

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

    def getBBox(self):
        ''' Retrieves the bounding box containing the base objects

            Returns a FreeCAD::BoundBox
    '''
        bbox = FreeCAD.BoundBox()
        if self.Object.Base is not None:
            if hasattr(self.Object.Base,"Shape"):
                bbox = self.Object.Base.Shape.BoundBox
        return bbox

    def getCondIndex(self):
        ''' Retrieves the conductor index.

            Returns the int16 conductor index.
    '''
        return self.Object.CondIndex

    def setVoxelState(self,isVoxelized):
        ''' Sets the voxelization state.
    '''
        self.Object.isVoxelized = isVoxelized

    def serialize(self,fid,isSupercond):
        ''' Serialize the object to the 'fid' file descriptor

        'fid' is the file descriptor
        'isSupercond' is a boolean indicating if the input file must contain
            superconductor lambda values (even if for some conductors this may be zero)
    '''
        if self.Object.isVoxelized == True:
            solver = getVHSolver()
            if solver is None:
                 return
            # get global parameters from the VHSolver object
            gbbox = solver.Proxy.getGlobalBBox()
            delta = solver.Proxy.getDelta()
            voxelSpace = solver.Proxy.getVoxelSpace()
            # get this object bbox
            bbox = self.Object.Base.Shape.BoundBox
            if not gbbox.isInside(bbox):
                FreeCAD.Console.PrintError(translate("EM","Conductor bounding box is larger than the global bounding box. Cannot serialize VHConductor.\n"))
                return
            # now must find the voxel set that contains the object bounding box
            # find the voxel that contains the bbox min point
            min_x = int((bbox.XMin - gbbox.XMin)/delta)
            min_y = int((bbox.YMin - gbbox.YMin)/delta)
            min_z = int((bbox.ZMin - gbbox.ZMin)/delta)
            # find the voxel that contains the bbox max point
            # (if larger than the voxelSpace, set to voxelSpace max dim,
            # we already verified that 'bbox' fits into 'gbbox')
            vs_size = voxelSpace.shape
            max_x = min(int((bbox.XMax - gbbox.XMin)/delta), vs_size[0]-1)
            max_y = min(int((bbox.YMax - gbbox.YMin)/delta), vs_size[1]-1)
            max_z = min(int((bbox.ZMax - gbbox.ZMin)/delta), vs_size[2]-1)
            # and now find which voxel belongs to this VHConductor
            voxCoords = np.argwhere(voxelSpace[min_x:max_x+1, min_y:max_y+1, min_z:max_z+1]==self.Object.CondIndex)
            # remark: VoxHenry voxel tensor is 1-based, not 0-based. Must add 1
            voxCoords = voxCoords + 1
            # and add the base offset
            voxCoords[:,0] = voxCoords[:,0]+min_x
            voxCoords[:,1] = voxCoords[:,1]+min_y
            voxCoords[:,2] = voxCoords[:,2]+min_z
            # now must add the information about the 'CondIndex' value:
            voxCoordsSize = voxCoords.shape
            # check if we must output lambda values or not
            if isSupercond:
                # first create a new matrix with an additional column full of 'Sigma'
                voxCoordsAndCond = np.full((voxCoordsSize[0],voxCoordsSize[1]+2),self.Object.Sigma,np.float64)
                # add the lambda values (note that since there is one column only, this is treated as an array in numpy, i.e. row-like)
                voxCoordsAndCond[:,-1] = np.full(voxCoordsSize[0],self.Object.Lambda.getValueAs('m'),np.float64)
                # then copy in the first 2 columns the voxCoords
                # REMARK: this is now a float64 array! Cannot contain int64 values without loss of precision
                # but up to 32 bits this should be ok
                voxCoordsAndCond[:,:-2] = voxCoords
                # finally output the voxels
                np.savetxt(fid, voxCoordsAndCond, fmt="V %d %d %d %g %g")
            else:
                # first create a new matrix with an additional column full of 'Sigma'
                voxCoordsAndCond = np.full((voxCoordsSize[0],voxCoordsSize[1]+1),self.Object.Sigma,np.float64)
                # then copy in the first 2 columns the voxCoords
                # REMARK: this is now a float64 array! Cannot contain int64 values without loss of precision
                # but up to 32 bits this should be ok
                voxCoordsAndCond[:,:-1] = voxCoords
                # finally output the voxels
                np.savetxt(fid, voxCoordsAndCond, fmt="V %d %d %d %g")
        else:
            FreeCAD.Console.PrintWarning(translate("EM","VHConductor object not voxelized, cannot serialize ") + str(self.Object.Label) + "\n")

    def __getstate__(self):
        # JSON does not understand FreeCAD.Vector, so need to convert to tuples
        shapePointsJSON = [(x[0],x[1],x[2]) for x in self.shapePoints]
        dictForJSON = {'sp':shapePointsJSON,'type':self.Type}
        #FreeCAD.Console.PrintMessage("Save\n"+str(dictForJSON)+"\n") #debug
        return dictForJSON

    def __setstate__(self,dictForJSON):
        if dictForJSON:
            #FreeCAD.Console.PrintMessage("Load\n"+str(dictForJSON)+"\n") #debug
            # no need to convert back to FreeCAD.Vectors, 'shapePoints' can also be tuples
            self.shapePoints = dictForJSON['sp']
            self.Type = dictForJSON['type']

class _ViewProviderVHConductor:
    def __init__(self, vobj):
        ''' Set this object to the proxy object of the actual view provider '''
        vobj.Proxy = self
        self.VObject = vobj
        self.Object = vobj.Object

    def attach(self, vobj):
        ''' Setup the scene sub-graph of the view provider, this method is mandatory '''
        #FreeCAD.Console.PrintMessage("ViewProvider attach()\n") # debug
        # on restore, self.Object is not there anymore (JSON does not serialize complex objects
        # members of the class, so __getstate__() and __setstate__() skip them);
        # so we must "re-attach" (re-create) the 'self.Object'
        self.VObject = vobj
        self.Object = vobj.Object
        # actual representation
        self.switch = coin.SoSwitch()
        self.hints = coin.SoShapeHints()
        self.style1 = coin.SoDrawStyle()
        self.style2 = coin.SoDrawStyle()
        self.material = coin.SoMaterial()
        self.linecolor = coin.SoBaseColor()
        self.data = coin.SoCoordinate3()
        self.face = coin.SoFaceSet()
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
        self.material.diffuseColor.setValue(self.VObject.ShapeColor[0],self.VObject.ShapeColor[1],self.VObject.ShapeColor[2])
        self.material.transparency = self.VObject.Transparency/100.0
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
        sep.addChild(self.data)
        sep.addChild(self.switch)
        # and finally the two groups, the first is the contour lines,
        # the second is the filled faces, so we can switch between
        # "Flat Lines", "Shaded" and "Wireframe". Note: not implementing "Points"
        group0Line = coin.SoGroup()
        self.switch.addChild(group0Line)
        group0Line.addChild(self.style2)
        group0Line.addChild(self.linecolor)
        group0Line.addChild(self.face)
        group1Face = coin.SoGroup()
        self.switch.addChild(group1Face)
        group1Face.addChild(self.material)
        group1Face.addChild(self.style1)
        group1Face.addChild(self.face)
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
            numpoints = len(self.Object.Proxy.shapePoints)
            # this can be used to reset the number of points to the value actually needed
            # (e.g. shorten the array, or pre-allocate it). However setValue() will automatically
            # increase the array size if needed, and will NOT shorten it if less values are inserted
            # This is less memory efficient, but faster; and in using the points in the SoFaceSet,
            # we specify how many points (vertices) we want out of the total array, so no issue
            # if the array is longer
            #self.data.point.setNum(numpoints)
            self.data.point.setValues(0,numpoints,self.Object.Proxy.shapePoints)
            # 'numvertices' contains the number of vertices used for each face.
            # Here all faces are quadrilaterals, so this is a long array of number '4's
            numvertices = [4 for i in range(int(numpoints/4))]
            # set the number of vertices per each face, for a total of len(numvertices) faces, starting from 0
            # but must first delete all the old values, otherwise the remaining panels with vertices from
            # 'numvertices+1' will still be shown
            self.face.numVertices.deleteValues(0,-1)
            self.face.numVertices.setValues(0,len(numvertices),numvertices)
            #FreeCAD.Console.PrintMessage("numpoints " + str(numpoints) + "; numvertices " + str(numvertices) + "\n") # debug
            #FreeCAD.Console.PrintMessage("self.Object.Proxy.shapePoints " + str(self.Object.Proxy.shapePoints) + "\n") # debug
            #FreeCAD.Console.PrintMessage("self.data.point " + str(self.data.point.get()) + "\n") # debug
            #FreeCAD.Console.PrintMessage("updateData() shape!\n") # debug
        return
       
#    def getDisplayModes(self,obj):
#        '''Return a list of display modes.'''
#        modes=[]
#        modes.append("Shaded")
#        modes.append("Wireframe")
#        return modes

    def onChanged(self, vp, prop):
        ''' If the 'prop' property changed for the ViewProvider 'vp' '''
        #FreeCAD.Console.PrintMessage("ViewProvider onChanged(), property: " + str(prop) + "\n") # debug
        if prop == "ShapeColor":
            #self.color.rgb.setValue(self.VObject.ShapeColor[0],self.VObject.ShapeColor[1],self.VObject.ShapeColor[2])
            self.material.diffuseColor.setValue(self.VObject.ShapeColor[0],self.VObject.ShapeColor[1],self.VObject.ShapeColor[2])
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
            self.material.transparency = self.VObject.Transparency/100.0
        
    def getDefaultDisplayMode(self):
        ''' Return the name of the default display mode. It must be defined in getDisplayModes. '''
        return "Flat Lines"

#    def setDisplayMode(self,mode):
#        return mode

    def claimChildren(self):
        ''' Used to place other objects as children in the tree'''
        c = []
        if hasattr(self,"Object"):
            if hasattr(self.Object,"Base"):
                c.append(self.Object.Base)
        return c

    def getIcon(self):
        ''' Return the icon which will appear in the tree view. This method is optional
        and if not defined a default icon is shown.
        '''
        return os.path.join(iconPath, 'EM_VHConductor.svg')

    def __getstate__(self):
        return None

    def __setstate__(self,state):
        return None

class _CommandVHConductor:
    ''' The EM VoxHenry Conductor (VHConductor) command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'EM_VHConductor.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_VHConductor","VHConductor"),
                'Accel': "E, C",
                'ToolTip': QT_TRANSLATE_NOOP("EM_VHConductor","Creates a VoxHenry Conductor object (voxelized 3D object) from a selected solid base object")}

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
                FreeCAD.ActiveDocument.openTransaction(translate("EM","Create VHConductor"))
                FreeCADGui.addModule("EM")
                FreeCADGui.doCommand('obj=EM.makeVHConductor(FreeCAD.ActiveDocument.'+selobj.Object.Name+')')
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
            FreeCAD.Console.PrintWarning(translate("EM","No valid object found in the selection for the creation of a VHConductor. Nothing done."))

class _CommandVHCondPortVoxelize:
    ''' The EM VoxHenry conductor (VHConductor) and port (VHPort) voxelize command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'EM_VHCondPortVoxelize.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_VHCondPortVoxelize","VHCondPortVoxelize"),
                'Accel': "E, V",
                'ToolTip': QT_TRANSLATE_NOOP("EM_VHCondPortVoxelize","Voxelize the selected VHConductor(s) and VHPort(s)")}

    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        # preferences
        #p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/EM")
        #self.Width = p.GetFloat("Width",200)
        # get the selected object(s)
        selection = FreeCADGui.Selection.getSelectionEx()
        conds = []
        ports = []
        # if selection is not empty
        for selobj in selection:
            # screen the VHConductors and VHPorts
            objType = Draft.getType(selobj.Object)
            if objType == "VHConductor":
                conds.append(selobj.Object)
            elif objType == "VHPort":
                ports.append(selobj.Object)
        if len(conds) > 0 or len(ports) > 0:
            FreeCAD.ActiveDocument.openTransaction(translate("EM","Voxelize VHConductors and VHPorts"))
            FreeCADGui.addModule("EM")
            for cond in conds:
                FreeCADGui.doCommand('FreeCAD.ActiveDocument.'+cond.Name+'.Proxy.voxelizeConductor()')
            for port in ports:
                FreeCADGui.doCommand('FreeCAD.ActiveDocument.'+port.Name+'.Proxy.voxelizePort()')
            FreeCAD.ActiveDocument.commitTransaction()
        # recompute the document (assuming something has changed; otherwise this is dummy)
        FreeCAD.ActiveDocument.recompute()

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_VHConductor',_CommandVHConductor())
    FreeCADGui.addCommand('EM_VHCondPortVoxelize',_CommandVHCondPortVoxelize())
