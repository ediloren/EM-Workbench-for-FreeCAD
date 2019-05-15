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


__title__="FreeCAD E.M. Workbench VoxHenry Solver Class"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
#
# default solver bbox color
EMVHSOLVER_DEF_SHAPECOLOR = (0.33,1.0,1.0)
# default solver bbox transparency
EMVHSOLVER_DEF_TRANSPARENCY = 90
# default voxel size
EMVHSOLVER_DEF_DELTA = 1.0
# minimum frequency that can be specified
EMVHSOLVER_DEF_MINFREQ = 1e-6
# maximum index value that can be contained in the voxel space array (made of int16)
EMVHSOLVER_COND_ID_OVERFLOW = 65535
# allowed .units
EMVHSOLVER_UNITS = ["km", "m", "cm", "mm", "um", "nm", "in", "mils"]
EMVHSOLVER_UNITS_VALS = [1e3, 1, 1e-2, 1e-3, 1e-6, 1e-9, 2.54e-2, 1e-3]
EMVHSOLVER_DEFUNITS = "um"
EMVHSOLVER_DEFNHINC = 1
EMVHSOLVER_DEFNWINC = 1
EMVHSOLVER_DEFRW = 2
EMVHSOLVER_DEFRH = 2
EMVHSOLVER_DEFFMIN = 2.5e+09
EMVHSOLVER_DEFFMAX = 1.0e+10
EMVHSOLVER_DEFNDEC = 1
# default input file name
EMVHSOLVER_DEF_FILENAME = "voxhenry_input_file.vhr"

import FreeCAD, FreeCADGui, Mesh, Part, MeshPart, Draft, DraftGeomUtils, os
from FreeCAD import Vector
import math
import numpy as np

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

def makeVHSolver(units=None,fmin=None,fmax=None,ndec=None,folder=None,filename=None,name='VHSolver'):
    ''' Creates a VoxHenry Solver object (all statements needed for the simulation, and container for objects)
    
        'units' is the VoxHenry unit of measurement. Each unit in FreeCad will be
            one unit of the default unit of measurement in VoxHenry.
            Allowed values are: "km", "m", "cm", "mm", "um", "in", "mils".
            Defaults to EMVHSOLVER_DEFUNITS
        'fmin' is the float minimum simulation frequency 
        'fmax' is the float maximum simulation frequency 
        'ndec' is the float value defining how many frequency points per decade
            will be simulated
        'folder' is the folder into which the FastHenry file will be saved.
            Defaults to the user's home path (e.g. in Windows "C:\\Documents
             and Settings\\username\\My Documents", in Linux "/home/username")
        'filename' is the name of the file that will be exported.
            Defaults to EMVHSOLVER_DEF_FILENAME
        'name' is the name of the object
    Example:
        solver = makeVHSolver()
'''
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    obj.Label = translate("EM", name)
    # this adds the relevant properties to the object 
    #'obj' (e.g. 'Base' property) making it a _VHSolver 
    _VHSolver(obj)
    # manage ViewProvider object
    if FreeCAD.GuiUp:
        _ViewProviderVHSolver(obj.ViewObject)
        # set base ViewObject properties to user-selected values (if any)
    if units in EMVHSOLVER_UNITS:
        obj.units = units
    else:
        obj.units = EMVHSOLVER_DEFUNITS
    if fmin is not None:
        obj.fmin = fmin
    else:
        obj.fmin = EMVHSOLVER_DEFFMIN
    if fmax is not None:
        obj.fmax = fmax
    else:
        obj.fmax = EMVHSOLVER_DEFFMAX
    if ndec is not None:
        obj.ndec = ndec
    else:
        obj.ndec = EMVHSOLVER_DEFNDEC
    if filename is not None:
        obj.Filename = filename
    else:
        obj.Filename = EMVHSOLVER_DEF_FILENAME
    if folder is not None:
        obj.Folder = folder
    else:
        # if not specified, default to the user's home path
        # (e.g. in Windows "C:\Documents and Settings\username\My Documents", in Linux "/home/username")
        obj.Folder = FreeCAD.ConfigGet("UserHomePath")
    # hide by default (would show the bbox when valid)
    obj.ViewObject.hide()
    # return the newly created Python object
    return obj

