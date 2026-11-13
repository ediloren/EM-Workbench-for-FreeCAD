# ElectroMagnetic workbench for FreeCAD

## Copyright

Copyright (c) 2026 Enrico Di Lorenzo
FastFieldSolvers https://www.fastfieldsolvers.com

### FastHenry support

Copyright (c) 2019
Efficient Power Conversion Corporation, Inc.  https://epc-co.com

Developed by FastFieldSolvers https://www.fastfieldsolvers.com under contract by EPC

## Description

This project is dedicated to building an ElectroMagnetic workbench for [FreeCAD](https://www.freecad.org) running open source and free solvers. FreeCAD is a free 3D parametric CAD.

The E.M. Workbench in FreeCAD is used as a pre-/post-processor interfacing to the following electromagnetic field solvers:

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

Place the complete repository in a single folder under `<UserAppData>/Mod/`, e.g. `<UserAppData>/Mod/EM/` (the 'EM' name is not mandatory, albeit recommended. In fact, the installation folder may have any name).
Remove a previous EM installation, if any, before installing this version as starting from E.M. workbench 3.0.0, the structure of the add-on has changed and is NOT compatible with the previous one.
Restart then FreeCAD to discover the E.M. workbench; it will appear as one of the workbenches in the list.

## Additional information

For any additional information please visit [FastFieldSolvers](https://www.fastfieldsolvers.com/), write on the [FastFieldSolvers Forum](https://www.fastfieldsolvers.com/forum) or on the [FreeCAD Forum](https://forum.freecad.org/viewforum.php?f=56) under the "External Workbenches".

Access to the binary and source code download pages on [FastFieldSolvers](https://www.fastfieldsolvers.com/) is free, and you may access anonymously if you want.

## Requirements and solver programs

- Core workbench:
  - FreeCAD 1.0 or later, with Python 3.10 or later
  - FreeCAD must have been compiled with Draft, Part, Mesh workbenches support, plus Pivy (as most of the distributions are).
  - NumPy and SciPy Python dependencies, as declared in `package.xml` and `pyproject.toml`. Use the Python environment belonging to FreeCAD when installing dependencies, if not already available.

- Solvers:

  - FastHenry, VoxHenry, FasterCap, and FastCap are separate external solver programs; they are not installed by this addon or its Python package. See [FastFieldSolvers](https://www.fastfieldsolvers.com/).

## Documentation

The [EM Workbench](https://wiki.freecad.org/EM_Workbench) pages describe the EM Workbench and its support for FastHenry.
The [FastHenry guide](Documentation/FH_guide.htm), [VoxHenry guide](Documentation/VH_guide.htm), and [FasterCap/FastCap guide](Documentation/FC_guide.htm) are supplemental documents, describing the solver workflows.

## Existing FastHenry and VoxHenry saved files

Old FH/VH documents saved with EM Workbench versions previous to 3.0.0 are automatically translated, upon opening, into the new object structures. Remember to save your project once converted in the new format.

## License

Code is distributed under LGPL-2.1-or-later; see [LICENCE.txt](LICENCE.txt).
Existing asset copyright and license notices are also noted in their source files.

