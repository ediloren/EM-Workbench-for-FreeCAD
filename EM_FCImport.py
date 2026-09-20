#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2026                                                    *
#*   FastFieldSolvers S.R.L., http://www.fastfieldsolvers.com              *
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


__title__="FreeCAD E.M. Workbench FasterCap / FastCap import command"
__author__ = "FastFieldSolvers S.R.L."
__url__ = "http://www.fastfieldsolvers.com"

import os
import re

import FreeCAD

# Import and editor notes:
# - File discovery follows physical references and embedded F/FILE sections.
# - Relative paths use the containing file, matching FasterCap semantics.
# - Cycle and depth checks bound malformed or mutually recursive inputs.
# - One editor represents each physical or logical section; only physical files
#   can be saved because embedded sections have no independent pathname.
# - GUI classes exist only with GuiUp, keeping console imports Qt-independent.
# - Geometry parsing remains in import_fastercap.py; this module owns commands,
#   discovery, syntax highlighting, and the optional MDI viewer.

from import_fastercap import read_fastcap_file

if FreeCAD.GuiUp:
    import FreeCADGui
    from DraftTools import translate
    from PySide import QtCore, QtGui
    try:
        from PySide import QtWidgets
    except ImportError:
        # PySide 1 keeps widget classes in QtGui.
        QtWidgets = QtGui
    # QShortcut moved from QtWidgets to QtGui in Qt 6. FreeCAD's ``PySide``
    # compatibility namespace follows the location used by its Qt version.
    if hasattr(QtWidgets, "QShortcut"):
        _FCQShortcut = QtWidgets.QShortcut
    else:
        _FCQShortcut = QtGui.QShortcut
    from PySide.QtCore import QT_TRANSLATE_NOOP
else:
    # \cond
    def translate(ctxt, txt):
        return txt
    def QT_TRANSLATE_NOOP(ctxt, txt):
        return txt
    # \endcond

__dir__ = os.path.dirname(__file__)
iconPath = os.path.join(__dir__, 'Resources')

# defines
#
# importer limits and file-selection filter
FCIMPORT_MAX_PARSE_LEVEL = 32
FCIMPORT_FILTER = QT_TRANSLATE_NOOP(
    "EM_FCImport",
    "FasterCap / FastCap files (*.lst *.txt *.qui *.geo *.inp);;All files (*)")

# FasterCap / FastCap text-editor syntax colors.
EM_FCIMPORT_COMMENT_COLOR = "#808080"
EM_FCIMPORT_REFERENCE_COLOR = "#008b8b"
EM_FCIMPORT_CONDUCTOR_COLOR = "#2a82da"
EM_FCIMPORT_PANEL_COLOR = "#24913c"
EM_FCIMPORT_CONTAINER_COLOR = "#8a46a3"
EM_FCIMPORT_NUMBER_COLOR = "#b05a00"
EM_FCIMPORT_COMPLEX_COLOR = "#b05a00"
EM_FCIMPORT_HEX_COLOR = "#c03080"


def _fc_record(fields):
    """Return the normalized record name used while following input files."""
    if not fields:
        return ""
    record = fields[0].upper()
    if record in ("F", "FILE"):
        return "F"
    if record in ("E", "END"):
        return "E"
    return record


def _fc_read_lines(path):
    """Read an input file while retaining line numbers for its subfiles."""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as stream:
        return list(enumerate(stream, 1))


# Scan top-level F/FILE markers once and map logical section names to their
# bounded line ranges; nested parsing then reuses these ranges.
def _fc_embedded_files(lines):
    """Return the definitions embedded between File and End records."""
    embedded = {}
    current = None
    for line_number, line in lines:
        fields = line.split()
        record = _fc_record(fields)
        if record == "F":
            if len(fields) < 2:
                continue
            current = fields[1]
            embedded[current] = []
        elif record == "E":
            current = None
        elif current is not None:
            embedded[current].append((line_number, line))
    return embedded


