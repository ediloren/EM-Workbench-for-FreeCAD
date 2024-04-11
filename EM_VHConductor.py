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

import math

# copper conductivity 1/(m*Ohms)
EMVHSOLVER_DEF_SIGMA = 5.8e7

import FreeCAD, FreeCADGui, Part, Draft, DraftGeomUtils, os
import DraftVecUtils
import Mesh
import MeshPart
from FreeCAD import Vector
import numpy as np
import time
from pivy import coin
import EM
from scipy import ndimage

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
    solver = EM.getVHSolver(True)
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


def intersects_box(triangle, box_center, box_extents):
    X, Y, Z = 0, 1, 2

    # Translate triangle as conceptually moving AABB to origin
    v0 = triangle[0] - box_center
    v1 = triangle[1] - box_center
    v2 = triangle[2] - box_center

    # Compute edge vectors for triangle
    f0 = triangle[1] - triangle[0]
    f1 = triangle[2] - triangle[1]
    f2 = triangle[0] - triangle[2]

    ## region Test axes a00..a22 (category 3)

    # Test axis a00
    a00 = np.array([0, -f0[Z], f0[Y]])
    p0 = np.dot(v0, a00)
    p1 = np.dot(v1, a00)
    p2 = np.dot(v2, a00)
    r = box_extents[Y] * abs(f0[Z]) + box_extents[Z] * abs(f0[Y])
    if (max(-max(p0, p1, p2), min(p0, p1, p2))) > r:
        return False

    # Test axis a01
    a01 = np.array([0, -f1[Z], f1[Y]])
    p0 = np.dot(v0, a01)
    p1 = np.dot(v1, a01)
    p2 = np.dot(v2, a01)
    r = box_extents[Y] * abs(f1[Z]) + box_extents[Z] * abs(f1[Y])
    if (max(-max(p0, p1, p2), min(p0, p1, p2))) > r:
        return False

    # Test axis a02
    a02 = np.array([0, -f2[Z], f2[Y]])
    p0 = np.dot(v0, a02)
    p1 = np.dot(v1, a02)
    p2 = np.dot(v2, a02)
    r = box_extents[Y] * abs(f2[Z]) + box_extents[Z] * abs(f2[Y])
    if (max(-max(p0, p1, p2), min(p0, p1, p2))) > r:
        return False

    # Test axis a10
    a10 = np.array([f0[Z], 0, -f0[X]])
    p0 = np.dot(v0, a10)
    p1 = np.dot(v1, a10)
    p2 = np.dot(v2, a10)
    r = box_extents[X] * abs(f0[Z]) + box_extents[Z] * abs(f0[X])
    if (max(-max(p0, p1, p2), min(p0, p1, p2))) > r:
        return False

    # Test axis a11
    a11 = np.array([f1[Z], 0, -f1[X]])
    p0 = np.dot(v0, a11)
    p1 = np.dot(v1, a11)
    p2 = np.dot(v2, a11)
    r = box_extents[X] * abs(f1[Z]) + box_extents[Z] * abs(f1[X])
    if (max(-max(p0, p1, p2), min(p0, p1, p2))) > r:
        return False

    # Test axis a12
    a11 = np.array([f2[Z], 0, -f2[X]])
    p0 = np.dot(v0, a11)
    p1 = np.dot(v1, a11)
    p2 = np.dot(v2, a11)
    r = box_extents[X] * abs(f2[Z]) + box_extents[Z] * abs(f2[X])
    if (max(-max(p0, p1, p2), min(p0, p1, p2))) > r:
        return False

    # Test axis a20
    a20 = np.array([-f0[Y], f0[X], 0])
    p0 = np.dot(v0, a20)
    p1 = np.dot(v1, a20)
    p2 = np.dot(v2, a20)
    r = box_extents[X] * abs(f0[Y]) + box_extents[Y] * abs(f0[X])
    if (max(-max(p0, p1, p2), min(p0, p1, p2))) > r:
        return False

    # Test axis a21
    a21 = np.array([-f1[Y], f1[X], 0])
    p0 = np.dot(v0, a21)
    p1 = np.dot(v1, a21)
    p2 = np.dot(v2, a21)
    r = box_extents[X] * abs(f1[Y]) + box_extents[Y] * abs(f1[X])
    if (max(-max(p0, p1, p2), min(p0, p1, p2))) > r:
        return False

    # Test axis a22
    a22 = np.array([-f2[Y], f2[X], 0])
    p0 = np.dot(v0, a22)
    p1 = np.dot(v1, a22)
    p2 = np.dot(v2, a22)
    r = box_extents[X] * abs(f2[Y]) + box_extents[Y] * abs(f2[X])
    if (max(-max(p0, p1, p2), min(p0, p1, p2))) > r:
        return False

    ## endregion

    ## region Test the three axes corresponding to the face normals of AABB b (category 1)

    # Exit if...
    # ... [-extents.X, extents.X] and [min(v0.X,v1.X,v2.X), max(v0.X,v1.X,v2.X)] do not overlap
    if max(v0[X], v1[X], v2[X]) < -box_extents[X] or min(v0[X], v1[X], v2[X]) > box_extents[X]:
        return False

    # ... [-extents.Y, extents.Y] and [min(v0.Y,v1.Y,v2.Y), max(v0.Y,v1.Y,v2.Y)] do not overlap
    if max(v0[Y], v1[Y], v2[Y]) < -box_extents[Y] or min(v0[Y], v1[Y], v2[Y]) > box_extents[Y]:
        return False

    # ... [-extents.Z, extents.Z] and [min(v0.Z,v1.Z,v2.Z), max(v0.Z,v1.Z,v2.Z)] do not overlap
    if max(v0[Z], v1[Z], v2[Z]) < -box_extents[Z] or min(v0[Z], v1[Z], v2[Z]) > box_extents[Z]:
        return False

    ## endregion

    ## region Test separating axis corresponding to triangle face normal (category 2)

    plane_normal = np.cross(f0, f1)
    plane_distance = np.abs(np.dot(plane_normal, v0))

    # Compute the projection interval radius of b onto L(t) = b.c + t * p.n
    r = box_extents[X] * abs(plane_normal[X]) + box_extents[Y] * abs(plane_normal[Y]) + box_extents[Z] * abs(
        plane_normal[Z])

    # Intersection occurs when plane distance falls within [-r,+r] interval
    if plane_distance > r:
        return False

    ## endregion

    return True


