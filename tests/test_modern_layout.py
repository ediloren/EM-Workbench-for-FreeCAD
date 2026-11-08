# SPDX-License-Identifier: LGPL-2.1-or-later
"""Namespace and legacy document identity checks, without a FreeCAD install.

FreeCAD geometry and GUI operations still require application-level smoke tests.
"""

import ast
from pathlib import Path
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

# These stand-ins let Python load actual proxy classes without running geometry
# or GUI operations. They do not emulate FreeCAD document restoration itself.
HOST_STUBS = '''
import sys
from types import ModuleType, SimpleNamespace
for name in ("FreeCAD", "Part", "Mesh", "MeshPart", "Draft", "DraftGeomUtils",
             "DraftVecUtils", "numpy", "scipy"):
    sys.modules[name] = ModuleType(name)
sys.modules["FreeCAD"].GuiUp = False
sys.modules["FreeCAD"].Vector = lambda *args: args
sys.modules["scipy"].ndimage = SimpleNamespace()
'''


class ModernLayoutTests(unittest.TestCase):
    def run_python(self, source):
        result = subprocess.run(
            [sys.executable, "-B", "-c", source], cwd=ROOT,
            text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_startup_and_api_import_are_lightweight(self):
        self.run_python('''
import sys
import freecad.EM
from freecad.EM import EM
from freecad.EM._legacy import LEGACY_MODULES, install
assert all(name in sys.modules for name in LEGACY_MODULES)
assert all(sys.modules[name].__spec__.origin.endswith("_legacy.py") for name in LEGACY_MODULES)
assert not any(name in sys.modules for name in ("FreeCAD", "FreeCADGui", "numpy", "scipy", "PySide"))
assert not any(name.startswith(("freecad.EM.EM_FH", "freecad.EM.EM_VH", "freecad.EM.EM_FC")) for name in sys.modules)
assert "EM" not in sys.modules and "EM_FCSolver" not in sys.modules
before = {name: sys.modules[name] for name in LEGACY_MODULES}
install()
assert all(sys.modules[name] is module for name, module in before.items())
''')

    def test_legacy_fh_and_vh_proxy_identity_and_resave(self):
        self.run_python(HOST_STUBS + '''
import importlib
import pickle
import types
import freecad.EM
from freecad.EM._legacy import LEGACY_MODULES
for module_name in LEGACY_MODULES:
    legacy = importlib.import_module(module_name)
    modern = importlib.import_module("freecad.EM." + module_name)
    kind = module_name.removeprefix("EM_")
    for name in ("_" + kind, "_ViewProvider" + kind):
        actual_class = getattr(legacy, name)
        assert actual_class is getattr(modern, name)
        assert actual_class.__module__ == "freecad.EM." + module_name
        if kind == "VHSolver" and name == "_VHSolver":
            # The real numeric grid is tested in FreeCAD (requires NumPy).
            continue
        state = None if name.startswith("_ViewProvider") else kind
        if name == "_VHConductor":
            state = {"sp": [(1., 2., 3.)], "type": kind}
        elif name == "_VHPort":
            state = {"nsp": [(1., 2., 3.)], "psp": [], "type": kind}
        # Produce a pickle with the historical module path, then restore it
        # through the bridge to the actual relocated proxy class.
        old_class = type(name, (), {"__module__": module_name,
                                   "__getstate__": lambda self: state})
        setattr(legacy, name, old_class)
        payload = pickle.dumps(old_class(), protocol=4)
        delattr(legacy, name)
        restored = pickle.loads(payload)
        assert type(restored) is actual_class
        assert restored.__getstate__() == state
        new_payload = pickle.dumps(restored, protocol=4)
        assert ("freecad.EM." + module_name).encode() in new_payload
        assert type(pickle.loads(new_payload)) is actual_class
assert "freecad.EM.EM_FCSolver" not in sys.modules
assert "FreeCADGui" not in sys.modules and "PySide" not in sys.modules
''')

    def test_api_resolves_only_requested_family(self):
        self.run_python(HOST_STUBS + '''
from freecad.EM import EM
from freecad.EM.EM_FHNode import makeFHNode
assert EM.makeFHNode is makeFHNode
assert EM.EM_VERSION == "3.0.0"
assert "freecad.EM.EM_VHConductor" not in sys.modules
assert "freecad.EM.EM_FCGeometry" not in sys.modules
''')

    def test_workbench_registration_before_activation_is_lightweight(self):
        self.run_python('''
import sys
from types import ModuleType, SimpleNamespace
from pathlib import Path
app = ModuleType("FreeCAD")
app.Console = SimpleNamespace(PrintLog=lambda text: None)
sys.modules["FreeCAD"] = app
gui = ModuleType("FreeCADGui")
gui.Workbench = type("Workbench", (), {})
registered = []
gui.addWorkbench = registered.append
sys.modules["FreeCADGui"] = gui
from freecad.EM import init_gui
assert len(registered) == 1
assert isinstance(registered[0], init_gui.EMWorkbench)
assert Path(registered[0].Icon).is_file()
assert registered[0].GetClassName() == "Gui::PythonWorkbench"
assert not any(name.startswith(("freecad.EM.EM_FH", "freecad.EM.EM_VH", "freecad.EM.EM_FC")) for name in sys.modules)
''')

    def test_manifest_resources_and_namespace_imports(self):
        ns = {"p": "https://wiki.freecad.org/Package_Metadata"}
        manifest = ET.parse(ROOT / "package.xml").getroot()
        self.assertTrue((ROOT / manifest.find("p:icon", ns).text).is_file())
        self.assertEqual(manifest.find("p:content/p:workbench/p:classname", ns).text, "EMWorkbench")
        self.assertTrue((ROOT / "Documentation/VH_guide.htm").is_file())
        self.assertTrue((ROOT / "Documentation/FC_guide.htm").is_file())
        package = ROOT / "freecad/EM"
        modules = {p.stem for p in package.glob("*.py")}
        for path in package.glob("*.py"):
            tree = ast.parse(path.read_bytes(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name in modules for alias in node.names), str(path))
                elif isinstance(node, ast.ImportFrom):
                    self.assertFalse(node.level == 0 and node.module in modules, str(path))
            self.assertNotIn('addModule("EM")', path.read_text())
        self.assertFalse((ROOT / "freecad/__init__.py").exists())


if __name__ == "__main__":
    unittest.main()
