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
from collections import namedtuple
from FreeCAD import Vector

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
AUTOREFINE_MAX_PARSE_LEVEL = 32

# filePosMap members
filePosData = namedtuple('filePosData', ['lineNum', 'filePos'])

# global vars
#
m_lDielNum = 0
m_lCondNum = 0
m_iParseLevel = -1
m_iGroupNum = [1]
m_lGroupDielNum = 0 
m_bUseMesh = True
# number of input panels
m_ulInputPanelNum = 0


def read_fastcap_file(filename, folder=DEF_FOLDER, usePartType='compound'):
    '''Import file in FasterCap format as Mesh or Part.compound
        
    'filename' is the name of the export file
    'folder' is the folder where the file resides
        
    Example:
    fastercapObj = read_fastcap_file('cube.txt')
'''

    # 
    # this function is a Python-converted version of the FasterCap C++ 
    # ReadFastCapFile() import function (and associated functions)
    #

    global m_lDielNum
    global m_lCondNum
    global m_iParseLevel
    global m_iGroupNum
    global m_lGroupDielNum
    global m_sUsePartType
    global m_ulInputPanelNum

    # init global vars
    m_lDielNum = 0
    m_lCondNum = 0
    m_iParseLevel = -1
    m_iGroupNum =  [1 for x in range(0,AUTOREFINE_MAX_PARSE_LEVEL)]
    m_lGroupDielNum = 0
    m_sUsePartType = usePartType
    # init number of input panels
    m_ulInputPanelNum = 0

      
    if not os.path.isdir(folder):
        FreeCAD.Console.PrintMessage("Error: '" + folder + "' is not a valid folder\n")
        return False
        
    if not os.path.exists(folder + os.sep + filename):
        FreeCAD.Console.PrintMessage("Error: '" + filename + "' is not a valid file in the directory " + folder + "\n")
        return False
        
    # understand the type of input file (2D or 3D)
    fileinname =fol
    der + os.sep + filename
    line = ''
    try:
        with open(fileinname, 'r') as fid:
            line = fid.readline()
            fid.closed
    except OSError as err:
        FreeCAD.Console.PrintMessage("OS error: " + format(err) + "\n")
        return False

    # clear filePosMap dictionary
    filePosMap = {}
    if '2d' in line or '2D' in line:
        # passing dummy 'fid' and 'filePosMap' (that must be empty) since
        # there is no parent file
        ret = parse_2D_input_file(fileinname, fid, filePosMap);
    else:
        # passing dummy 'fid' and 'filePosMap' (that must be empty) since
        # there is no parent file
        ret = parse_3D_input_file(fileinname, fid, filePosMap);
    
    return ret
    
def parse_2D_input_file(fileinname, fid, filePosMap, use_mesh):
    
    FreeCAD.Console.PrintMessage("Parse 2D\n")
    return True
    
    