# Return physical and embedded sources in traversal order while suppressing
# duplicates, cycles, and references beyond the defensive depth limit.
def getFCInputFiles(filename):
    '''Return the physical files in a FasterCap / FastCap input hierarchy.

       'filename' is the root list or geometry file. C and D references are
            followed recursively relative to the directory of the containing
            physical file. Definitions embedded between File and End records
            are traversed as part of their containing file and therefore do
            not add another filename to the returned list.

       Files are returned in first-use order and each physical file occurs
       only once. Missing references are reported through the FreeCAD console.
    '''
    root = os.path.abspath(os.path.expanduser(filename))
    files = []
    physical_files = set()
    logical_files = set()

    # Physical files establish a new relative-path base and may themselves host
    # several named embedded geometry sections.
    def parse_physical(path, depth):
        path = os.path.abspath(path)
        identity = os.path.normcase(os.path.realpath(path))
        if identity in physical_files:
            return
        if depth >= FCIMPORT_MAX_PARSE_LEVEL:
            FreeCAD.Console.PrintWarning(
                translate("EM", "Maximum FasterCap input nesting depth reached at ") +
                "'" + path + "'\n")
            return
        try:
            lines = _fc_read_lines(path)
        except OSError as error:
            FreeCAD.Console.PrintWarning(
                translate("EM", "Cannot open referenced FasterCap file ") +
                "'" + path + "': " + str(error) + "\n")
            return

        physical_files.add(identity)
        files.append(path)
        parse_logical(path, lines, _fc_embedded_files(lines), None, depth)

    # Logical sections inherit their parent path context but are not independently
    # writable filesystem resources.
    def parse_logical(path, lines, embedded, section, depth):
        identity = (os.path.normcase(os.path.realpath(path)), section or "")
        if identity in logical_files:
            return
        logical_files.add(identity)

        inside_embedded = False
        for _line_number, line in lines:
            fields = line.split()
            if not fields or fields[0].startswith(("*", "#", ";")):
                continue
            record = _fc_record(fields)
            if section is None and record == "F":
                inside_embedded = True
                continue
            if section is None and record == "E":
                inside_embedded = False
                continue
            if inside_embedded or record not in ("C", "D") or len(fields) < 2:
                continue

            child_name = fields[1]
            child_lines = embedded.get(child_name)
            if child_lines is not None:
                parse_logical(path, child_lines, embedded, child_name, depth + 1)
            else:
                child_path = (child_name if os.path.isabs(child_name)
                              else os.path.join(os.path.dirname(path), child_name))
                parse_physical(child_path, depth + 1)

    parse_physical(root, 0)
    return files


# Open every discovered source in the MDI viewer, preserving the root model so
# reload can rebuild the same physical/logical editor set.
def openFCTextFiles(filename, model=None):
    '''Open all physical files in a FasterCap / FastCap hierarchy for editing.

       'filename' is the root input filename. Every external file referenced
            by a C or D statement is opened in a separate FreeCAD MDI tab or
            window. Combined-file definitions remain in the root file editor.
       'model' is the imported outer compound associated with the editors;
            it is used by their Save and reload model context-menu action.

       The function returns the list of editor windows that were opened or
       activated. It returns an empty list outside the FreeCAD GUI.
    '''
    if not FreeCAD.GuiUp:
        FreeCAD.Console.PrintWarning(
            translate("EM", "FasterCap text files require the FreeCAD GUI.\n"))
        return []

    root = os.path.abspath(os.path.expanduser(filename))
    editors = []
    for path in getFCInputFiles(root):
        editor = _open_fc_text_file(path, root, model)
        if editor is not None:
            editors.append(editor)
    return editors


def _fc_document_name(path):
    """Build a valid, unused FreeCAD document name from an input filename."""
    base = os.path.splitext(os.path.basename(path))[0]
    base = re.sub(r"[^A-Za-z0-9_]", "_", base)
    if not base or base[0].isdigit():
        base = "FasterCap_" + base
    documents = FreeCAD.listDocuments() if hasattr(FreeCAD, "listDocuments") else {}
    name = base
    suffix = 1
    while name in documents:
        suffix += 1
        name = "%s_%d" % (base, suffix)
    return name


# Geometry import delegates parsing to the reader, then optionally opens source
# text; document creation and GUI presentation remain separate concerns.
def importFCInputFile(filename, viewText=False):
    '''Import a FasterCap / FastCap file hierarchy into the active document.

       'filename' is the root list or geometry file to import.
       'viewText', when True, also opens every physical input file in a
            separate syntax-highlighted editor tab or window inside FreeCAD.

       Geometry is always imported as a Part::Compound containing separate
       conductor and dielectric compounds. The mesh importer is deliberately
       not exposed by this workbench command. The function returns the outer
       Part::Compound, or False when the geometry cannot be imported.
    '''
    path = os.path.abspath(os.path.expanduser(filename))
    if not os.path.isfile(path):
        FreeCAD.Console.PrintError(
            translate("EM", "FasterCap input file does not exist: ") +
            "'" + path + "'\n")
        return False

    if FreeCAD.ActiveDocument is None:
        FreeCAD.newDocument(_fc_document_name(path))

    result = read_fastcap_file(os.path.basename(path), os.path.dirname(path),
                               usePartType='compound')
    if FreeCAD.GuiUp and viewText:
        # Keep the files available for inspection and correction even when the
        # geometry parser reports an error.
        openFCTextFiles(path, result)
    if not result:
        return False

    if FreeCAD.GuiUp:
        try:
            FreeCADGui.activeDocument().activeView().fitAll()
        except AttributeError:
            pass
    return result