class _VHSolver:
    '''The EM VoxHenry Solver object'''
    def __init__(self, obj):
        ''' Add properties '''
        obj.addProperty("App::PropertyFloat","delta","EM",QT_TRANSLATE_NOOP("App::Property","Voxel size dimension ('delta' parameter in VoxHenry)"))
        obj.addProperty("App::PropertyInteger","VoxelSpaceX","EM",QT_TRANSLATE_NOOP("App::Property","Voxel space dimension along X (read-only)"),1)
        obj.addProperty("App::PropertyInteger","VoxelSpaceY","EM",QT_TRANSLATE_NOOP("App::Property","Voxel space dimension along Y (read-only)"),1)
        obj.addProperty("App::PropertyInteger","VoxelSpaceZ","EM",QT_TRANSLATE_NOOP("App::Property","Voxel space dimension along Z (read-only)"),1)
        obj.addProperty("App::PropertyInteger","VoxelSpaceDim","EM",QT_TRANSLATE_NOOP("App::Property","Voxel space dimension, total number of voxels (read-only)"),1)
        obj.addProperty("App::PropertyEnumeration","units","EM",QT_TRANSLATE_NOOP("App::Property","The measurement units for all the dimensions"))
        obj.addProperty("App::PropertyFloatConstraint","fmin","EM",QT_TRANSLATE_NOOP("App::Property","Lowest simulation frequency"))
        obj.addProperty("App::PropertyFloatConstraint","fmax","EM",QT_TRANSLATE_NOOP("App::Property","Highest simulation frequency"))
        obj.addProperty("App::PropertyFloat","ndec","EM",QT_TRANSLATE_NOOP("App::Property","Number of desired frequency points per decade"))
        obj.addProperty("App::PropertyFloatList","freq","EM",QT_TRANSLATE_NOOP("App::Property","Frequencies for simulation"))
        obj.addProperty("App::PropertyPath","Folder","EM",QT_TRANSLATE_NOOP("App::Property","Folder path for exporting the file in VoxHenry input file format"))
        obj.addProperty("App::PropertyString","Filename","EM",QT_TRANSLATE_NOOP("App::Property","Simulation filename when exporting to VoxHenry input file format"))
        obj.addProperty("App::PropertyBool","voxelSpaceValid","EM",QT_TRANSLATE_NOOP("App::Property","Flags the validity of the voxel space (read only)"),1)
        obj.addProperty("App::PropertyInteger","condIndexGenerator","EM",QT_TRANSLATE_NOOP("App::Property","Latest index for conductor numbering (hidden)"),4)
        obj.Proxy = self
        obj.delta = EMVHSOLVER_DEF_DELTA
        obj.units = EMVHSOLVER_UNITS
        obj.voxelSpaceValid = False
        obj.condIndexGenerator = 0
        obj.freq = []
        obj.fmin = (EMVHSOLVER_DEFFMIN, EMVHSOLVER_DEF_MINFREQ, 1e+20, EMVHSOLVER_DEF_MINFREQ)
        obj.fmax = (EMVHSOLVER_DEFFMAX, EMVHSOLVER_DEF_MINFREQ, 1e+20, EMVHSOLVER_DEF_MINFREQ)
        obj.fmin = EMVHSOLVER_DEFFMIN
        self.bbox = FreeCAD.BoundBox()
        self.voxelSpace = np.full((0,0,0), 0, np.int16)
        self.oldDelta = obj.delta
        self.Type = "VHSolver"
        # save the object in the class, to store or retrieve specific data from it
        # from within the class
        self.Object = obj
        self.justLoaded = False

    def execute(self, obj):
        ''' this method is mandatory. It is called on Document.recompute() 
    '''
        if self.bbox.isValid():
            obj.Shape = Part.makeBox(self.bbox.XLength,self.bbox.YLength,self.bbox.ZLength,Vector(self.bbox.XMin,self.bbox.YMin,self.bbox.ZMin))
            
    def onChanged(self, obj, prop):
        ''' take action if an object property 'prop' changed
    '''
        #FreeCAD.Console.PrintWarning("\n_VHSolver onChanged(" + str(prop)+")\n") #debug
        if not hasattr(self,"Object"):
            # on restore, self.Object is not there anymore (JSON does not serialize complex objects
            # members of the class, so __getstate__() and __setstate__() skip them);
            # so we must "re-attach" (re-create) the 'self.Object'
            self.Object = obj
        if prop == "delta":
            # at creation 'oldDelta' does not yet exist (created after 'delta')
            if hasattr(self,"oldDelta"):
                if obj.delta != self.oldDelta:
                    self.oldDelta = obj.delta
                    # if changing 'Delta', must flag the voxel space as invalid
                    obj.voxelSpaceValid = False
                    self.flagVoxelizationInvalidAll()
        if prop == "VoxelSpaceX" or prop == "VoxelSpaceY" or prop == "VoxelSpaceZ" or prop == "VoxelSpaceDim":
            # if just changed read-only properties, clear the recompute flag (not needed)
            obj.purgeTouched()
        if prop == "fmin" or prop == "fmax" or prop == "ndec":
            if hasattr(obj,"fmin") and hasattr(obj,"fmax") and hasattr(obj,"ndec"):
                if self.Object.fmin > EMVHSOLVER_DEF_MINFREQ and self.Object.ndec > 0.0:
                    # calculate all the frequency points
                    # first calculate how many decades
                    decades = math.log10(self.Object.fmax / self.Object.fmin)
                    # then the total number of points, knowing the decades and the number of points per decade
                    npoints = int(decades * self.Object.ndec)+1
                    # step per decade
                    logofstep = 1.0/self.Object.ndec
                    # finally the frequencies
                    self.Object.freq = [self.Object.fmin*math.pow(10,m*logofstep) for m in range(0,npoints)]
                else:
                    self.Object.freq = [1]
                
    def computeContainingBBox(self):
        ''' Get the bounding box containing all the VHConductors in the document
                   
            Returns the global bounding box.
            If there are no VHConductors, or if the VHConductors Base objects have no Shape,
            the returned BoundBox is invalid (.isValid() on the returned BoundBox gives False)
    '''
        # create an empty bbox
        gbbox = FreeCAD.BoundBox()
        # get the document containing this object
        doc = self.Object.Document
        if doc is None:
            FreeCAD.Console.PrintWarning(translate("EM","No active document available. Cannot compute containing BBox."))
        else:
            # get all the VHConductors
            conds = [obj for obj in doc.Objects if Draft.getType(obj) == "VHConductor"]
            for obj in conds:
                gbbox.add(obj.Proxy.getBBox())
        # if the the old bbox or the newly computed bbox is invalid, flag the voxel space as invalid
        if (not gbbox.isValid()) or (not self.bbox.isValid()):
            self.Object.voxelSpaceValid = False
        else:
            # if we just re-loaded the model, do not flag the bbox as invalid.
            # the problem is that the Shape.BoundBox of the base objects of the VHConductors
            # can be different if the object actually has a visible shape or not.
            # At load time, if the object is invisible, its boundbox may be different. 
            # However, if we knew it was valid at save time, no reason to invalidate it
            if not self.justLoaded:
                if (not gbbox.isInside(self.bbox)) and (not self.bbox.isInside(gbbox)):
                    self.Object.voxelSpaceValid = False
            else:
                self.justLoaded = False
        self.bbox = gbbox
        return gbbox

    def createVoxelSpace(self, bbox=None, delta=None):
        ''' Creates the voxel tensor (3D array) in the given bounding box
        
            'bbox' is the overall FreeCAD.BoundBox bounding box
            'delta' is the voxels size length
            
            Returns a voxel tensor as a Numpy 3D array.
            If gbbox is None, returns None
    '''
        if bbox is None:
            return None
        if not bbox.isValid():
            return None
        if delta is None:
            return None
        if delta <= 0.0:
            return None
        # add 1.0 to always cover the bbox space with the voxels
        stepsX = int(bbox.XLength/delta + 1.0)
        stepsY = int(bbox.YLength/delta + 1.0)
        stepsZ = int(bbox.ZLength/delta + 1.0)
        # store info in the properties visible to the user (but read-only)
        self.Object.VoxelSpaceX = stepsX
        self.Object.VoxelSpaceY = stepsY
        self.Object.VoxelSpaceZ = stepsZ
        self.Object.VoxelSpaceDim = stepsX*stepsY*stepsZ
        # create the 3D array of nodes as 16-bit integers (max 65k different conductivities)
        voxelSpace=np.full((stepsX+1,stepsY+1,stepsZ+1), 0, np.int16)
        return voxelSpace

    def getVoxelSpace(self,force=False):
        ''' Retrieves the voxel space. If not computed yet, or invalid, forces computation.
            
            'force' causes full recalculation of both the bbox and the voxel space
            
            Returns the voxel space tensor as a Numpy 3D array. If impossible to calculate, returns 'None'
    '''
        # get the document containing this object
        doc = self.Object.Document
        if doc is None:
            FreeCAD.Console.PrintWarning(translate("EM","No active document available. Cannot compute the voxel space."))
            return None
        # first re-compute the global bbox. This may flag the voxel space as invalid.
        self.computeContainingBBox()
        # if the bounding box is invalid, no voxel space, no matter what
        if not self.bbox.isValid():
            self.voxelSpace = np.full((0,0,0), 0, np.int16)
        # else if voxel space invalid, or forcing recalculation, let's compute it
        elif (self.voxelSpace.size == 0) or (not self.Object.voxelSpaceValid) or force:
            # create voxel space
            self.voxelSpace = self.createVoxelSpace(self.bbox, self.Object.delta)
            self.Object.voxelSpaceValid = True
            # now flag all VHConductor and VHPort voxelizations as invalid
            # get all the VHConductors
            conds = [obj for obj in doc.Objects if Draft.getType(obj) == "VHConductor"]
            for obj in conds:
                obj.Proxy.flagVoxelizationInvalid()
            # get all the VHPorts
            ports = [obj for obj in doc.Objects if Draft.getType(obj) == "VHPort"]
            for obj in ports:
                obj.Proxy.flagVoxelizationInvalid()
        # return the voxel space (may also be None)
        return self.voxelSpace

    def getGlobalBBox(self):
        ''' Retrieves the bounding box. If not calculated yet, forces calculation
        
            Returns the global bbox as FreeCAD.BoundBox class
    '''
        return self.computeContainingBBox()
        
    def getDelta(self):
        ''' Retrieves the voxel size.
        
            Returns the voxel size float value 'delta'.
    '''
        return self.Object.delta

    def isSupercond(self):
        ''' Check if there is any VHConductor specifying a lambda value (in this case,
            must treat the system as containing superconductors)
                   
            Returns boolean 'True' if there are superconductors
    '''
        isSupercond = False
        # get the document containing this object
        doc = self.Object.Document
        if doc is None:
            FreeCAD.Console.PrintWarning(translate("EM","No active document available. Cannot check if there are superconductors."))
        else:
            # get all the VHConductors
            conds = [obj for obj in doc.Objects if Draft.getType(obj) == "VHConductor"]
            for obj in conds:
                if obj.Lambda.Value > 0.0:
                    isSupercond = True
                    break
        return isSupercond

    def flagVoxelSpaceInvalid(self):
        ''' Flags the voxel space as invalid
    '''
        self.Object.voxelSpaceValid = False

    def getNextCondIndex(self):
        ''' Generates a unique conductor index for marking the different VHConductors in the voxel space.
        
            Returns a unique integer.
    '''
        self.Object.condIndexGenerator = self.Object.condIndexGenerator + 1
        if self.Object.condIndexGenerator > EMVHSOLVER_COND_ID_OVERFLOW:
            FreeCAD.Console.PrintWarning(translate("EM","Conductor index generator overflowed int16 capacity! Cannot reliably mark VHConductors any more in the voxel space"))
        return self.Object.condIndexGenerator

    def voxelizeAll(self):
        ''' Voxelize all VHConductors and VHPorts in the voxelSpace of the VHSolver object
    '''
        # get the document containing this object
        doc = self.Object.Document
        if doc is None:
            FreeCAD.Console.PrintWarning(translate("EM","No active document available. Cannot voxelize conductors."))
            return None
        # get all VHConductors and VHPorts
        conds = [obj for obj in doc.Objects if Draft.getType(obj) == "VHConductor"]
        for cond in conds:
            cond.Proxy.voxelizeConductor()
        ports = [obj for obj in doc.Objects if Draft.getType(obj) == "VHPort"]
        for port in ports:
            port.Proxy.voxelizePort()

    def flagVoxelizationInvalidAll(self):
        ''' Invalidate the voxelization of all VHConductors and VHPorts
    '''
        # get the document containing this object
        doc = self.Object.Document
        if doc is None:
            FreeCAD.Console.PrintWarning(translate("EM","No active document available. Cannot invalidate conductors."))
            return None
        # get all VHConductors and VHPorts
        conds = [obj for obj in doc.Objects if Draft.getType(obj) == "VHConductor"]
        for cond in conds:
            cond.Proxy.flagVoxelizationInvalid()
        ports = [obj for obj in doc.Objects if Draft.getType(obj) == "VHPort"]
        for port in ports:
            port.Proxy.flagVoxelizationInvalid()

    def serialize(self,fid):
        ''' Serialize the object to the 'fid' file descriptor
    '''
        fid.write("* VoxHenry input file created using FreeCAD's ElectroMagnetic Workbench\n")
        fid.write("* See http://www.freecad.org and http://www.fastfieldsolvers.com\n")
        fid.write("\n")
        fid.write("* Frequency points (Hz)\n")
        fid.write("freq=")
        for freq in self.Object.freq:
            fid.write(" "+str(freq))
        fid.write("\n")
        fid.write("\n")
        fid.write("* Voxel size (m)\n")
        scaledDelta = self.Object.delta * EMVHSOLVER_UNITS_VALS[EMVHSOLVER_UNITS.index(self.Object.units)]
        fid.write("dx=" + str(scaledDelta) + "\n")
        fid.write("\n")
        fid.write("* Voxel grid dimension in voxel units: x, y, z\n")
        fid.write("LMN=" + str(self.Object.VoxelSpaceX) + "," + str(self.Object.VoxelSpaceY) + "," + str(self.Object.VoxelSpaceZ) + "\n")
        fid.write("\n")

    def __getstate__(self):
        voxelspacedim = (self.Object.VoxelSpaceX+1,self.Object.VoxelSpaceY+1,self.Object.VoxelSpaceZ+1)
        bboxcoord = (self.bbox.XMin,self.bbox.YMin,self.bbox.ZMin,self.bbox.XMax,self.bbox.YMax,self.bbox.ZMax)
        voxelSpaceConds =  self.voxelSpace.nonzero()
        voxelSpaceVals = self.voxelSpace[voxelSpaceConds].tolist()
        voxelSpaceCoordX = voxelSpaceConds[0].tolist()
        voxelSpaceCoordY = voxelSpaceConds[1].tolist()
        voxelSpaceCoordZ = voxelSpaceConds[2].tolist()
        dictForJSON = {'oldD':self.oldDelta,'vsDim':voxelspacedim,'vsX':voxelSpaceCoordX,'vsY':voxelSpaceCoordY,'vsZ':voxelSpaceCoordZ,'vsVals':voxelSpaceVals,'bbox':bboxcoord,'type':self.Type}
        #FreeCAD.Console.PrintMessage("Save\n"+str(dictForJSON)+"\n") #debug
        return dictForJSON

    def __setstate__(self,dictForJSON):
        if dictForJSON:
            #FreeCAD.Console.PrintMessage("Load\n"+str(dictForJSON)+"\n") #debug
            self.oldDelta = dictForJSON['oldD']
            bboxcoord = dictForJSON['bbox']
            self.bbox = FreeCAD.BoundBox(bboxcoord[0],bboxcoord[1],bboxcoord[2],bboxcoord[3],bboxcoord[4],bboxcoord[5])
            voxelspacedim = dictForJSON['vsDim']        
            self.voxelSpace = np.full(voxelspacedim,0,np.int16)
            voxelSpaceConds = (np.array(dictForJSON['vsX']),np.array(dictForJSON['vsY']),np.array(dictForJSON['vsZ']))
            self.voxelSpace[voxelSpaceConds] = dictForJSON['vsVals']
            self.Type = dictForJSON['type']
        self.justLoaded = True
            
