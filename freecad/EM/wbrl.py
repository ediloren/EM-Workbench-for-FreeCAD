#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2026 FastFieldSolvers                                   *
#*   Enrico Di Lorenzo                                                     *
#*   https://www.fastfieldsolvers.com                                      *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2.1 of   *
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

from . import EM
from . import EM_FHNode
from . import EM_FHSegment
from . import EM_FHPath
from . import EM_FHPlane
from . import EM_FHPlaneHole
from . import EM_FHEquiv
from . import EM_FHPort
from . import EM_FHSolver
from . import EM_FHInputFile
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
    from . import EM
    from . import EM_Globals
    from . import EM_FHNode
    from . import EM_FHSegment
    from . import EM_FHPath
    from . import EM_FHPlane
    from . import EM_FHPlaneHole
    from . import EM_FHEquiv
    from . import EM_FHPort
    from . import EM_FHSolver
    from . import EM_FHInputFile
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