if FreeCAD.GuiUp:
    class _FCSyntaxHighlighter(QtGui.QSyntaxHighlighter):
        """Syntax coloring for FasterCap / FastCap list and geometry files."""
        def __init__(self, document):
            super(_FCSyntaxHighlighter, self).__init__(document)

            self.commentFormat = self._format(
                EM_FCIMPORT_COMMENT_COLOR, italic=True)
            self.referenceFormat = self._format(EM_FCIMPORT_REFERENCE_COLOR)
            self.conductorFormat = self._format(
                EM_FCIMPORT_CONDUCTOR_COLOR, bold=True)
            self.geometryFormat = self._format(
                EM_FCIMPORT_PANEL_COLOR, bold=True)
            self.containerFormat = self._format(
                EM_FCIMPORT_CONTAINER_COLOR, bold=True)
            self.numberFormat = self._format(EM_FCIMPORT_NUMBER_COLOR)
            self.complexFormat = self._format(
                EM_FCIMPORT_COMPLEX_COLOR, bold=True)
            self.colorFormat = self._format(EM_FCIMPORT_HEX_COLOR)

            self.numberExpression = re.compile(
                r"(?<![\w.])[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
            self.colorExpression = re.compile(r"\b0x[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\b")
            self.complexExpression = re.compile(r"(?i)(?<!\w)j(?=[+-]?(?:\d|\.))")
            self.recordExpression = re.compile(
                r"^(\s*)(File|End|F|E|C|D|B|G|T|Q|S|N)\b", re.IGNORECASE)

        @staticmethod
        def _format(color, bold=False, italic=False):
            text_format = QtGui.QTextCharFormat()
            text_format.setForeground(QtGui.QColor(color))
            if bold:
                text_format.setFontWeight(QtGui.QFont.Bold)
            text_format.setFontItalic(italic)
            return text_format

        def _apply(self, expression, text, text_format):
            for match in expression.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(),
                               text_format)

        def highlightBlock(self, text):
            text = str(text)
            # Both formats reserve the first physical line for a title or
            # comment. FastCap requires that title to start with 0; FasterCap
            # ignores it regardless of its first character.
            if (self.currentBlock().blockNumber() == 0 or
                    re.match(r"^\s*[*#;]", text)):
                self.setFormat(0, len(text), self.commentFormat)
                return

            self._apply(self.numberExpression, text, self.numberFormat)
            self._apply(self.complexExpression, text, self.complexFormat)
            self._apply(self.colorExpression, text, self.colorFormat)

            record_match = self.recordExpression.search(text)
            if record_match is None:
                return
            record = record_match.group(2).upper()
            if record in ("C", "D", "B"):
                record_format = self.conductorFormat
            elif record in ("T", "Q", "S"):
                record_format = self.geometryFormat
            else:
                record_format = self.containerFormat
            self.setFormat(record_match.start(2), len(record_match.group(2)),
                           record_format)

            # Color file, conductor, and group names after the statement. N has
            # both an old and a new conductor name; End has no argument.
            reference_count = 2 if record == "N" else (
                0 if record in ("E", "END") else 1)
            tail_start = record_match.end()
            for index, reference in enumerate(
                    re.finditer(r"\S+", text[tail_start:])):
                if index >= reference_count:
                    break
                start = tail_start + reference.start()
                self.setFormat(start, len(reference.group(0)),
                               self.referenceFormat)


    # Each subwindow tracks one source plus root-model context for coordinated
    # reload, Save All, and shutdown behavior.
    class _FCTextWindow(QtWidgets.QMdiSubWindow):
        """Editable view of one physical FasterCap / FastCap input file."""
        def __init__(self, path, parent=None):
            super(_FCTextWindow, self).__init__(parent)
            self.path = os.path.abspath(path)
            self.rootPath = None
            self.documentName = ""
            self.modelObjectNames = []
            self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
            self.setWindowTitle(os.path.basename(self.path) + "[*] - FasterCap")

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
            wrap_lines = preferences.GetBool("FCImportWrapText", False)
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
            close_all_button = QtWidgets.QPushButton(
                translate("EM", "Close All"), container)
            close_all_button.clicked.connect(self.closeAllEditors)
            button_layout.addWidget(close_all_button)
            layout.addLayout(button_layout)

            self.setWidget(container)
            # attach syntax coloring and propagate document changes to the MDI tab
            self.highlighter = _FCSyntaxHighlighter(self.editor.document())
            self.editor.document().modificationChanged.connect(
                self.setWindowModified)

            # keep Ctrl+S local to the active input-file editor
            shortcut = _FCQShortcut(QtGui.QKeySequence.Save, self)
            shortcut.activated.connect(self.saveFile)
            self.saveShortcut = shortcut
            self.loadFile()
            self.resize(820, 560)

        def setImportContext(self, root_path, model=None):
            """Associate this editor with its root file and imported geometry."""
            self.rootPath = os.path.abspath(os.path.expanduser(root_path))
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
            """Save this input hierarchy and replace its imported geometry."""
            if not self.rootPath:
                FreeCAD.Console.PrintWarning(
                    translate("EM", "This editor is not associated with an imported model.\n"))
                return False

            # save every physical file belonging to the same root hierarchy
            related_editors = [
                editor for editor in list(_fc_text_windows.values())
                if getattr(editor, "rootPath", None) == self.rootPath]
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
                    translate("EM", "Cannot reload FasterCap model: its document is closed.\n"))
                return False

            # delete and rebuild the complete model as one undoable operation
            FreeCAD.setActiveDocument(document.Name)
            document.openTransaction(translate(
                "EM", "Reload FasterCap / FastCap model"))
            try:
                for name in self.modelObjectNames:
                    if document.getObject(name) is not None:
                        document.removeObject(name)
                result = importFCInputFile(self.rootPath, False)
                if not result:
                    document.abortTransaction()
                    document.recompute()
                    return False
                document.commitTransaction()
            except Exception as error:
                document.abortTransaction()
                document.recompute()
                FreeCAD.Console.PrintError(
                    translate("EM", "FasterCap model reload failed: ") +
                    str(error) + "\n")
                return False

            # update every related editor to point at the replacement objects
            for editor in related_editors:
                try:
                    editor.setImportContext(self.rootPath, result)
                except RuntimeError:
                    continue
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.Selection.addSelection(result)
            FreeCAD.Console.PrintMessage(
                translate("EM", "Reloaded FasterCap / FastCap model from ") +
                self.rootPath + "\n")
            return True

        def setLineWrap(self, enabled):
            mode = (QtWidgets.QPlainTextEdit.WidgetWidth if enabled
                    else QtWidgets.QPlainTextEdit.NoWrap)
            self.editor.setLineWrapMode(mode)
            # share the display preference between all subsequently opened files
            FreeCAD.ParamGet(
                "User parameter:BaseApp/Preferences/Mod/EM").SetBool(
                    "FCImportWrapText", enabled)

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
                    self, translate("EM", "Cannot save FasterCap file"),
                    str(error))
                return False
            self.editor.document().setModified(False)
            FreeCAD.Console.PrintMessage(
                translate("EM", "Saved FasterCap file ") +
                "'" + self.path + "'\n")
            return True

        def saveAllFiles(self):
            """Save every open FasterCap / FastCap text editor."""
            for editor in list(_fc_text_windows.values()):
                try:
                    if not editor.saveFile():
                        return False
                except RuntimeError:
                    continue
            return True

        def closeAllEditors(self):
            """Close every input editor, stopping if a close is cancelled."""
            for editor in list(_fc_text_windows.values()):
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
                self, translate("EM", "Unsaved FasterCap file"),
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
    _fc_text_windows = {}


    def _fc_mdi_area():
        main_window = FreeCADGui.getMainWindow()
        central_widget = main_window.centralWidget()
        if isinstance(central_widget, QtWidgets.QMdiArea):
            return central_widget
        mdi_areas = main_window.findChildren(QtWidgets.QMdiArea)
        return mdi_areas[0] if mdi_areas else None


    # Reuse an existing window by canonical source identity so recursive includes
    # cannot open duplicate editors for the same physical file.
    def _open_fc_text_file(path, root_path=None, model=None):
        path = os.path.abspath(path)
        identity = os.path.normcase(os.path.realpath(path))
        existing = _fc_text_windows.get(identity)
        # activate an existing editor instead of opening duplicate views
        if existing is not None:
            try:
                if root_path is not None:
                    existing.setImportContext(root_path, model)
                existing.show()
                existing.raise_()
                mdi_area = existing.mdiArea()
                if mdi_area is not None:
                    mdi_area.setActiveSubWindow(existing)
                return existing
            except RuntimeError:
                _fc_text_windows.pop(identity, None)

        mdi_area = _fc_mdi_area()
        if mdi_area is None:
            FreeCAD.Console.PrintError(
                translate("EM", "Cannot find the FreeCAD MDI area for ") +
                "'" + path + "'\n")
            return None
        try:
            window = _FCTextWindow(path)
            if root_path is not None:
                window.setImportContext(root_path, model)
        except OSError as error:
            FreeCAD.Console.PrintError(
                translate("EM", "Cannot open FasterCap text file ") +
                "'" + path + "': " + str(error) + "\n")
            return None

        # register the editor with both FreeCAD's MDI area and the local cache
        mdi_area.addSubWindow(window)
        _fc_text_windows[identity] = window

        def forget_window(*_args):
            _fc_text_windows.pop(identity, None)

        window.destroyed.connect(forget_window)
        window.show()
        mdi_area.setActiveSubWindow(window)
        return window


    # The dialog gathers only path and view preference; actual parsing stays in the
    # command helper where console and scripted callers share behavior.
    class _FCImportDialog(QtWidgets.QDialog):
        """File selector with the optional text-view flag."""
        def __init__(self, parent=None):
            super(_FCImportDialog, self).__init__(parent)
            self.setWindowTitle(translate(
                "EM", "Import FasterCap / FastCap input files"))
            self.setMinimumWidth(620)

            layout = QtWidgets.QVBoxLayout(self)
            description = QtWidgets.QLabel(
                translate("EM", "Select the root FasterCap / FastCap list or geometry file."),
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
                "FCImportFolder", FreeCAD.ConfigGet("UserHomePath"))
            self.textCheck.setChecked(preferences.GetBool(
                "FCImportViewText", False))

        def browse(self):
            selected = QtWidgets.QFileDialog.getOpenFileName(
                self, translate("EM", "Import FasterCap / FastCap file"),
                self.folder, FCIMPORT_FILTER)
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
                    self, translate("EM", "Invalid FasterCap input file"),
                    translate("EM", "Select an existing input file."))
                return
            # remember successful dialog choices for the next import
            preferences = FreeCAD.ParamGet(
                "User parameter:BaseApp/Preferences/Mod/EM")
            preferences.SetString("FCImportFolder", os.path.dirname(filename))
            preferences.SetBool("FCImportViewText", self.viewText())
            super(_FCImportDialog, self).accept()


    class _CommandFCImport:
        '''The EM FasterCap / FastCap import command definition.'''
        def GetResources(self):
            return {
                'Pixmap': os.path.join(iconPath, 'EM_FCImport.svg'),
                'MenuText': QT_TRANSLATE_NOOP(
                    "EM_FCImport", "Import FasterCap / FastCap file"),
                'Accel': "E, R",
                'ToolTip': QT_TRANSLATE_NOOP(
                    "EM_FCImport",
                    "Imports FasterCap / FastCap geometry and optionally opens its text files")}

        def IsActive(self):
            return True

        def Activated(self):
            dialog = _FCImportDialog(FreeCADGui.getMainWindow())
            if dialog.exec_() != QtWidgets.QDialog.Accepted:
                return

            if FreeCAD.ActiveDocument is None:
                FreeCAD.newDocument(_fc_document_name(dialog.selectedFile()))
            document = FreeCAD.ActiveDocument
            # make the complete hierarchy import one undoable FreeCAD operation
            document.openTransaction(translate(
                "EM", "Import FasterCap / FastCap file"))
            try:
                result = importFCInputFile(dialog.selectedFile(),
                                           dialog.viewText())
                if result:
                    document.commitTransaction()
                    FreeCADGui.Selection.clearSelection()
                    FreeCADGui.Selection.addSelection(result)
                else:
                    document.abortTransaction()
            except Exception as error:
                document.abortTransaction()
                FreeCAD.Console.PrintError(
                    translate("EM", "FasterCap import failed: ") +
                    str(error) + "\n")


    # register the command only when the graphical interface is available
    FreeCADGui.addCommand('EM_FCImport', _CommandFCImport())
