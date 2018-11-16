# ElectroMagnetic workbench for FreeCAD
Copyright (c) 2018
FastFieldSolvers S.R.L. http://www.fastfieldsolvers.com

## Description

This project is dedicated to building an ElectroMagnetic workbench for [FreeCAD](https://www.freecadweb.org). FreeCAD is a free 3D parametric CAD.
FreeCAD is used as pre-processor interfacing to the electromagnetic field solvers.

At present, the workbench supports:

- [FastHenry](https://www.fastfieldsolvers.com/fasthenry2.htm) inductance solver: ongoing development including GUI support
- [FasterCap](https://www.fastfieldsolvers.com/fastercap.htm) capacitance solver: ongoing development, today at the stage of Python macro only, for creating an input file


## Installing

The ElectroMagnetic workbench is managed as a FreeCAD addon. This addon can be downloaded by clicking the **Download ZIP** button found on top of the page, or using **Git**. The addon must be placed in your user's FreeCAD/Mod folder. 

**Note**: Your user's FreeCAD folder location is obtained by typing in FreeCAD's python console: `FreeCAD.ConfigGet("UserAppData")`.

You must then rename the new folder 'EM'. I.e., the new folder structure must be <UserAppData>/Mod/EM. Opening, or closing/reopening FreeCAD then reloads the workbenches, and the E.M. workbench will show up in the pull-down workbenches menu in FreeCAD.

## Additional information

For any additional information please visit [FastFieldSolvers](https://www.fastfieldsolvers.com/), write on the [FastFieldSolvers Forum](https://www.fastfieldsolvers.com/forum) or on the [FreeCAD Forum](https://forum.freecadweb.org/viewforum.php?f=18) under the FEM topic.

See LICENCE.txt for the license conditions.

Access to the binary and source code download pages on [FastFieldSolvers](https://www.fastfieldsolvers.com/) is free, and you may access anonymously if you want.
