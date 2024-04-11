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


__title__="FreeCAD E.M. Workbench global definitions"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

# defines
#
# version information
EM_VERSION = '2.1.0'
# default node color
EMFHNODE_DEF_NODECOLOR = (1.0,0.0,0.0)
# tolerance in degrees when verifying if vectors are parallel
EMFHSEGMENT_PARTOL = 0.01
# tolerance in length
EMFHSEGMENT_LENTOL = 1e-8

import FreeCAD, Part, Draft
from FreeCAD import Vector
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

def getAbsCoordBodyPart(obj,position):
    ''' Retrieve the absolute coordinates of a point belonging to an object, even if in a Body or Part

        'obj': object to which the 'position' is relative
        'position': FreeCAD.Vector 3D position relative to objects that contain 'obj'
            (Note: 'position' is NOT relative to the 'obj.Placement', only to the containers)

        return value: FreeCAD.Vector 3D absolute position
'''
    if obj == None:
        return None
    for parent in obj.InList:
        if parent.TypeId ==  "PartDesign::Body" or parent.TypeId == "App::Part":
            # make the position absolute
            position = parent.Placement.multVec(position)
            # and recursively check upside
            position = getAbsCoordBodyPart(parent,position)
            break
    return position

def makeSegShape(n1,n2,width,height,ww):
    ''' Compute a segment shape given:

        'n1': start node position (Vector)
        'n2': end node position (Vector)
        'width': segment width
        'height': segment height
        'ww': cross-section direction (along width)

        Returns the created Shape
'''
    # do not accept coincident nodes
    if (n2-n1).Length < EMFHSEGMENT_LENTOL:
        return None
    # vector along length
    wl = n2-n1;
    # calculate the vector along the height
    wh = (ww.cross(wl))
    # if cross-section is not defined, by default the width vector
    # is assumed to lie in x-y plane perpendicular to the length.
    # If the length direction is parallel to the z-axis, then
    # the width is assumed along the x-axis.
    # The same is done if 'ww' has been defined parallel to 'wl'
    if ww.Length < EMFHSEGMENT_LENTOL or wh.Length < EMFHSEGMENT_LENTOL:
        # if length parallel to the z-axis (note that getAngle() always returns a value
        # between 0 and 180)
        angle = wl.getAngle(Vector(0,0,1))*FreeCAD.Units.Radian
        if angle < EMFHSEGMENT_PARTOL or angle > 180-EMFHSEGMENT_PARTOL:
            ww = Vector(1,0,0)
        else:
            ww = (wl.cross(Vector(0,0,1))).normalize()
        # and re-calculate 'wh' since we changed 'ww'
        wh = (ww.cross(wl))
    # normalize the freshly calculated 'wh'
    wh.normalize()
    # copy ww as the multiply() method changes the vector on which is called
    wwHalf = Vector(ww)
    # must normalize. We don't want to touch 'ww', as this is user's defined
    wwHalf.normalize()
    wwHalf.multiply(width / 2)
    # copy wh as the multiply() method changes the vector on which is called
    whHalf = Vector(wh)
    whHalf.multiply(height / 2)
    # calculate the vertexes
    v11 = n1 - wwHalf - whHalf
    v12 = n1 + wwHalf - whHalf
    v13 = n1 + wwHalf + whHalf
    v14 = n1 - wwHalf + whHalf
    v21 = n2 - wwHalf - whHalf
    v22 = n2 + wwHalf - whHalf
    v23 = n2 + wwHalf + whHalf
    v24 = n2 - wwHalf + whHalf
    # now make faces
    # front
    poly = Part.makePolygon( [v11,v12,v13,v14,v11])
    face1 = Part.Face(poly)
    # back
    poly = Part.makePolygon( [v21,v24,v23,v22,v21])
    face2 = Part.Face(poly)
    # left
    poly = Part.makePolygon( [v11,v14,v24,v21,v11])
    face3 = Part.Face(poly)
    # right
    poly = Part.makePolygon( [v12,v22,v23,v13,v12])
    face4 = Part.Face(poly)
    # top
    poly = Part.makePolygon( [v14,v13,v23,v24,v14])
    face5 = Part.Face(poly)
    # bottom
    poly = Part.makePolygon( [v11,v21,v22,v12,v11])
    face6 = Part.Face(poly)
    # create a shell. Does not need to be solid.
    segShell = Part.makeShell([face1,face2,face3,face4,face5,face6])
    return segShell

def getVHSolver(createIfNotExisting=False):
    ''' Retrieves the VHSolver object.

        'createIfNotExisting' if True forces the creation of a VHSolver object,
            if not already existing

        Returns the VHSolver object of the current Document. If more than one VHSolver object is present,
        return the first one.
'''
    # get the document containing this object
    doc = FreeCAD.ActiveDocument
    if doc is None:
        FreeCAD.Console.PrintWarning(translate("EM","No active document available. Cannot get any VHSolver object."))
        return None
    solver = [obj for obj in doc.Objects if Draft.getType(obj) == "VHSolver"]
    if solver == []:
        if createIfNotExisting == True:
            solver = EM.makeVHSolver()
            if solver is None:
                FreeCAD.Console.PrintError(translate("EM","Cannot create VHSolver!"))
        else:
            FreeCAD.Console.PrintWarning(translate("EM","Cannot get VHSolver. Is at least one VHSolver object existing?"))
            return None
    else:
        # take the first in the list
        solver = solver[0]
    return solver

