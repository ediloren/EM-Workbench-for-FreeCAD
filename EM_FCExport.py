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
#***************************************************************************


"""Explicit panelization and export commands for FasterCap / FastCap."""

# Export pipeline notes:
# - Export consumes the last explicit panelization, so files match the preview.
# - List records carry material data; geometry files contain their panels only.
# - FreeCAD millimetres are converted to FCSolver Units at the text boundary.
# - Generated names are sanitized and made case-insensitively unique.
# - Every output is staged beside its destination and atomically replaced,
#   preventing an interrupted write from leaving a mixed solver input set.

import os
import re
import tempfile

import FreeCAD

from EM_FCPanelization import (
    FC_ELEMENT_SEGMENT, FCPanelizationCancelled, FCPanelizationError,
    createFCPanelization, getFCPanelization, getFCPanelizationSignature)
from EM_FCSolver import EMFCSOLVER_UNITS, EMFCSOLVER_UNITS_VALS

if FreeCAD.GuiUp:
    import FreeCADGui
    from DraftTools import translate
    from PySide.QtCore import QT_TRANSLATE_NOOP
    try:
        from PySide import QtCore, QtWidgets
        QMessageBox = QtWidgets.QMessageBox
    except (ImportError, AttributeError):
        from PySide import QtCore, QtGui
        QtWidgets = QtGui
        QMessageBox = QtGui.QMessageBox
else:
    def translate(context, text):
        return text

    def QT_TRANSLATE_NOOP(context, text):
        return text


__dir__ = os.path.dirname(__file__)
iconPath = os.path.join(__dir__, "Resources")


def _type_of(obj):
    return getattr(getattr(obj, "Proxy", None), "Type", None)


def _solver(document):
    solvers = [obj for obj in getattr(document, "Objects", [])
               if _type_of(obj) == "FCSolver"]
    if len(solvers) != 1:
        raise FCPanelizationError(
            "Exactly one FCSolver is required; found %d" % len(solvers))
    return solvers[0]


def _safe_name(value, fallback):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    return value or fallback


# Convert FreeCAD millimetres into the selected solver unit.  Material values
# remain dimensionless and are never scaled.
def _coordinate_scale(units):
    try:
        metres_per_unit = EMFCSOLVER_UNITS_VALS[
            EMFCSOLVER_UNITS.index(units)]
    except ValueError:
        raise FCPanelizationError("Unsupported FCSolver Units '%s'" % units)
    return 1.0e-3 / metres_per_unit


def _number(value):
    return "%.15g" % float(value)


def _byte(value):
    """Convert a normalized FreeCAD material component to one RGBA byte."""
    return max(0, min(255, int(round(float(value) * 255.0))))


def _fastercap_color(fc_object):
    """Return FasterCap's 0xRRGGBBAA color for an FC object.

    The standard Part Transparency property is an actual transparency in
    percent (zero is opaque), whereas FasterCap's final hexadecimal byte is
    alpha/opacity (ff is opaque). Shape Appearance may override both the
    legacy ShapeColor and Transparency values, so follow the same precedence
    as the transient FC panel preview.
    """
    view = getattr(fc_object, "ViewObject", None)
    if view is None:
        return "0xffffffff"
    try:
        color = tuple(view.ShapeColor)
        transparency = max(0.0, min(1.0, float(view.Transparency) / 100.0))
        appearances = list(view.ShapeAppearance)
        if appearances:
            material = appearances[0]
            color = tuple(material.DiffuseColor)
            transparency = max(0.0, min(1.0, float(material.Transparency)))
        red, green, blue = (_byte(component) for component in color[:3])
        alpha = _byte(1.0 - transparency)
        return "0x%02x%02x%02x%02x" % (red, green, blue, alpha)
    except (AttributeError, IndexError, TypeError, ValueError):
        # A headless or older view provider need not expose Shape Appearance.
        return "0xffffffff"


def _point_fields(point, dimension, scale):
    count = 2 if dimension == "2D" else 3
    return [_number(point[index] * scale) for index in range(count)]


# Serialize only coordinates meaningful to the model dimension; FasterCap 3D
# dielectric records may additionally carry a per-panel reference point.
def _panel_line(panel, conductor_name, dimension, scale,
                panel_reference=False):
    fields = [panel.kind, conductor_name]
    for point in panel.points:
        fields.extend(_point_fields(point, dimension, scale))
    if panel_reference and panel.reference_point is not None:
        fields.extend(_point_fields(panel.reference_point, dimension, scale))
    return " ".join(fields)