class _ViewProviderVHSolver:
    def __init__(self, vobj):
        ''' Set this object to the proxy object of the actual view provider '''
        vobj.ShapeColor = EMVHSOLVER_DEF_SHAPECOLOR
        vobj.Transparency = EMVHSOLVER_DEF_TRANSPARENCY
        vobj.Proxy = self

    def attach(self, obj):
        ''' Setup the scene sub-graph of the view provider, this method is mandatory '''
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
        return os.path.join(iconPath, 'EM_VHSolver.svg')

    def __getstate__(self):
        return None

    def __setstate__(self,state):
        return None
            
class _CommandVHSolver:
    ''' The EM VoxHenry Solver command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'EM_VHSolver.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_VHSolver","VHSolver"),
                'Accel': "E, Y",
                'ToolTip': QT_TRANSLATE_NOOP("EM_VHSolver","Creates a VoxHenry Solver object")}
                
    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        # preferences
        #p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/EM")
        #self.Width = p.GetFloat("Width",200)
        FreeCAD.ActiveDocument.openTransaction(translate("EM","Create VHSolver"))
        FreeCADGui.addModule("EM")
        FreeCADGui.doCommand('obj=EM.makeVHSolver()')
        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()

class _CommandVHVoxelizeAll:
    ''' The EM VoxHenry 'voxelize all' command definition
