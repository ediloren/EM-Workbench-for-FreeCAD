#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2017                                                    *  
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

import FreeCAD, Mesh, Draft, Part, os
#from FreeCAD import Vector

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtGui
else:
    def translate(ctxt,txt):
        return txt

__title__="FreeCAD E.M. FasterCap Importer"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

DEF_FOLDER = "."
COLORMAP_LEN = 256

def import_fastercap(filename, folder=DEF_FOLDER, use_mesh=True):
    '''Import file in FasterCap format as Mesh or Part.compound
        
    'filename' is the name of the export file
    'folder' is the folder where the file resides
        
    Example:
    fastercapObj = import_fastercap('cube.txt')
'''
     
    # 
    # this importer is a Python converted version of the FasterCap C++ import function
    #
    
    if not os.path.isdir(folder):
        FreeCAD.Console.PrintMessage("Error: '" + folder + "' is not a valid folder\n")
        return
        
    if not os.path.exists(folder + os.sep + filename):
        FreeCAD.Console.PrintMessage("Error: '" + filename + "' is not a valid file in the directory " + folder + "\n")
        return
        
    try:
        with open(folder + os.sep + filename, 'r') as fid:
            # reset the list of triangle vertexes
            panelVertexes = []
            chargeDensity = []
            # and scan all the file
            for i, line in enumerate(fid.readlines()):
                # if first line, or empty line, skip
                if i == 0 or line in ['', '\n', '\r\n']:
                    continue
                # now check for actual statements
                #
                # first split the line into the components
                splitLine = line.split()
                # if the line was actually composed only by separators, continue
                if len(splitLine) == 0:
                    continue

                # then check content
                #
                # if triangle
                if splitLine[0] == 'T':
                    try:
                        # if using mesh, we need a flat list of vertexed, that will be used in triplets
                        # to build the triangular-only mesh faces
                        if use_mesh == True:
                            panelVertexes.extend( [ [float(splitLine[2]), float(splitLine[3]), float(splitLine[4])],
                                                    [float(splitLine[5]), float(splitLine[6]), float(splitLine[7])],
                                                    [float(splitLine[8]), float(splitLine[9]), float(splitLine[10])] ])
                        # if using faces, we need FreeCAD.Vector or tuple of three floats for each vertex, in a vector
                        # with as many elements as the vertexes of the polygon supporting the face
                        else:
                            panelVertexes.append( [ (float(splitLine[2]), float(splitLine[3]), float(splitLine[4])),
                                                    (float(splitLine[5]), float(splitLine[6]), float(splitLine[7])),
                                                    (float(splitLine[8]), float(splitLine[9]), float(splitLine[10])) ])
                    except (IndexError, ValueError):
                        FreeCAD.Console.PrintMessage("Error on line " + format(i) + " : " + line + "\n")   
                    # if there is trailing charge density information, store it
                    if len(splitLine) >= 12:
                        chargeDensity.append(float(splitLine[11]))
                # if quadrilateral
                if splitLine[0] == 'Q':
                    try:
                        if use_mesh == True:
                            panelVertexes.extend( [ [float(splitLine[2]), float(splitLine[3]), float(splitLine[4])],
                                                    [float(splitLine[5]), float(splitLine[6]), float(splitLine[7])],
                                                    [float(splitLine[8]), float(splitLine[9]), float(splitLine[10])],
                                                    [float(splitLine[2]), float(splitLine[3]), float(splitLine[4])],
                                                    [float(splitLine[8]), float(splitLine[9]), float(splitLine[10])],
                                                    [float(splitLine[11]), float(splitLine[12]), float(splitLine[13])] ])
                            # if there is trailing charge density information, store it
                            if len(splitLine) >= 15:
                                # add twice, as a quadrilateral panel spits into two triangles in a triangular mesh
                                chargeDensity.extend([float(splitLine[14]), float(splitLine[14])])
                        else:
                            panelVertexes.extend( [[ (float(splitLine[2]), float(splitLine[3]), float(splitLine[4])),
                                                     (float(splitLine[5]), float(splitLine[6]), float(splitLine[7])),
                                                     (float(splitLine[8]), float(splitLine[9]), float(splitLine[10])),
                                                     (float(splitLine[11]), float(splitLine[12]), float(splitLine[13])) ]])              
                            # if there is trailing charge density information, store it
                            if len(splitLine) >= 15:
                                chargeDensity.append(float(splitLine[14]))
                    except ValueError:
                        FreeCAD.Console.PrintMessage("Error on line " + format(i) + " : " + line + "\n")  
                    # if there is trailing charge density information, store it
                    if len(splitLine) >= 15:
                        chargeDensity.append(float(splitLine[14]))

            fid.closed

    except OSError as err:
        FreeCAD.Console.PrintMessage("OS error: " + format(err) + "\n")
        return
                
    if use_mesh == True:
        # now create the mesh. As of FreeCAD 0.16 we cannot color the mesh faces individually,
        # so we'll ignore the charge information, even if present
        fastercapMesh = Mesh.Mesh(panelVertexes)
        # and show it
        Mesh.show(fastercapMesh)
        return fastercapMesh
    else:
        # check if there is charge information
        if len(chargeDensity) > 0:
            # check if every panel has the info
            if len(chargeDensity) != len(panelVertexes):
                FreeCAD.Console.PrintMessage("\nWarning: charge densities vector has length " + 
                                          format(len(chargeDensity)) + " while panels are " +
                                          format(len(panelVertexes)))
                chargeDensity = []
        # create faces
        facelist = []
        for panel in panelVertexes:
            # to create closed wires, the last point should be identical to the first
            wirepoly = Part.makePolygon(panel + [panel[0]])
            face = Part.Face(wirepoly)
            facelist.append(face)
        # cannot use a shell, otherwise face order will be all scrambled up,
        # as Part will stitch faces when building the shell, cutting the 
        # edges where there are other triangle vertexes in contact, and 
        # doing so changes the face order
        #shellObj = Part.makeShell(facelist)
        # a compound instead will just contain a list of faces
        compObj = Part.makeCompound(facelist)
        # might use "Part.show(compObj)" but we need access to the Part::Feature 'featObj'
        # to be able to change its ViewObject properties
        doc = App.ActiveDocument
        partFeatObj = doc.addObject("Part::Feature","FasterCap_Compound")
        partFeatObj.Shape = compObj
        doc.recompute() 
        # add density color
        if len(chargeDensity) > 0:
            # create colormap
            gradTable = [ (0.0, 1.0, 1.0), (0.0, 0.0, 1.0),
                          (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0)]
            colorMap = colormap(gradTable)
            
            #
            # create gradient table (debug only). Should implement using Pivy to have a fixed table at the side
            #~ facelist = []
            #~ for i in range(0,256):
                #~ wirepoly = Part.makePolygon( [ (0.0, i*10.0, 0.0), (0.0, (i+1)*10.0, 0.0), (0.0, (i+1)*10.0, 50.0),
                                               #~ (0.0, i*10.0, 50.0), (0.0, i*10.0, 0.0) ] )
                #~ face = Part.Face(wirepoly)
                #~ facelist.append(face)
            #~ shellGradObj = Part.makeShell(facelist)
            #~ gradObj = doc.addObject("Part::Feature","Gradient_Table")
            #~ gradObj.Shape = shellGradObj
            #~ doc.recompute()
            #~ gradObj.ViewObject.DiffuseColor = [colorMap[x] for x in range(0,256)]
            # end debug
            #
            
            # convert the charge density values into color indexes
            coeff = (COLORMAP_LEN - 1) / (max(chargeDensity) - min(chargeDensity))
            partFeatObj.ViewObject.DiffuseColor = [colorMap[(int)((x-min(chargeDensity))*coeff)] for x in chargeDensity]
        return partFeatObj
        
def colormap(gradientTable, maplen = COLORMAP_LEN):
    '''create a color map based on the given gradient table.
    
  'gradientTable' is a list of colors, represented as 3-tuples
  'maplen' is the length of the map that will be generated.
           The map will consist of 4-tuples, where the 4th
           element (alpha, transparency) is always zero.
    
  Example:
  gradientTable = [ (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
  myMap = colormap(gradientTable)
'''
    colorMap = []
    step = maplen / (float)(len(gradientTable) - 1)
    for i in range(0, maplen):
        gradientIndex = (int) (i/step)
        base = (int) (gradientIndex * step)
        # init color
        color = [0.0, 0.0, 0.0, 0.0]
        for j in range(0,3):
            colorstep = (gradientTable[gradientIndex+1][j] - gradientTable[gradientIndex][j]) / step
            color[j] = gradientTable[gradientIndex][j] + (i-base)*colorstep
            if(color[j] > 1.0):
                color[j] = 1.0
            elif(color[j] < 0.0):
                color[j] = 0.0
        colorMap.append((color[0], color[1], color[2], 0.0))
    return colorMap
    
    