def _geometry_text(title, panels, conductor_name, dimension, scale,
                   panel_references=False):
    lines = ["0 " + title, "*"]
    lines.extend(_panel_line(
        panel, conductor_name, dimension, scale, panel_references)
                 for panel in panels)
    return "\n".join(lines) + "\n"


# One conductor may require several C records when different boundary portions
# see different surrounding permittivities.
def _group_conductor_panels(panelization, entity):
    groups = {}
    for panel in panelization.panels_for(entity.fc_object):
        if panel.entity.kind != "FCConductor":
            continue
        key = round(float(panel.surrounding_permittivity), 12)
        groups.setdefault(key, []).append(panel)
    return [(permittivity, groups[permittivity])
            for permittivity in sorted(groups)]


# FasterCap 3D groups dielectric panels by ordered outer/inner material pair.
def _group_fastercap_dielectrics(panelization, entity):
    groups = {}
    for panel in panelization.panels_for(entity.fc_object):
        if panel.entity.kind != "FCDielectric":
            continue
        key = (round(float(panel.outer_permittivity), 12),
               round(float(panel.inner_permittivity), 12))
        groups.setdefault(key, []).append(panel)
    return [(key, groups[key]) for key in sorted(groups)]


def _list_conductor_line(filename, permittivity, dimension, continuation,
                         color=None):
    offsets = ["0", "0"] if dimension == "2D" else ["0", "0", "0"]
    fields = ["C", filename, _number(permittivity)] + offsets
    if continuation:
        fields.append("+")
    if color is not None:
        fields.append(color)
    return " ".join(fields)


def _list_dielectric_line(filename, outer, inner, reference,
                          reference_side, dimension, scale, color=None):
    offsets = ["0", "0"] if dimension == "2D" else ["0", "0", "0"]
    fields = ["D", filename, _number(outer), _number(inner)] + offsets
    fields.extend(_point_fields(reference, dimension, scale))
    if reference_side == "inner":
        fields.append("-")
    if color is not None:
        fields.append(color)
    return " ".join(fields)


# In 2D the zero-potential reference conductor is emitted after signal
# conductors, with dielectric interfaces following conductor records.
def _ordered_entities(panelization):
    entities = list(panelization.geometry.entities)
    if panelization.context.dimension != "2D":
        return entities
    reference = panelization.context.reference_conductor
    return sorted(entities, key=lambda entity: (
        2 if entity.kind == "FCDielectric" else
        (1 if entity.fc_object is reference else 0),
        0 if entity.kind == "FCConductor" else 2,
        getattr(entity.fc_object, "Name", "")))


# Build the complete in-memory export set before opening any destination file.
def _build_export_files(panelization, list_filename):
    context = panelization.context
    target = context.target_solver
    dimension = context.dimension
    scale = _coordinate_scale(context.units)
    extension = ".qui" if target == "FastCap" else ".txt"
    stem = os.path.splitext(os.path.basename(list_filename))[0]
    files = {}
    list_lines = [
        "* %s %s input generated by FreeCAD EM Workbench" %
        (dimension, target),
        "* Geometry units: %s" % context.units,
        "*"]

    used_names = set()

    def geometry_name(base):
        candidate = _safe_name("%s_%s%s" % (stem, base, extension),
                               "fc_geometry" + extension)
        suffix = 2
        while candidate.lower() in used_names:
            candidate = _safe_name(
                "%s_%s_%d%s" % (stem, base, suffix, extension),
                "fc_geometry_%d%s" % (suffix, extension))
            suffix += 1
        used_names.add(candidate.lower())
        return candidate

    for entity in _ordered_entities(panelization):
        object_name = _safe_name(
            getattr(entity.fc_object, "Label", entity.fc_object.Name),
            entity.fc_object.Name)
        solver_name = _safe_name(
            getattr(entity.fc_object, "Name", object_name), object_name)
        # FasterCap stores an element display color on its C/D list record.
        # FastCap does not define that optional extension, so retain its
        # strictly portable output grammar.
        color = (_fastercap_color(entity.fc_object)
                 if target == "FasterCap" else None)
        if entity.kind == "FCConductor":
            groups = _group_conductor_panels(panelization, entity)
            for index, (permittivity, panels) in enumerate(groups):
                filename = geometry_name(
                    "%s_c%d" % (object_name, index + 1))
                files[filename] = _geometry_text(
                    "%s conductor panels" % object_name, panels,
                    solver_name, dimension, scale)
                list_lines.append(_list_conductor_line(
                    filename, permittivity, dimension,
                    index < len(groups) - 1, color))
            continue

        if target == "FasterCap" and dimension == "3D":
            groups = _group_fastercap_dielectrics(panelization, entity)
            for index, ((outer, inner), panels) in enumerate(groups):
                filename = geometry_name(
                    "%s_d%d" % (object_name, index + 1))
                files[filename] = _geometry_text(
                    "%s dielectric panels" % object_name, panels,
                    solver_name, dimension, scale, panel_references=True)
                reference = next(
                    (panel.reference_point for panel in panels
                     if panel.reference_point is not None), None)
                if reference is None:
                    raise FCPanelizationError(
                        "No reference point for dielectric '%s'" %
                        object_name)
                list_lines.append(_list_dielectric_line(
                    filename, outer, inner, reference, "outer",
                    dimension, scale, color))
        else:
            groups = [group for group in panelization.dielectric_groups
                      if group.entity is entity]
            for index, group in enumerate(groups):
                filename = geometry_name(
                    "%s_d%d" % (object_name, index + 1))
                files[filename] = _geometry_text(
                    "%s dielectric panels" % object_name,
                    group.panels, solver_name, dimension, scale)
                list_lines.append(_list_dielectric_line(
                    filename, group.outer_permittivity,
                    group.inner_permittivity, group.reference_point,
                    group.reference_side, dimension, scale, color))

    files[os.path.basename(list_filename)] = (
        "\n".join(list_lines) + "\n")
    return files


