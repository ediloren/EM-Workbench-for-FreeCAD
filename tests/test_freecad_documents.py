# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual .FCStd persistence checks; run inside FreeCAD's Python environment."""

import importlib
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

try:
    import FreeCAD as App
except ImportError:
    App = None


@unittest.skipIf(App is None, "requires FreeCAD and its NumPy/SciPy dependencies")
class DocumentMigrationTests(unittest.TestCase):
    def test_legacy_fh_vh_document_resaves_with_modern_paths(self):
        import numpy as np
        # Importing the package installs legacy resolution without activating EM.
        from freecad.EM._legacy import LEGACY_MODULES

        document = App.newDocument("EMMigrationTest")
        opened = None
        try:
            proxies = {}
            for module_name in LEGACY_MODULES:
                module = importlib.import_module("freecad.EM." + module_name)
                kind = module_name.removeprefix("EM_")
                obj = document.addObject("Part::FeaturePython", kind)
                getattr(module, "_" + kind)(obj)
                if App.GuiUp:
                    getattr(module, "_ViewProvider" + kind)(obj.ViewObject)
                proxies[kind] = obj
            # Preserve linked objects, conductor identities, and nonempty
            # serialized numeric state independently of geometric voxelization.
            proxies["FHSegment"].NodeStart = proxies["FHNode"]
            proxies["FHSegment"].NodeEnd = proxies["FHNode"]
            plane_base = document.addObject("Part::Box", "PlaneBase")
            proxies["FHPlane"].Base = plane_base
            proxies["FHPlane"].Nodes = [proxies["FHNode"]]
            proxies["FHPlane"].Holes = [proxies["FHPlaneHole"]]
            solver = proxies["VHSolver"]
            solver.VoxelSpaceX = solver.VoxelSpaceY = solver.VoxelSpaceZ = 1
            solver.Proxy.voxelSpace = np.zeros((2, 2, 2), dtype=np.int16)
            solver.Proxy.voxelSpace[1, 0, 1] = 7
            solver.Proxy.bbox = App.BoundBox(0, 0, 0, 2, 2, 2)
            conductor = proxies["VHConductor"]
            conductor.CondIndex = 7
            conductor.Proxy.shapePoints = [(1., 2., 3.)]
            port = proxies["VHPort"]
            port.Proxy.posContactShapePoints = [(4., 5., 6.)]
            port.Proxy.negContactShapePoints = [(7., 8., 9.)]
            # Populate the contact properties before capturing expected state:
            # callbacks may invalidate voxelization data.
            port.PosVoxelContacts = [1, 0, 1, 0]
            port.NegVoxelContacts = [0, 0, 0, 1]
            expected = {kind: obj.Proxy.__getstate__() for kind, obj in proxies.items()}
            with tempfile.TemporaryDirectory() as directory:
                current = Path(directory) / "current.FCStd"
                legacy = Path(directory) / "legacy.FCStd"
                migrated = Path(directory) / "migrated.FCStd"
                document.saveAs(str(current))
                App.closeDocument(document.Name)
                document = None
                # Generate a legacy-identity fixture with the real FreeCAD
                # property/state representation, preserving all ZIP members.
                with zipfile.ZipFile(current) as source, zipfile.ZipFile(legacy, "w") as target:
                    for info in source.infolist():
                        data = source.read(info.filename)
                        if info.filename in ("Document.xml", "GuiDocument.xml"):
                            for name in LEGACY_MODULES:
                                data = data.replace(
                                    ('module="freecad.EM.' + name + '"').encode(),
                                    ('module="' + name + '"').encode())
                        target.writestr(info, data)
                opened = App.openDocument(str(legacy))
                for kind, state in expected.items():
                    obj = opened.getObject(kind)
                    self.assertEqual(type(obj.Proxy).__module__, "freecad.EM.EM_" + kind)
                    self.assertEqual(obj.Proxy.__getstate__(), state)
                self.assertEqual(opened.FHSegment.NodeStart, opened.FHNode)
                self.assertEqual(opened.FHPlane.Nodes, [opened.FHNode])
                self.assertEqual(opened.VHConductor.CondIndex, 7)
                np.testing.assert_array_equal(opened.VHSolver.Proxy.voxelSpace, solver_grid())
                opened.saveAs(str(migrated))
                App.closeDocument(opened.Name)
                opened = None
                modern_modules = set()
                with zipfile.ZipFile(migrated) as archive:
                    for filename in ("Document.xml", "GuiDocument.xml"):
                        if filename not in archive.namelist():
                            continue
                        root = ET.fromstring(archive.read(filename))
                        for element in root.iter("Python"):
                            module = element.get("module", "")
                            self.assertNotIn(module, LEGACY_MODULES)
                            if module.startswith("freecad.EM.EM_"):
                                modern_modules.add(module)
                self.assertEqual(modern_modules, {"freecad.EM." + name for name in LEGACY_MODULES})
                opened = App.openDocument(str(migrated))
                self.assertEqual(opened.FHNode.Proxy.Type, "FHNode")
                np.testing.assert_array_equal(opened.VHSolver.Proxy.voxelSpace, solver_grid())
        finally:
            if document is not None:
                App.closeDocument(document.Name)
            if opened is not None:
                App.closeDocument(opened.Name)


def solver_grid():
    import numpy as np
    grid = np.zeros((2, 2, 2), dtype=np.int16)
    grid[1, 0, 1] = 7
    return grid