'''
    def GetResources(self):
        return {'Pixmap'  : os.path.join(iconPath, 'EM_VHVoxelizeAll.svg') ,
                'MenuText': QT_TRANSLATE_NOOP("EM_VHVoxelizeAll","VHVoxelizeAll"),
                'Accel': "E, W",
                'ToolTip': QT_TRANSLATE_NOOP("EM_VHVoxelizeAll","Voxelize all the VHConductors and VHPorts in the document")}
                
    def IsActive(self):
        return not FreeCAD.ActiveDocument is None

    def Activated(self):
        # preferences
        #p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/EM")
        #self.Width = p.GetFloat("Width",200)
        # get the selected object(s)
        if FreeCAD.ActiveDocument is not None:
            if hasattr(FreeCAD.ActiveDocument, 'VHSolver'):
                FreeCAD.ActiveDocument.openTransaction(translate("EM","Voxelize all VHConductors and VHPorts"))
                FreeCADGui.addModule("EM")
                FreeCADGui.doCommand('FreeCAD.ActiveDocument.VHSolver.Proxy.voxelizeAll()')
                FreeCAD.ActiveDocument.commitTransaction()
                # recompute the document (assuming something has changed; otherwise this is dummy)
                FreeCAD.ActiveDocument.recompute()

if FreeCAD.GuiUp:
    FreeCADGui.addCommand('EM_VHSolver',_CommandVHSolver())
    FreeCADGui.addCommand('EM_VHVoxelizeAll',_CommandVHVoxelizeAll())
