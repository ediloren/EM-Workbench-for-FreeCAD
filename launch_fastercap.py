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

import subprocess
from time import sleep
import FreeCAD, FreeCADGui
 
simfile = "C:/Users/Public/Documents/FastFieldSolvers/FasterCap/3D/array_of_5_spheres.lst"
simengine = 'C:/Program Files (x86)/FastFieldSolvers/FasterCap/fastercap.exe'

p=subprocess.Popen([simengine, "-b", "-a0.001", "-ap", simfile],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
 
while True:
  myline = p.stdout.readline()
  if myline:
    App.Console.PrintMessage(myline)
  if not myline:
    break
  
lastout = p.communicate()
App.Console.PrintMessage(lastout)