def parse_3D_input_file(fileinname, parentFid, parentFilePosMap, isdiel = False, offset = Vector(0.0, 0.0, 0.0), 
                        outperm = complex(1.0), groupname = '', inperm = complex(1.0), dielrefpoint = Vector(0.0, 0.0, 0.0)):
    
    global m_iParseLevel
    global m_iGroupNum 
    global m_lGroupDielNum
    global m_sUsePartType
    global m_ulInputPanelNum
    
    # increment the recursion level counter
    m_iParseLevel = m_iParseLevel + 1
    
    if m_iParseLevel >= AUTOREFINE_MAX_PARSE_LEVEL:
        FreeCAD.Console.PrintMessage("Warning: maximum number (" + format(AUTOREFINE_MAX_PARSE_LEVEL) + 
                                     ") of recursive files exceeded, skipping file " + fileinname + "\n")
        return True
        
    # reset group number for current parse level
    m_iGroupNum[m_iParseLevel] = 1;
    
    # init filePosMap
    filePosMap = {}
    
    # check if the conductor file is a sub-file
    if fileinname in parentFilePosMap:
        # if it is a sub-file, copy parent data
        filePosMap = parentFilePosMap
        fid = parentFid
        try:
            # store current file position to restore it at the end
            # Remark: tell() in Python under Windows must be used with files opened as 'rb'
            # as Unix-style endings may cause tell() to return illegal values
            startPos = fid.tell()
            # and get linenum and position
            linenum = parentFilePosMap[fileinname].linenum
            fid.seek(parentFilePosMap[fileinname].filePos)
        except IOError as err:
            FreeCAD.Console.PrintMessage("OS error: " + format(err) + "\n")
            fid.closed
            return False
    else:
        try:
            # open the sub file id
            fid = open(fileinname, 'rb')
            linenum = 1
            fid.closed
        except OSError as err:
            FreeCAD.Console.PrintMessage("OS error: " + format(err) + "\n")
            return False
        
        # build the file map (for single input file)
        ret = create_file_map(fileinname, fid, filePosMap)
        if ret != True:
            return ret
            
    panelVertexes = []
    chargeDensity = []
    panelColors = []
        
    for line in fid:
        # if subfile definitions (starting or ending), stop here
        if line[0] in ('E', 'e', 'F', 'f'):
            break
        # now check for actual statements
        #
        # first split the line into the components
        splitLine = line.split()
        # if the line was actually composed only by separators, continue
        if len(splitLine) == 0:
            continue
        # if conductor file
        if splitLine[0] == 'C':
            try:
                # read file name
                name = splitline[1]
                
                # read outer permittivity
                
                if 'j' in splitline[2]:
                    # as the complex format in FasterCap is 'a-jb' and not 'a-bj' as the Python 'complex' class
                    # would like, this trick modifies the string to be parsable by 'complex'
                    # Remark: we assume that the complex number has no spaces; FasterCap would accept
                    # also syntax like 'a - jb', here it would cause errors
                    localOutPerm = complex(splitline[2].replace('j', '') + 'j')
                else:
                    localOutPerm = complex(splitline[2])
                
                # read offset coordinates
                localOffset = Vector(float(splitLine[3]), float(splitLine[4]), float(splitLine[5]))
                localOffset = localOffset + offset
                
                # compute group name (to distinguish between panels with the same
                # conductor name because in the same file called more than once)
                if m_iParseLevel == 0:
                    localGroupname = "g"
                else:
                    localGroupname = groupname
                localGroupname = localGroupname + str(m_iGroupNum[m_iParseLevel]) + '_'
                
                # read optional values
                if len(splitLine) >= 7:
                    # read optional '+'. If not a '+', increment the group
                    if splitLine[6] != '+':
                        # increase group name
                        m_iGroupNum[m_iParseLevel] = m_iGroupNum[m_iParseLevel] + 1
                    
                # read optional color; if present, it is the last element of the line
                if splitLine[-1][0:2] in ("0x", "0X"):
                    groupcolor = splitLine[5]               
                
                # recurse into new conductor file
                m_iGroupNum[m_iParseLevel+1] = 1
                
            except (IndexError, ValueError):
                FreeCAD.Console.PrintMessage("Error in file " + fileinname + " at line " + format(linenum) + " : " + line + "\n")   
            
            ret = Parse3DInputFile(name, fid, filePosMap, False, localOffset, localOutperm, localGroupname)
            
            if ret == False:
                break

        # if dielectric file
        if splitLine[0] == 'D':
            try:
                # read file name
                name = splitline[1]
                
                # read outer permittivity
                
                if 'j' in splitline[2]:
                    # as the complex format in FasterCap is 'a-jb' and not 'a-bj' as the Python 'complex' class
                    # would like, this trick modifies the string to be parsable by 'complex'
                    # Remark: we assume that the complex number has no spaces; FasterCap would accept
                    # also syntax like 'a - jb', here it would cause errors
                    localOutPerm = complex(splitline[2].replace('j', '') + 'j')
                else:
                    localOutPerm = complex(splitline[2])
                
                # read inner permittivity
                
                if 'j' in splitline[3]:
                    # as the complex format in FasterCap is 'a-jb' and not 'a-bj' as the Python 'complex' class
                    # would like, this trick modifies the string to be parsable by 'complex'
                    # Remark: we assume that the complex number has no spaces; FasterCap would accept
                    # also syntax like 'a - jb', here it would cause errors
                    localOutPerm = complex(splitline[3].replace('j', '') + 'j')
                else:
                    localOutPerm = complex(splitline[3])
 
                 # read offset coordinates
                localOffset = Vector(float(splitLine[4]), float(splitLine[5]), float(splitLine[6]))
                localOffset = localOffset + offset
                
                 # read dielectric reference point coordinates
                localDielrefpoint = Vector(float(splitLine[7]), float(splitLine[8]), float(splitLine[9]))
                localDielrefpoint = localDielrefpoint + offset

                # read optional values
                if len(splitLine) >= 11:
                    # read optional '-'
                    # if '-', reverse outperm and inperm;
                    # in this way, the reference point is always on the outperm side
                    if splitLine[10] == '-':
                        localInperm, localOutperm = localOutperm, localInperm
                    
                # read optional color; if present, it is the last element of the line
                if splitLine[-1][0:2] in ("0x", "0X"):
                    groupcolor = splitLine[5]               
                
                # compute dielectric name (to distinguish between panels
                # in the same file called more than once)
                localGroupname = "diel" + str(m_lGroupDielNum)
                sprintf(localGroupname, "diel%ld", m_lGroupDielNum)
                # increase group name
                m_lGroupDielNum = m_lGroupDielNum + 1

            except (IndexError, ValueError):
                FreeCAD.Console.PrintMessage("Error in file " + fileinname + " at line " + format(linenum) + " : " + line + "\n")   

            # recurse into new dielectric file
            ret = Parse3DInputFile(name, fid, filePosMap, True, localOffset, localOutperm, localGroupname, localInperm, localDielrefpoint)
            
            if ret == False:
                break

        # if triangle
        if splitLine[0] == 'T':
            try:
                # read conductor name to which the patch belongs
                tmpname = splitline[1]
                
                # read panel coordinates
                #
                
                # if using mesh, we need a flat list of vertexes, that will be used in triplets
                # to build the triangular-only mesh faces
                if m_sUsePartType == 'mesh':
                    panelVertexes.extend( [ [float(splitLine[2]), float(splitLine[3]), float(splitLine[4])],
                                            [float(splitLine[5]), float(splitLine[6]), float(splitLine[7])],
                                            [float(splitLine[8]), float(splitLine[9]), float(splitLine[10])] ])
                # if using faces, we need FreeCAD.Vector or tuple of three floats for each vertex, in a vector
                # with as many elements as the vertexes of the polygon supporting the face
                else:
                    panelVertexes.append( [ (float(splitLine[2]), float(splitLine[3]), float(splitLine[4])),
                                            (float(splitLine[5]), float(splitLine[6]), float(splitLine[7])),
                                            (float(splitLine[8]), float(splitLine[9]), float(splitLine[10])) ])
                                            
                # read optional reference point
                if len(splitLine) >= 14:
                    localDielrefpoint = Vector(float(splitLine[11]), float(splitLine[12]), float(splitLine[13]))
                    localDielrefpoint = localDielrefpoint + offset
                    uselocaldiel = True
                else
                    uselocaldiel = False

                # read optional trailing charge density information, or color
                # Note that charge density is alternative to color (cannot have both), but charge density could 
                # be confused with the last coordinate of the optional reference point. So if there are three
                # additional optional float values, this is the reference point, and if there is something else still,
                # this must be charge density or color; if there are not three additional optional float values, 
                # but there is something else, again this must be charge density or color, so look at the last value
                # on the line
                if (uselocaldiel == True and len(splitLine) >= 15) or (uselocaldiel == false and len(splitline) >= 12):
                    # if color, read it
                    if splitLine[-1][0:2] in ("0x", "0X"):
                        panelColors.append(splitLine[-1])
                    else
                        chargeDensity.append(float(splitLine[11]))

            except (IndexError, ValueError):
                FreeCAD.Console.PrintMessage("Error on line " + format(i) + " : " + line + "\n")
                
            name = groupname
            # if this is a conductor panel, compose the actual name; otherwise, for dielectric interfaces,
            # we can ignore specific conductor names
            if isdiel == False:
                # concat name with group name
                name = name + tmpname
            
            ret = GetConductor(&(itc), &dielIndex, name, isdiel, outpermRe, outpermIm, inpermRe, inpermIm, dielrefpoint)
            if(ret == False)
                break
            # ret = (long)CreatePanel(vertex, tmpname, dielIndex, &itc, fileinname, linenum, AUTOREFINE_SIMPLE_CREATE_PANEL, globalVars, uselocaldiel, localDielrefpoint);
           
            

            # counting panels (i.e. the panel # in the input file, no input refinement,
            # e.g. Q panels split in two triangles)
            if isdiel == False:
                m_ulInputPanelNum = m_ulInputPanelNum + 1
            else:
                m_ulInputPanelNum = m_ulInputPanelNum + 1
                                            



                            
    return True
    
def create_file_map(fileinname, fid, filePosMap)
    return False
    
def import_fastercap(filename, folder=DEF_FOLDER, use_mesh=True):
    '''Import file in FasterCap format as Mesh or Part.compound
        
    'filename' is the name of the export file
    'folder' is the folder where the file resides
        
    Example:
    fastercapObj = import_fastercap('cube.txt')
'''
    
    if not os.path.isdir(folder):
        FreeCAD.Console.PrintMessage("Error: '" + folder + "' is not a valid folder\n")
        return
        
    if not os.path.exists(folder + os.sep + filename):
        FreeCAD.Console.PrintMessage("Error: '" + filename + "' is not a valid file in the directory " + folder + "\n")
        return
        
    try:
        with open(folder + os.sep + filename, 'rb') as fid:
            # reset the list of triangle vertexes
            panelVertexes = []
            chargeDensity = []
            # and scan all the file
            for i, line in enumerate(fid):
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
    
    