# Stage every member first, then replace destinations only after all writes
# succeed; finally cleanup covers failures during either phase.
def _write_files_atomically(folder, files, overwrite):
    os.makedirs(folder, exist_ok=True)
    paths = [os.path.join(folder, name) for name in files]
    conflicts = [path for path in paths if os.path.exists(path)]
    if conflicts and not overwrite:
        raise FileExistsError(conflicts[0])

    staged = []
    try:
        for name, contents in files.items():
            handle, temporary = tempfile.mkstemp(
                prefix=".fc-export-", dir=folder, text=True)
            staged.append((temporary, os.path.join(folder, name)))
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fid:
                fid.write(contents)
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _destination in staged:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return paths


def _panelization_sources_touched(panelization):
    """Return True when source geometry has pending document recomputation."""
    objects = []
    for entity in panelization.geometry.entities:
        objects.append(entity.fc_object)
        objects.extend(reference.source_object
                       for reference in entity.source_references)
    for obj in objects:
        try:
            if obj.isTouched():
                return True
        except (AttributeError, RuntimeError, TypeError):
            continue
    return False


# Export warns about a stale signature but deliberately writes the frozen cache:
# silently regenerating would make output differ from the inspected preview.
def exportFCPanelization(document=None, folder=None, filename=None,
                         overwrite=False):
    """Export the current validated preview to .lst and geometry files."""
    if document is None:
        document = FreeCAD.ActiveDocument
    if document is None:
        raise FCPanelizationError("No active document")
    solver = _solver(document)
    panelization = getFCPanelization(document)
    if panelization is None:
        raise FCPanelizationError(
            "Create the panelization before exporting")
    if panelization.context.solver is not solver:
        raise FCPanelizationError(
            "The cached panelization belongs to a different FCSolver")
    if (panelization.signature !=
            getFCPanelizationSignature(document, solver) or
            _panelization_sources_touched(panelization)):
        FreeCAD.Console.PrintWarning(translate(
            "EM",
            "Warning: the FC model changed after panelization; exporting the existing static panelization.\n"))
    if panelization.has_errors:
        error_count = sum(
            item.severity == "error"
            for item in panelization.diagnostics)
        raise FCPanelizationError(
            "Panelization contains %d error(s); inspect the red panels and diagnostics before exporting"
            % error_count)

    folder = folder or str(getattr(solver, "Folder", ""))
    if not folder:
        folder = FreeCAD.ConfigGet("UserHomePath")
    filename = filename or str(getattr(solver, "Filename", ""))
    if not filename:
        filename = "%s_fastercap.lst" % getattr(document, "Name", "model")
    if not filename.lower().endswith(".lst"):
        filename += ".lst"
    solver.Folder = folder
    solver.Filename = filename

    files = _build_export_files(panelization, filename)
    paths = _write_files_atomically(folder, files, overwrite)
    FreeCAD.Console.PrintMessage(
        translate("EM", "Exported FasterCap/FastCap list and geometry files to '%s'.\n")
        % folder)
    return paths