def get_voxel_center(bb_min, voxel, delta):
    return bb_min + (voxel + 0.5) * delta

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
            solver = EM.getVHSolver()
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
        X, Y, Z = 0, 1, 2
        if self.Object.Base is None:
            return
        if not hasattr(self.Object.Base, "Shape"):
            return
        # get the VHSolver object
        solver = EM.getVHSolver()
        if solver is None:
            return
        FreeCAD.Console.PrintMessage(translate("EM", "Starting voxelization of conductor ") + self.Object.Label + "...\n")
        # get global parameters from the VHSolver object
        gbbox = solver.Proxy.getGlobalBBox()
        gbbox_min = np.array((gbbox.XMin, gbbox.YMin, gbbox.ZMin))
        gbbox_max = np.array((gbbox.XMax, gbbox.YMax, gbbox.ZMax))
        delta = solver.Proxy.getDelta()
        voxelSpace = solver.Proxy.getVoxelSpace()
        if voxelSpace is None:
            FreeCAD.Console.PrintWarning(translate("EM", "VoxelSpace not valid, cannot voxelize conductor\n"))
            return
        # get this object bbox
        bbox = self.Object.Base.Shape.BoundBox
        bbox_min = np.array((bbox.XMin, bbox.YMin, bbox.ZMin))
        bbox_max = np.array((bbox.XMax, bbox.YMax, bbox.ZMax))
        if not gbbox.isInside(bbox):
            FreeCAD.Console.PrintError(translate("EM", "Internal error: conductor bounding box is larger than the global bounding box. Cannot voxelize conductor.\n"))
            return
        # first of all, must remove all previous instances of the conductor in the voxel space
        voxelSpace[voxelSpace == self.Object.CondIndex] = 0
        # now must find the voxel set that contains the object bounding box
        # find the voxel that contains the bbox min point
        local_vs_min = ((bbox_min - gbbox_min)/delta).astype(int)
        # find the voxel that contains the bbox max point
        # (if larger than the voxelSpace, set to voxelSpace max dim,
        # we already verified that 'bbox' fits into 'gbbox')
        local_vs_max = np.min((((bbox_max - gbbox_min) / delta).astype(int),
                              np.array(voxelSpace.shape) - 1),
                              axis=0)
        local_vs_size = local_vs_max - local_vs_min + 1
        # if the Base object is a Part::Box, just mark all the voxels
        # inside the bounding box as belonging to the conductor
        if self.Object.Base.TypeId == "Part::Box" and \
           self.Object.Base.Placement.Rotation.Angle < 1e-12:
            box_start = time.perf_counter()

            # Since we want to sample by voxel centre, our minimum/maximum voxel might be off by one in 1, 2, or dimensions.
            # This would make the voxelized box too big. So check and offset where necessary.
            # first, assume its correct
            partbox_min = local_vs_min
            partbox_max = local_vs_max
            # get the center coordinates of our assumed min/max voxel
            min_voxel_center = get_voxel_center(gbbox_min, local_vs_min, delta)
            max_voxel_center = get_voxel_center(gbbox_min, local_vs_min, delta)
            # make arrays of booleans
            min_too_small = min_voxel_center < bbox_min
            max_too_big = max_voxel_center > bbox_max
            # offset where required. we should only ever be off by one.
            partbox_min[min_too_small] += 1
            partbox_max[max_too_big] -= 1

            voxelSpace[partbox_min[X]:partbox_max[X] + 1,
                       partbox_min[Y]:partbox_max[Y] + 1,
                       partbox_min[Z]:partbox_max[Z] + 1] = self.Object.CondIndex
        else:
            #  Voxelization is done with the Shape.isInside function, sampled on voxel centers.
            #  BUT isInside can be expensive, so to minimize calls to isInside:
            #    1. Make a temporary mesh of the solid
            #    2. Find the set 'A' of voxels that intersect the mesh
            #    3. For all voxels in 'A', set (or not) its conductor index based on isInside
            #    4. Using the voxels 'A', find sets 'B', 'C', ... that are contiguous regions split up by 'A'
            #    5. For region 'R_' in voxel sets 'B', 'C',...
            #      a. Set (or not) 'R_' based on a single arbitrary voxel in 'R' with inSide
            #
            #  The number of isInside calls should be approximately proportional to the conductor surface area.
            #  The result should be identical to calling isInside for every voxel.

            voxel_start = time.perf_counter()

            make_mesh_start = time.perf_counter()
            # make a reasonably fine mesh of the solid
            meshed = MeshPart.meshFromShape(Shape=self.Object.Base.Shape,
                                            LinearDeflection=(delta / 5.0),
                                            AngularDeflection=math.radians(30),
                                            Relative=False)
            make_mesh_time = time.perf_counter() - make_mesh_start
            # FreeCAD.Console.PrintMessage(f"make_mesh_time {make_mesh_time:.1f}, n_facets {meshed.CountFacets}\n")

            # collect all the mesh facet coordinates (these must be triangles)
            facets = np.zeros((meshed.CountFacets, 3, 3))
            for index, facet in enumerate(meshed.Facets):
                facets[index, :, :] = np.array(facet.Points)

            # collect all the voxel-center coordinates
            voxel_centers = np.zeros((local_vs_size[X], local_vs_size[Y], local_vs_size[Z], 3))
            for x in range(local_vs_size[X]):
                for y in range(local_vs_size[Y]):
                    for z in range(local_vs_size[Z]):
                        voxel_centers[x, y, z, :] = get_voxel_center(bb_min=gbbox_min,
                                                                     voxel=np.array((x, y, z)) + local_vs_min,
                                                                     delta=delta)

            # consider every mesh facet, and check for mesh intersections with voxels
            intersection_start = time.perf_counter()
            mesh_intersections = np.zeros(local_vs_size, dtype=bool)
            half_el_size_eps = delta / 2.0 + 1e-14
            half_el_size = np.array((half_el_size_eps, half_el_size_eps, half_el_size_eps))
            for facet_index in range(np.size(facets, 0)):
                # get facet bounding box
                facet_bb_min = np.min(facets[facet_index], 0)
                facet_bb_max = np.max(facets[facet_index], 0)

                # get voxel indices of facet bb points, in conductor-local voxel coordinates
                facet_min_possible_voxel = np.floor((facet_bb_min - gbbox_min) / delta).astype(int) - local_vs_min
                facet_max_possible_voxel = np.floor((facet_bb_max - gbbox_min) / delta).astype(int) - local_vs_min

                # facet_min_possible_voxel = grid.get_voxel_containing_point(facet_bb_min) - np.array((1, 1, 1))
                # facet_min_possible_voxel[facet_min_possible_voxel < 0] = 0  # limit to vox space
                # facet_max_possible_voxel = grid.get_voxel_containing_point(facet_bb_max) + np.array((1, 1, 1))
                # facet_max_possible_voxel = np.min(np.stack((facet_max_possible_voxel, max_vox_index)), 0)  # limit to vox space
                for x in range(facet_min_possible_voxel[X], facet_max_possible_voxel[X] + 1):
                    for y in range(facet_min_possible_voxel[Y], facet_max_possible_voxel[Y] + 1):
                        for z in range(facet_min_possible_voxel[Z], facet_max_possible_voxel[Z] + 1):
                            if mesh_intersections[(x, y, z)]:
                                continue  # already filled. skip checking again

                            # n_intersection_checks = n_intersection_checks + 1
                            if intersects_box(triangle=facets[facet_index, :, :],
                                              box_center=voxel_centers[x, y, z, :],
                                              box_extents=half_el_size):
                                mesh_intersections[(x, y, z)] = True

            intersection_end = time.perf_counter() - intersection_start
            # FreeCAD.Console.PrintMessage(f"intersection time {intersection_end:.1f}\n")

            # Identify contiguous voxel regions
            region_labels, n_features = ndimage.label(~mesh_intersections)
            # FreeCAD.Console.PrintMessage(f"regions: {n_features}\n")

            # Check each region
            for label_index in range(n_features + 1):
                region_indices = np.nonzero(region_labels == label_index)
                region_indices_global = (region_indices[X] + local_vs_min[X],
                                         region_indices[Y] + local_vs_min[Y],
                                         region_indices[Z] + local_vs_min[Z])

                # special case of label == 0. these are the voxels that intersected with the mesh. check each of these
                # voxels individually
                if label_index == 0:
                    region_voxel_count = np.size(region_indices[0])
                    progress_bar = FreeCAD.Base.ProgressIndicator()
                    progress_bar.start(f"Voxelizing {self.Object.Name}...", region_voxel_count)
                    # FreeCAD.Console.PrintMessage(f"Doing {region_voxel_count} isInside checks...\n")
                    inside_checks_start = time.perf_counter()
                    for x, y, z in zip(*region_indices_global):
                        progress_bar.next(True)  # next(True) -> no cancel button on progress bar
                        if self.Object.Base.Shape.isInside(Vector(get_voxel_center(bb_min=gbbox_min,
                                                                                   voxel=np.array((x, y, z)),
                                                                                   delta=delta)),
                                                           0.0,  # tolerance
                                                           True  # check points on faces
                                                           ):
                            voxelSpace[(x, y, z)] = self.Object.CondIndex
                    inside_checks_end = time.perf_counter()
                    # FreeCAD.Console.PrintMessage(f"Average isInside time {1000*(inside_checks_end - inside_checks_start)/region_voxel_count:.3g} milliseconds\n")
                    progress_bar.stop()

                # a contiguous region of voxels that did NOT intersect with the mesh. these can be set all at once
                else:
                    # Check if this whole region should be set by sampling a single voxel
                    first_voxel_coord = np.array((region_indices_global[X][0],
                                                  region_indices_global[Y][0],
                                                  region_indices_global[Z][0]))
                    if self.Object.Base.Shape.isInside(Vector(get_voxel_center(bb_min=gbbox_min,
                                                                               voxel=first_voxel_coord,
                                                                               delta=delta)),
                                                       0.0,  # tolerance
                                                       True  # check points on faces
                                                       ):
                        # This whole region is part of the conductor
                        voxelSpace[region_indices_global] = self.Object.CondIndex

            voxel_end = time.perf_counter()
            n_vox_checks = np.prod(local_vs_size)
            tot_time = voxel_end - voxel_start
            time_per_check_us = 1000000 * tot_time / n_vox_checks
            # FreeCAD.Console.PrintMessage(f"time per vox {time_per_check_us:.2f} usec, {n_vox_checks} vox\n")
            # FreeCAD.Console.PrintMessage(f"tot time {tot_time:.2f} sec\n")
        # flag as voxelized
        self.Object.isVoxelized = True
        # if just voxelized, cannot show voxeld; and if there was an old shell representing
        # the previoius voxelization, must clear it
        self.Object.ShowVoxels = False
        FreeCAD.Console.PrintMessage(translate("EM", "Voxelization of the conductor completed.\n"))

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
            solver = EM.getVHSolver()
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
