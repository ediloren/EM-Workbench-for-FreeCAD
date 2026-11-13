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


__title__="FreeCAD E.M. Workbench FastHenry import command"
__author__ = "FastFieldSolvers - Enrico Di Lorenzo"
__url__ = "http://www.fastfieldsolvers.com"

import os
import re

import FreeCAD

# The geometry reader is GUI independent; this module owns the FC-style MDI
# editors, file discovery, progress dialog, reload transactions and command.
from .import_fasthenry import (read_fasthenry_file,
                               get_fasthenry_input_files, FHImportError)

if FreeCAD.GuiUp:
    import FreeCADGui
    from FreeCAD import Qt
    translate = Qt.translate
    from PySide import QtCore, QtGui
    try:
        from PySide import QtWidgets
    except ImportError:
        # PySide 1 keeps widget classes in QtGui.
        QtWidgets = QtGui
    # QShortcut moved from QtWidgets to QtGui in Qt 6. FreeCAD's ``PySide``
    # compatibility namespace follows the location used by its Qt version.
    if hasattr(QtWidgets, "QShortcut"):
        _FHQShortcut = QtWidgets.QShortcut
    else:
        _FHQShortcut = QtGui.QShortcut
    if hasattr(QtWidgets, "QAction"):
        _FHQAction = QtWidgets.QAction
    else:
        _FHQAction = QtGui.QAction
    from PySide.QtCore import QT_TRANSLATE_NOOP
else:
    # \cond
    def translate(ctxt, txt):
        return txt
    def QT_TRANSLATE_NOOP(ctxt, txt):
        return txt
    # \endcond

from ._paths import ICONS_DIR as iconPath

# FastHenry-specific colors; values intentionally follow FCImport's palette.
FHIMPORT_FILTER = QT_TRANSLATE_NOOP(
    "EM_FHImport", "FastHenry input files (*.inp *.INP);;All files (*)")
EM_FHIMPORT_COMMENT_COLOR = "#777777"
EM_FHIMPORT_REFERENCE_COLOR = "#cc6600"
EM_FHIMPORT_SEGMENT_COLOR = "#0066cc"
EM_FHIMPORT_PLANE_COLOR = "#cc3399"
EM_FHIMPORT_GEOMETRY_COLOR = "#336600"
EM_FHIMPORT_DIRECTIVE_COLOR = "#9933ff"
EM_FHIMPORT_NUMBER_COLOR = "#202020"


def getFHInputFiles(filename):
    """Return the input and distinct plane-discretization files in first-use order."""
    try:
        return get_fasthenry_input_files(filename)
    except (OSError, FHImportError) as error:
        FreeCAD.Console.PrintWarning("Cannot discover FastHenry input files: %s\n" % error)
        return [os.path.abspath(os.path.expanduser(filename))]


def openFHTextFiles(filename, model=None, model_window=None):
    """Open the input and every file= dependency in separate highlighted MDI tabs."""
    if not FreeCAD.GuiUp:
        FreeCAD.Console.PrintWarning("FastHenry text files require the FreeCAD GUI.\n")
        return []
    root = os.path.abspath(os.path.expanduser(filename))
    editors = []
    for path in getFHInputFiles(root):
        editor = _open_fh_text_file(path, root, model, model_window)
        if editor is not None:
            editors.append(editor)
    return editors


