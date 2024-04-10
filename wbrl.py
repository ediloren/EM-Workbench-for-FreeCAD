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

from importlib import reload

import EM
import EM_FHNode
import EM_FHSegment
import EM_FHPath
import EM_FHPlane
import EM_FHPlaneHole
import EM_FHEquiv
import EM_FHPort
import EM_FHSolver
import EM_FHInputFile
reload(EM)
reload(EM_FHNode)
reload(EM_FHSegment)
reload(EM_FHPath)
reload(EM_FHPlane)
reload(EM_FHPlaneHole)
reload(EM_FHEquiv)
reload(EM_FHPort)
reload(EM_FHSolver)
reload(EM_FHInputFile)

def go(c='s'):
    ''' Function to reload the workbench objects and commands
'''
    import EM
    import EM_Globals
    import EM_FHNode
    import EM_FHSegment
    import EM_FHPath
    import EM_FHPlane
    import EM_FHPlaneHole
    import EM_FHEquiv
    import EM_FHPort
    import EM_FHSolver
    import EM_FHInputFile
    reload(EM)
    reload(EM_Globals)
    reload(EM_FHNode)
    reload(EM_FHSegment)
    reload(EM_FHPath)
    reload(EM_FHPlane)
    reload(EM_FHPlaneHole)
    reload(EM_FHEquiv)
    reload(EM_FHPort)
    reload(EM_FHSolver)
    reload(EM_FHInputFile)
    if c=='n' or c==1:
        EM_FHNode._CommandFHNode().Activated()
    elif c=='s' or c==2:
        EM_FHSegment._CommandFHSegment().Activated()
    elif c=='p' or c==3:
        EM_FHPlane._CommandFHPlane().Activated()
    elif c=='h' or c==4:
        EM_FHPlaneHole._CommandFHPlaneHole().Activated()
    elif c=='t' or c==5:
        EM_FHPath._CommandFHPath().Activated()
    elif c=='a' or c==6:
        EM_FHPlane._CommandFHPlaneAddRemoveNodeHole().Activated()

#import EM
#import EM_FHNode
#EM_FHNode._CommandFHNode().Activated()

#import EM_FHPlaneHole
#EM_FHPlaneHole._CommandFHPlaneHole().Activated()