def _print_diagnostics(panelization):
    for item in panelization.diagnostics:
        prefix = {
            "error": "Error", "warning": "Warning"}.get(
                item.severity, "Info")
        location = item.object_name or "model"
        if item.component_index is not None:
            location += "/component %d" % item.component_index
        message = "%s [%s] %s: %s\n" % (
            prefix, item.code, location, item.message)
        if item.severity == "error":
            FreeCAD.Console.PrintError(message)
        elif item.severity == "warning":
            FreeCAD.Console.PrintWarning(message)
        else:
            FreeCAD.Console.PrintMessage(message)


# Panelization is the explicit boundary between live CAD and frozen solver data.
class _CommandFCPanelize:
    """Explicit FasterCap / FastCap panelization command."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(iconPath, "EM_FCPanelize.svg"),
            "MenuText": QT_TRANSLATE_NOOP(
                "EM_FCPanelize", "Create FC Panelization"),
            "Accel": "E, M",
            "ToolTip": QT_TRANSLATE_NOOP(
                "EM_FCPanelize",
                "Resolve and panelize all FasterCap/FastCap geometry for inspection")}

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        # The computational pipeline remains Qt-independent. This dialog only
        # receives notifications at its safe phase boundaries, where it pumps
        # events and can request a clean cancellation.
        dialog = QtWidgets.QProgressDialog(
            translate("EM", "Preparing panelization"),
            translate("EM", "Cancel"), 0, 10,
            FreeCADGui.getMainWindow())
        dialog.setWindowTitle(translate(
            "EM", "FasterCap/FastCap panelization"))
        dialog.setWindowModality(QtCore.Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.show()
        progress_step = [0]

        def progress(phase):
            progress_step[0] = min(progress_step[0] + 1, dialog.maximum())
            dialog.setLabelText(translate("EM", phase))
            dialog.setValue(progress_step[0])
            application = QtWidgets.QApplication.instance()
            if application is not None:
                application.processEvents()
            if dialog.wasCanceled():
                raise FCPanelizationCancelled("Panelization cancelled by user")

        try:
            panelization = createFCPanelization(
                FreeCAD.ActiveDocument, progress=progress)
        except FCPanelizationCancelled:
            FreeCAD.Console.PrintMessage(translate(
                "EM", "FasterCap/FastCap panelization cancelled.\n"))
            return
        except Exception as error:
            FreeCAD.Console.PrintError(
                translate("EM", "FasterCap/FastCap panelization failed: %s\n")
                % error)
            return
        finally:
            dialog.close()
        _print_diagnostics(panelization)
        errors = sum(item.severity == "error"
                     for item in panelization.diagnostics)
        warnings = sum(item.severity == "warning"
                       for item in panelization.diagnostics)
        FreeCAD.Console.PrintMessage(translate(
            "EM",
            "FasterCap/FastCap panelization created: %d panels, %d errors, %d warnings.\n")
            % (len(panelization.panels), errors, warnings))


# Overwrite consent applies to the whole generated set, not just its list file.
class _CommandFCExport:
    """Validated FasterCap / FastCap multi-file export command."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(iconPath, "EM_FCExport.svg"),
            "MenuText": QT_TRANSLATE_NOOP(
                "EM_FCExport", "Export FasterCap / FastCap"),
            "Accel": "E, L",
            "ToolTip": QT_TRANSLATE_NOOP(
                "EM_FCExport",
                "Export the current validated FC panelization")}

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        document = FreeCAD.ActiveDocument
        try:
            exportFCPanelization(document)
            return
        except FileExistsError as error:
            path = str(error)
            dialog = QMessageBox()
            dialog.setText(
                translate("EM", "One or more export files already exist."))
            dialog.setInformativeText(
                translate("EM", "Overwrite the FasterCap/FastCap export set?\n")
                + path)
            dialog.setStandardButtons(
                QMessageBox.Cancel | QMessageBox.Ok)
            if dialog.exec_() != QMessageBox.Ok:
                return
        except Exception as error:
            FreeCAD.Console.PrintError(
                translate("EM", "FasterCap/FastCap export failed: %s\n")
                % error)
            return
        try:
            exportFCPanelization(document, overwrite=True)
        except Exception as error:
            FreeCAD.Console.PrintError(
                translate("EM", "FasterCap/FastCap export failed: %s\n")
                % error)


if FreeCAD.GuiUp:
    FreeCADGui.addCommand("EM_FCPanelize", _CommandFCPanelize())
    FreeCADGui.addCommand("EM_FCExport", _CommandFCExport())