def importFHInputFile(filename, viewText=False, model_window=None):
    """Import grouped FastHenry surfaces and optionally open all source editors.

    Native input and text files remain authoritative. No FH solver primitives
    are created. The returned Part::Compound can be replaced by Save & Reload.
    """
    path = os.path.abspath(os.path.expanduser(filename))
    if not os.path.isfile(path):
        FreeCAD.Console.PrintError("FastHenry input file does not exist: %s\n" % path)
        return False
    if FreeCAD.ActiveDocument is None:
        FreeCAD.newDocument(_fh_document_name(path))
    progress = _FHImportProgress() if FreeCAD.GuiUp else None
    try:
        result = read_fasthenry_file(path, progress=progress)
        cancelled = progress.cancelled if progress is not None else False
    finally:
        if progress is not None:
            progress.close()
    if FreeCAD.GuiUp:
        if model_window is None:
            try:
                FreeCADGui.activateView("Gui::View3DInventor", False)
            except (AttributeError, RuntimeError, TypeError):
                pass
            area = _fh_mdi_area()
            active = area.activeSubWindow() if area is not None else None
            if isinstance(active, _FHTextWindow):
                model_window = active.modelWindow
            else:
                model_window = active
        if viewText and not cancelled:
            # Keep source editing available even after a parse failure.
            openFHTextFiles(path, result, model_window)
        if result:
            _fh_activate_model_view(result, model_window)
    return result


def _fh_document_name(path):
    """Build a valid, unused FreeCAD document name from an input filename."""
    base = os.path.splitext(os.path.basename(path))[0]
    base = re.sub(r"[^A-Za-z0-9_]", "_", base)
    if not base or base[0].isdigit():
        base = "FastHenry_" + base
    documents = FreeCAD.listDocuments() if hasattr(FreeCAD, "listDocuments") else {}
    name = base
    suffix = 1
    while name in documents:
        suffix += 1
        name = "%s_%d" % (base, suffix)
    return name


# Return focus to the concrete 3D MDI subwindow captured before text editors
# were opened. FreeCADGui.activateView() alone does not raise that Qt window
# when a custom editor subwindow currently owns the MDI focus.
def _fh_activate_model_view(model, model_window=None):
    if not FreeCAD.GuiUp or not model:
        return
    FreeCAD.setActiveDocument(model.Document.Name)
    FreeCADGui.Selection.clearSelection()
    try:
        if model_window is not None:
            mdi_area = model_window.mdiArea()
            if mdi_area is not None:
                model_window.show()
                mdi_area.setActiveSubWindow(model_window)
                model_window.raise_()
                model_window.setFocus()
            else:
                model_window = None
        if model_window is None:
            FreeCADGui.activateView("Gui::View3DInventor", False)
        FreeCADGui.activeDocument().activeView().fitAll()
    except (AttributeError, RuntimeError, TypeError):
        pass


if FreeCAD.GuiUp:
    class _FHImportProgress:
        """Modal, coarse-grained progress reporter used by the parser."""
        def __init__(self):
            self.cancelled = False
            self.stage = None
            self.dialog = QtWidgets.QProgressDialog(
                translate("EM", "Reading FastHenry input..."),
                translate("EM", "Cancel"), 0, 0, FreeCADGui.getMainWindow())
            self.dialog.setWindowTitle(
                translate("EM", "Import FastHenry model"))
            self.dialog.setWindowModality(QtCore.Qt.WindowModal)
            self.dialog.setMinimumDuration(0)
            self.dialog.setAutoClose(False)
            self.dialog.setAutoReset(False)
            self.dialog.show()

        def __call__(self, stage, current, total):
            if self.dialog is None:
                return False
            if stage != self.stage:
                self.stage = stage
                self.dialog.setLabelText(translate("EM", stage + "..."))
            # Parsing may not yet know the total work. Keep an indeterminate
            # bar until a construction stage can supply a meaningful count.
            if total > 0:
                if (self.dialog.minimum() != 0 or
                        self.dialog.maximum() != total):
                    self.dialog.setRange(0, total)
                self.dialog.setValue(current)
            elif self.dialog.minimum() != 0 or self.dialog.maximum() != 0:
                self.dialog.setRange(0, 0)
            QtWidgets.QApplication.processEvents()
            # Return cancellation to the reader at its next coarse checkpoint;
            # do not interrupt a native shape construction halfway through.
            self.cancelled = self.dialog.wasCanceled()
            return not self.cancelled

        def close(self):
            if self.dialog is not None:
                self.dialog.close()
                self.dialog.deleteLater()
                self.dialog = None



