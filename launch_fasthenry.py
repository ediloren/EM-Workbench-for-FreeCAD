# SPDX-License-Identifier: LGPL-2.1-or-later

################################################################################
#                                                                              #
#   © 2018 Efficient Power Conversion Corporation, Inc. ( http://epc-co.com )  #
#                                                                              #
#   Developed by FastFieldSolvers S.R.L. ( http://www.fastfieldsolvers.com )   #
#   under contract by Efficient Power Conversion Corporation, Inc.             #
#                                                                              #
#   This addon is free software: you can redistribute it and/or modify it      #
#   under the terms of the GNU Lesser General Public License as published      #
#   by the Free Software Foundation, either version 2.1 of the License,        #
#   or (at your option) any later version.                                     #
#                                                                              #
#   This addon is distributed in the hope that it will be useful,              #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser                          #
#   General Public License along with this addon.                              #
#   If not, see https://www.gnu.org/licenses                                   #
#                                                                              #
################################################################################


import subprocess
from time import sleep
import FreeCAD, FreeCADGui

simfile = "C:/Users/Public/Documents/FastFieldSolvers/FastHenry2/pin-con7.inp"
simengine = 'C:/Program Files (x86)/FastFieldSolvers/FastHenry2/FastHenry2.exe'

p=subprocess.Popen([simengine, "-b", "-a0.001", "-ap", simfile],stdin=subprocess.PIPE,stdout=subprocess.PIPE)

while True:
  myline = p.stdout.readline()
  if myline:
    App.Console.PrintMessage(myline)
  if not myline:
    break

# get what is left in the buffer
lastout = p.communicate()
App.Console.PrintMessage(lastout)

