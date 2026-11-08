# ElectroMagnetic workbench for FreeCAD

## Copyright

### FastHenry support

Copyright (c) 2019
Efficient Power Conversion Corporation, Inc.  http://epc-co.com

Developed by FastFieldSolvers S.R.L.  http://www.fastfieldsolvers.com under contract by EPC


### VoxHenry, FasterCap and FastCap support

Copyright (c) 2026 Enrico Di Lorenzo
FastFieldSolvers http://www.fastfieldsolvers.com

## Description

This project is dedicated to building an ElectroMagnetic workbench for [FreeCAD](https://www.freecad.org). FreeCAD is a free 3D parametric CAD.
FreeCAD is used as pre-/post-processor interfacing to the open source electromagnetic field solvers  [FastHenry](https://www.fastfieldsolvers.com/fasthenry2.htm),  [VoxHenry](https://www.fastfieldsolvers.com/software.htm#voxhenry), [FasterCap](https://www.fastfieldsolvers.com/fastercap.htm), [FastCap](https://www.fastfieldsolvers.com/fastcap2.htm).

At present, the workbench supports:

- [FastHenry](https://www.fastfieldsolvers.com/fasthenry2.htm) inductance solver
- [VoxHenry](https://www.fastfieldsolvers.com/software.htm#voxhenry) inductance solver: beta support
- [FasterCap](https://www.fastfieldsolvers.com/fastercap.htm) and [FastCap](https://www.fastfieldsolvers.com/fastercap.htm) capacitance solvers

## Version

The current version of the ElectroMagnetic workbench can be shown, once installed, from the **E.M.** menu, selecting **About**.

The version number is also reported in the sources, in the global variable **EM_VERSION** in `freecad/EM/EM_Globals.py`.

## Installing

The ElectroMagnetic workbench is managed as a FreeCAD addon. It can be installed from within FreeCAD using the add-ons manager under the <b>Tools</b> menu, see the [FreeCAD add-on documentation](https://www.freecad.org/wiki/Std_AddonMgr) for more specific instructions

### Manual installation

This addon can also be manually installed, but this method is not recommended, as the add-ons manager provides a more user friendly experience.

If you still wish to manually install the workbench, you can download it by clicking the **Download ZIP** button found on top of the page, or using **Git**. The addon must be un-zipped in your user's FreeCAD/Mod folder. 

**Note**: Your user's FreeCAD folder location is obtained by typing in FreeCAD's python console: `FreeCAD.ConfigGet("UserAppData")`.

Place the complete repository in a single folder under `<UserAppData>/Mod/`, retaining `package.xml`, `freecad/EM/`, `Resources/`, and `Documentation/`. The installation folder may have any name. Remove the previous EM installation before installing this version; in particular, starting from E.M. workbench 3.0.0, the structure of the add-on has changed and is NOT compatible with the previous one. Restart FreeCAD to discover the E.M. workbench.

## Additional information

For any additional information please visit [FastFieldSolvers](https://www.fastfieldsolvers.com/), write on the [FastFieldSolvers Forum](https://www.fastfieldsolvers.com/forum) or on the [FreeCAD Forum](https://forum.freecad.org/viewforum.php?f=56) under the "External Workbenches".

See LICENCE.txt for the license conditions.

Access to the binary and source code download pages on [FastFieldSolvers](https://www.fastfieldsolvers.com/) is free, and you may access anonymously if you want.

## Requirements and solver programs

FreeCAD 1.0 or later, with Python 3.10 or later, is required
FreeCAD must have been compiled with Draft, Part, Mesh workbenches support, plus Pivy (as most of the distributions are).
NumPy and SciPy Python dependencies are also required for the E.M. Workbench, as declared in `package.xml` and `pyproject.toml`. Use the Python environment belonging to FreeCAD when installing dependencies, if not already available.
FastHenry, VoxHenry, FasterCap, and FastCap are separate external solver programs; they are not installed by this addon or its Python package. See [FastFieldSolvers](https://www.fastfieldsolvers.com/).

## Modern Python API

Python modules live in the shared `freecad` namespace. For example:

```python
from freecad.EM import EM
node = EM.makeFHNode(X=0, Y=0, Z=0)
```

## Documentation

The [EM Workbench](https://wiki.freecad.org/EM_Workbench) pages describe the EM Workbench and its support for FastHenry.
The [VoxHenry guide](Documentation/VH_guide.htm) and [FasterCap/FastCap guide](Documentation/FC_guide.htm) provisionally describe the solver workflows, waiting to be integrated in the wiki.

## Existing FastHenry and VoxHenry documents

Old FH/VH documents saved with EM Workbench versions previous to 3.0.0 are automatically translated upon opening into the new object structures. Remember to save your project once converted in the new format.

## License

Code is distributed under LGPL-2.1-or-later; see [LICENCE.txt](LICENCE.txt).
Existing asset copyright and license notices are also noted in their source files.