if FreeCAD.GuiUp:
    class _FHSyntaxHighlighter(QtGui.QSyntaxHighlighter):
        """Native input and binary plane-discretization syntax highlighting."""
        def __init__(self, document, hierarchy=False):
            super(_FHSyntaxHighlighter, self).__init__(document)
            self.hierarchy = hierarchy
            self.formats = {}
            for kind, color in (("comment", EM_FHIMPORT_COMMENT_COLOR),
                                ("reference", EM_FHIMPORT_REFERENCE_COLOR),
                                ("segment", EM_FHIMPORT_SEGMENT_COLOR),
                                ("plane", EM_FHIMPORT_PLANE_COLOR),
                                ("geometry", EM_FHIMPORT_GEOMETRY_COLOR),
                                ("directive", EM_FHIMPORT_DIRECTIVE_COLOR),
                                ("number", EM_FHIMPORT_NUMBER_COLOR)):
                value = QtGui.QTextCharFormat()
                value.setForeground(QtGui.QColor(color))
                if kind not in ("comment", "number"):
                    value.setFontWeight(QtGui.QFont.Bold)
                self.formats[kind] = value
            self.numberExpression = re.compile(
                r"(?<![\w.])[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
            # Require an identifier after a directive dot and a token boundary
            # before words, so decimals and exponent suffixes remain numeric.
            self.wordExpression = re.compile(
                r"(?<![\w.])(?:\.[A-Za-z_]|[A-Za-z_])[\w.]*")
            self.fileExpression = re.compile(
                r'\bfile\s*=\s*("[^"\n]*"|\'[^\'\n]*\'|[^\s]+)', re.I)

        def highlightBlock(self, text):
            text = str(text)
            if (text.lstrip().startswith("*") or
                    not self.hierarchy and self.currentBlock().blockNumber() == 0):
                self.setFormat(0, len(text), self.formats["comment"])
                return
            for match in self.numberExpression.finditer(text):
                self.setFormat(match.start(), len(match.group()), self.formats["number"])
            first = True
            for match in self.wordExpression.finditer(text):
                word = match.group().lower()
                kind = None
                if self.hierarchy:
                    if word in ("b", "none", "ew", "ns"):
                        kind = "geometry" if word in ("ew", "ns") else "directive"
                elif (not text[:match.start()].strip() and word.startswith(".") and
                      word[1:4] in ("uni", "def", "ext", "equ", "fre", "end")):
                    # dodot() in readGeom.c accepts these three-letter prefixes.
                    kind = "directive"
                elif word in ("hole", "contact", "rect", "point", "circle", "line",
                              "decay_rect", "equiv_rect", "connection", "initial_grid",
                              "initial_mesh_grid", "trace"):
                    kind = "geometry"
                elif word.startswith("n") and word not in ("nhinc", "nwinc", "ndec", "none"):
                    kind = "reference"
                elif first and word.startswith("e"):
                    kind = "segment"
                elif first and word.startswith("g"):
                    kind = "plane"
                if kind:
                    self.setFormat(match.start(), len(match.group()), self.formats[kind])
                first = False
            if not self.hierarchy:
                for match in self.fileExpression.finditer(text):
                    self.setFormat(match.start(1), len(match[1]), self.formats["reference"])


    class _FHTextWindow(QtWidgets.QMdiSubWindow):
        """Editable view of one physical FastHenry input file."""
        def __init__(self, path, parent=None):
            super(_FHTextWindow, self).__init__(parent)
            self.path = os.path.abspath(path)
            self.rootPath = None
            self.documentName = ""
            self.modelObjectNames = []
            self.modelWindow = None
            self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
            self.setWindowTitle(os.path.basename(self.path) + "[*] - FastHenry")

            container = QtWidgets.QWidget(self)
            layout = QtWidgets.QVBoxLayout(container)
            layout.setContentsMargins(4, 4, 4, 4)

            # expose editor display options without adding them to FreeCAD's
            # global menus
            menu_bar = QtWidgets.QMenuBar(container)
            view_menu = menu_bar.addMenu(translate("EM", "View"))
            self.wrapAction = view_menu.addAction(
                translate("EM", "Wrap lines"))
            self.wrapAction.setCheckable(True)
            layout.setMenuBar(menu_bar)

            path_label = QtWidgets.QLabel(self.path, container)
            path_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            layout.addWidget(path_label)

            self.editor = QtWidgets.QPlainTextEdit(container)
            # restore the last line-wrap choice for every new editor window
            preferences = FreeCAD.ParamGet(
                "User parameter:BaseApp/Preferences/Mod/EM")
            wrap_lines = preferences.GetBool("FHImportWrapText", False)
            wrap_mode = (QtWidgets.QPlainTextEdit.WidgetWidth if wrap_lines
                         else QtWidgets.QPlainTextEdit.NoWrap)
            self.editor.setLineWrapMode(wrap_mode)
            self.wrapAction.setChecked(wrap_lines)
            self.wrapAction.toggled.connect(self.setLineWrap)
            self.editor.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self.editor.customContextMenuRequested.connect(
                self.showEditorContextMenu)
            # use the platform fixed-width font for aligned panel coordinates
            if hasattr(QtGui.QFontDatabase, "systemFont"):
                fixed_font = QtGui.QFontDatabase.systemFont(
                    QtGui.QFontDatabase.FixedFont)
            else:
                # Qt 4 / PySide 1 has no systemFont() convenience function.
                fixed_font = QtGui.QFont("Monospace")
                fixed_font.setStyleHint(QtGui.QFont.TypeWriter)
            self.editor.setFont(fixed_font)
            layout.addWidget(self.editor)

            # provide file controls without replacing the standard shortcut
            button_layout = QtWidgets.QHBoxLayout()
            button_layout.addStretch()
            save_button = QtWidgets.QPushButton(
                translate("EM", "Save"), container)
            save_button.clicked.connect(self.saveFile)
            button_layout.addWidget(save_button)
            save_all_button = QtWidgets.QPushButton(
                translate("EM", "Save All"), container)
            save_all_button.clicked.connect(self.saveAllFiles)
            button_layout.addWidget(save_all_button)
            # Qt interprets '&' as a mnemonic; double it for a literal label.
            reload_button = QtWidgets.QPushButton(
                translate("EM", "Save && Reload"), container)
            reload_button.clicked.connect(self.reloadModel)
            button_layout.addWidget(reload_button)
            close_all_button = QtWidgets.QPushButton(
                translate("EM", "Close All"), container)
            close_all_button.clicked.connect(self.closeAllEditors)
            button_layout.addWidget(close_all_button)
            layout.addLayout(button_layout)

            self.setWidget(container)
            # attach syntax coloring and propagate document changes to the MDI tab
            self.highlighter = _FHSyntaxHighlighter(
                self.editor.document(), hierarchy=False)
            self.editor.document().modificationChanged.connect(
                self.setWindowModified)

            # keep Ctrl+S local to the active input-file editor
            shortcut = _FHQShortcut(QtGui.QKeySequence.Save, self)
            shortcut.activated.connect(self.saveFile)
            self.saveShortcut = shortcut
            self.loadFile()
            self.resize(820, 560)

        def setImportContext(self, root_path, model=None, model_window=None):
            """Associate this editor with its root file and imported geometry."""
            self.rootPath = os.path.abspath(os.path.expanduser(root_path))
            self.highlighter.hierarchy = (
                os.path.realpath(self.path) != os.path.realpath(self.rootPath))
            self.highlighter.rehighlight()
            if model_window is not None:
                self.modelWindow = model_window
            document = getattr(model, "Document", None)
            if document is None:
                document = FreeCAD.ActiveDocument
            self.documentName = document.Name if document is not None else ""
            self.modelObjectNames = []
            if model:
                self.modelObjectNames.append(model.Name)
                self.modelObjectNames.extend(
                    child.Name for child in getattr(model, "Links", [])
                    if getattr(child, "Name", None))

        def reloadModel(self):
            """Save this input and plane discretizations and replace its imported geometry."""
            if not self.rootPath:
                FreeCAD.Console.PrintWarning(
                    translate("EM", "This editor is not associated with an imported model.\n"))
                return False

            # save every physical file belonging to the same root input
            related_editors = [
                editor for editor in list(_fh_text_windows.values())
                if getattr(editor, "rootPath", None) and
                os.path.normcase(os.path.realpath(editor.rootPath)) ==
                os.path.normcase(os.path.realpath(self.rootPath))]
            for editor in related_editors:
                try:
                    if not editor.saveFile():
                        return False
                except RuntimeError:
                    continue

            documents = FreeCAD.listDocuments()
            document = documents.get(self.documentName)
            if document is None:
                FreeCAD.Console.PrintError(
                    translate("EM", "Cannot reload FastHenry model: its document is closed.\n"))
                return False

            # delete and rebuild the complete model as one undoable operation
            FreeCAD.setActiveDocument(document.Name)
            document.openTransaction(translate(
                "EM", "Reload FastHenry model"))
            try:
                for name in self.modelObjectNames:
                    if document.getObject(name) is not None:
                        document.removeObject(name)
                result = importFHInputFile(self.rootPath, False, self.modelWindow)
                if not result:
                    # Restore the old imported objects on parser failure or
                    # cancellation. Their editors must keep the old association.
                    document.abortTransaction()
                    document.recompute()
                    return False
                document.commitTransaction()
            except Exception as error:
                document.abortTransaction()
                document.recompute()
                FreeCAD.Console.PrintError(
                    translate("EM", "FastHenry model reload failed: ") +
                    str(error) + "\n")
                return False

            # update every related editor to point at the replacement objects
            for editor in related_editors:
                try:
                    editor.setImportContext(self.rootPath, result, self.modelWindow)
                except RuntimeError:
                    continue
            openFHTextFiles(self.rootPath, result, self.modelWindow)
            # Only a committed reload may redirect focus.
            _fh_activate_model_view(result, self.modelWindow)
            FreeCAD.Console.PrintMessage(
                translate("EM", "Reloaded FastHenry model from ") +
                self.rootPath + "\n")
            return True

        def setLineWrap(self, enabled):
            mode = (QtWidgets.QPlainTextEdit.WidgetWidth if enabled
                    else QtWidgets.QPlainTextEdit.NoWrap)
            self.editor.setLineWrapMode(mode)
            # share the display preference between all subsequently opened files
            FreeCAD.ParamGet(
                "User parameter:BaseApp/Preferences/Mod/EM").SetBool(
                    "FHImportWrapText", enabled)

        def showEditorContextMenu(self, position):
            # extend Qt's normal editing menu with the shared View action
            menu = self.editor.createStandardContextMenu()
            menu.addSeparator()
            menu.addAction(self.wrapAction)
            menu.addSeparator()
            reload_action = menu.addAction(
                translate("EM", "Save files and reload model"))
            reload_action.triggered.connect(self.reloadModel)
            menu.exec_(self.editor.mapToGlobal(position))
            menu.deleteLater()

        def loadFile(self):
            with open(self.path, "r", encoding="utf-8-sig",
                      errors="replace") as stream:
                self.editor.setPlainText(stream.read())
            self.editor.document().setModified(False)

        def saveFile(self):
            try:
                with open(self.path, "w", encoding="utf-8", newline="") as stream:
                    stream.write(self.editor.toPlainText())
            except OSError as error:
                QtWidgets.QMessageBox.critical(
                    self, translate("EM", "Cannot save FastHenry file"),
                    str(error))
                return False
            self.editor.document().setModified(False)
            FreeCAD.Console.PrintMessage(
                translate("EM", "Saved FastHenry file ") +
                "'" + self.path + "'\n")
            return True

        def saveAllFiles(self):
            """Save every open FastHenry text editor."""
            # Snapshot the registry: Qt callbacks may close windows while these
            # operations run. A deleted C++ widget raises RuntimeError in Python.
            for editor in list(_fh_text_windows.values()):
                try:
                    if not editor.saveFile():
                        return False
                except RuntimeError:
                    continue
            return True

        def closeAllEditors(self):
            """Close every input editor, stopping if a close is cancelled."""
            for editor in list(_fh_text_windows.values()):
                try:
                    # closeEvent asks how to handle each modified document
                    if not editor.close():
                        return False
                except RuntimeError:
                    continue
            return True

        def closeEvent(self, event):
            if not self.editor.document().isModified():
                event.accept()
                return
            answer = QtWidgets.QMessageBox.warning(
                self, translate("EM", "Unsaved FastHenry file"),
                translate("EM", "Save changes to ") +
                "'" + os.path.basename(self.path) + "'?",
                QtWidgets.QMessageBox.Save |
                QtWidgets.QMessageBox.Discard |
                QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Save)
            if answer == QtWidgets.QMessageBox.Save:
                if self.saveFile():
                    event.accept()
                else:
                    event.ignore()
            elif answer == QtWidgets.QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()


    # map canonical file paths to their currently open MDI editor windows
    _fh_text_windows = {}


    def _fh_mdi_area():
        main_window = FreeCADGui.getMainWindow()
        central_widget = main_window.centralWidget()
        if isinstance(central_widget, QtWidgets.QMdiArea):
            return central_widget
        mdi_areas = main_window.findChildren(QtWidgets.QMdiArea)
        return mdi_areas[0] if mdi_areas else None


    # Reuse an existing window by canonical source identity so repeated plane references
    # cannot open duplicate editors for the same physical file.
    def _open_fh_text_file(path, root_path=None, model=None, model_window=None):
        path = os.path.abspath(path)
        identity = os.path.normcase(os.path.realpath(path))
        existing = _fh_text_windows.get(identity)
        # activate an existing editor instead of opening duplicate views
        if existing is not None:
            try:
                if root_path is not None:
                    existing.setImportContext(root_path, model, model_window)
                existing.show()
                existing.raise_()
                mdi_area = existing.mdiArea()
                if mdi_area is not None:
                    mdi_area.setActiveSubWindow(existing)
                return existing
            except RuntimeError:
                _fh_text_windows.pop(identity, None)

        mdi_area = _fh_mdi_area()
        if mdi_area is None:
            FreeCAD.Console.PrintError(
                translate("EM", "Cannot find the FreeCAD MDI area for ") +
                "'" + path + "'\n")
            return None
        try:
            window = _FHTextWindow(path)
            if root_path is not None:
                window.setImportContext(root_path, model, model_window)
        except OSError as error:
            FreeCAD.Console.PrintError(
                translate("EM", "Cannot open FastHenry text file ") +
                "'" + path + "': " + str(error) + "\n")
            return None

        # register the editor with both FreeCAD's MDI area and the local cache
        mdi_area.addSubWindow(window)
        _fh_text_windows[identity] = window

        def forget_window(*_args):
            if _fh_text_windows.get(identity) is window:
                _fh_text_windows.pop(identity, None)

        window.destroyed.connect(forget_window)
        window.show()
        mdi_area.setActiveSubWindow(window)
        return window


    # The dialog gathers only path and view preference; actual parsing stays in the
    # command helper where console and scripted callers share behavior.
    class _FHImportDialog(QtWidgets.QDialog):
        """File selector with the optional text-view flag."""
        def __init__(self, parent=None):
            super(_FHImportDialog, self).__init__(parent)
            self.setWindowTitle(translate(
                "EM", "Import FastHenry input files"))
            self.setMinimumWidth(620)

            layout = QtWidgets.QVBoxLayout(self)
            description = QtWidgets.QLabel(
                translate("EM", "Select the FastHenry input file."),
                self)
            layout.addWidget(description)

            file_layout = QtWidgets.QHBoxLayout()
            self.fileEdit = QtWidgets.QLineEdit(self)
            file_layout.addWidget(self.fileEdit)
            browse_button = QtWidgets.QPushButton(
                translate("EM", "Browse..."), self)
            browse_button.clicked.connect(self.browse)
            file_layout.addWidget(browse_button)
            layout.addLayout(file_layout)

            self.textCheck = QtWidgets.QCheckBox(
                translate("EM", "Also open all input files for text editing"), self)
            layout.addWidget(self.textCheck)

            self.buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Ok |
                QtWidgets.QDialogButtonBox.Cancel,
                QtCore.Qt.Horizontal, self)
            self.buttons.accepted.connect(self.accept)
            self.buttons.rejected.connect(self.reject)
            layout.addWidget(self.buttons)

            # restore the last import location and text-view selection
            preferences = FreeCAD.ParamGet(
                "User parameter:BaseApp/Preferences/Mod/EM")
            self.folder = preferences.GetString(
                "FHImportFolder", FreeCAD.ConfigGet("UserHomePath"))
            self.textCheck.setChecked(preferences.GetBool(
                "FHImportViewText", False))

        def browse(self):
            selected = QtWidgets.QFileDialog.getOpenFileName(
                self, translate("EM", "Import FastHenry file"),
                self.folder, FHIMPORT_FILTER)
            if isinstance(selected, (tuple, list)):
                selected = selected[0]
            if selected:
                self.fileEdit.setText(selected)
                self.folder = os.path.dirname(selected)

        def selectedFile(self):
            return str(self.fileEdit.text()).strip()

        def viewText(self):
            return self.textCheck.isChecked()

        def accept(self):
            filename = self.selectedFile()
            if not os.path.isfile(filename):
                QtWidgets.QMessageBox.warning(
                    self, translate("EM", "Invalid FastHenry input file"),
                    translate("EM", "Select an existing input file."))
                return
            # remember successful dialog choices for the next import
            preferences = FreeCAD.ParamGet(
                "User parameter:BaseApp/Preferences/Mod/EM")
            preferences.SetString("FHImportFolder", os.path.dirname(filename))
            preferences.SetBool("FHImportViewText", self.viewText())
            super(_FHImportDialog, self).accept()


    class _CommandFHImport:
        '''The EM FastHenry import command definition.'''
        def GetResources(self):
            return {
                'Pixmap': os.path.join(iconPath, 'EM_FHImport.svg'),
                'MenuText': QT_TRANSLATE_NOOP(
                    "EM_FHImport", "Import FastHenry file"),
                'Accel': "E, J",
                'ToolTip': QT_TRANSLATE_NOOP(
                    "EM_FHImport",
                    "Imports FastHenry geometry, including nonuniform planes, and optionally opens its text files")}

        def IsActive(self):
            return True

        def Activated(self):
            dialog = _FHImportDialog(FreeCADGui.getMainWindow())
            if dialog.exec_() != QtWidgets.QDialog.Accepted:
                return

            if FreeCAD.ActiveDocument is None:
                FreeCAD.newDocument(_fh_document_name(dialog.selectedFile()))
            document = FreeCAD.ActiveDocument
            try:
                FreeCADGui.activateView("Gui::View3DInventor", False)
            except (AttributeError, RuntimeError, TypeError):
                pass
            mdi_area = _fh_mdi_area()
            model_window = (mdi_area.activeSubWindow()
                            if mdi_area is not None else None)
            if isinstance(model_window, _FHTextWindow):
                if model_window.documentName == document.Name:
                    model_window = model_window.modelWindow
                else:
                    model_window = None
            # make the complete input import one undoable FreeCAD operation
            document.openTransaction(translate(
                "EM", "Import FastHenry file"))
            try:
                result = importFHInputFile(dialog.selectedFile(),
                                           dialog.viewText(), model_window)
                if result:
                    document.commitTransaction()
                    _fh_activate_model_view(result, model_window)
                else:
                    document.abortTransaction()
            except Exception as error:
                document.abortTransaction()
                FreeCAD.Console.PrintError(
                    translate("EM", "FastHenry import failed: ") +
                    str(error) + "\n")


    # register the command only when the graphical interface is available
    FreeCADGui.addCommand('EM_FHImport', _CommandFHImport())
