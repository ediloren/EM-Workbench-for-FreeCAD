#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2018                                                    *
#*   Efficient Power Conversion Corporation, Inc.  http://epc-co.com       *
#*                                                                         *
#*   Developed by FastFieldSolvers S.R.L. under contract by EPC            *
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

__title__="FreeCAD E.M. Workbench API"
__author__ = "FastFieldSolvers - Enrico Di Lorenzo"
__url__ = "http://www.fastfieldsolvers.com"

## \defgroup EM E.M.
#  \ingroup PYTHONWORKBENCHES
#  \brief ElectroMagnetic tools
#
#  This module provides tools for ElectroMagnetic analysis,
#  enabling to create suitable geometries, launching field solvers,
#  and post-processing the results

'''The E.M. module provides tools for ElectroMagnetic analysis'''

from importlib import import_module as _import_module

# Resolve a public symbol only when a script or command first requests it.
# Importing EM itself never loads solver modules, Qt, NumPy, or SciPy.
_EXPORTS = {
    'EMFCCONDUCTOR_DEF_COLOR': 'EM_FCConductor',
    'EMFCCONDUCTOR_DEF_CURVATURE_TOLERANCE': 'EM_FCConductor',
    'EMFCCONDUCTOR_DEF_LINECOLOR': 'EM_FCConductor',
    'EMFCDIELECTRIC_DEF_ARROWCOLOR': 'EM_FCDielectric',
    'EMFCDIELECTRIC_DEF_ARROWSCALE': 'EM_FCDielectric',
    'EMFCDIELECTRIC_DEF_COLOR': 'EM_FCDielectric',
    'EMFCDIELECTRIC_DEF_CURVATURE_TOLERANCE': 'EM_FCDielectric',
    'EMFCDIELECTRIC_DEF_INNER_PERMITTIVITY': 'EM_FCDielectric',
    'EMFCDIELECTRIC_DEF_LINECOLOR': 'EM_FCDielectric',
    'EMFCDIELECTRIC_DEF_TRANSPARENCY': 'EM_FCDielectric',
    'EMFCDIELECTRIC_MAX_ARROWS': 'EM_FCDielectric',
    'EMFCDIELECTRIC_ORIENTATIONS': 'EM_FCDielectric',
    'EMFCSOLVER_DEFDIMENSION': 'EM_FCSolver',
    'EMFCSOLVER_DEFSOLVER': 'EM_FCSolver',
    'EMFCSOLVER_DEFUNITS': 'EM_FCSolver',
    'EMFCSOLVER_DEF_AUTO_MAX_ERR': 'EM_FCSolver',
    'EMFCSOLVER_DEF_EXPANSION_ORDER': 'EM_FCSolver',
    'EMFCSOLVER_DEF_FILENAME': 'EM_FCSolver',
    'EMFCSOLVER_DEF_GEOMETRY_TOLERANCE': 'EM_FCSolver',
    'EMFCSOLVER_DEF_GMRES_TOL': 'EM_FCSolver',
    'EMFCSOLVER_DEF_ITERATION_TOL': 'EM_FCSolver',
    'EMFCSOLVER_DEF_MAX_PANEL_SIZE': 'EM_FCSolver',
    'EMFCSOLVER_DEF_MESH_CURV_COEFF': 'EM_FCSolver',
    'EMFCSOLVER_DEF_MESH_EPS': 'EM_FCSolver',
    'EMFCSOLVER_DEF_PARTITIONING_DEPTH': 'EM_FCSolver',
    'EMFCSOLVER_DEF_PERMITTIVITY_FACTOR': 'EM_FCSolver',
    'EMFCSOLVER_DEF_SPACE_PERMITTIVITY': 'EM_FCSolver',
    'EMFCSOLVER_DIMENSIONS': 'EM_FCSolver',
    'EMFCSOLVER_SOLVERS': 'EM_FCSolver',
    'EMFCSOLVER_UNITS': 'EM_FCSolver',
    'EMFCSOLVER_UNITS_VALS': 'EM_FCSolver',
    'EMFHEQUIV_LENTOL': 'EM_FHEquiv',
    'EMFHNODE_DEF_NODECOLOR': 'EM_Globals',
    'EMFHNODE_DEF_NODENAMEEXT': 'EM_FHPlane',
    'EMFHNODE_DEF_NODESIZE': 'EM_FHNode',
    'EMFHNODE_DEF_PLANENODECOLOR': 'EM_FHPlane',
    'EMFHPATH_DEF_DISCR': 'EM_FHPath',
    'EMFHPATH_DEF_SEGHEIGHT': 'EM_FHPath',
    'EMFHPATH_DEF_SEGWIDTH': 'EM_FHPath',
    'EMFHPATH_TIMESWIDTH': 'EM_FHPath',
    'EMFHPLANEHOLE_DEFTYPE': 'EM_FHPlaneHole',
    'EMFHPLANEHOLE_TYPES': 'EM_FHPlaneHole',
    'EMFHPLANE_DEF_SEG1': 'EM_FHPlane',
    'EMFHPLANE_DEF_SEG2': 'EM_FHPlane',
    'EMFHPLANE_DEF_THICKNESS': 'EM_FHPlane',
    'EMFHPORT_LENTOL': 'EM_FHPort',
    'EMFHSEGMENT_DEF_SEGHEIGHT': 'EM_FHSegment',
    'EMFHSEGMENT_DEF_SEGWIDTH': 'EM_FHSegment',
    'EMFHSEGMENT_LENTOL': 'EM_Globals',
    'EMFHSEGMENT_PARTOL': 'EM_Globals',
    'EMFHSOLVER_DEFFMAX': 'EM_FHSolver',
    'EMFHSOLVER_DEFFMIN': 'EM_FHSolver',
    'EMFHSOLVER_DEFNDEC': 'EM_FHSolver',
    'EMFHSOLVER_DEFNHINC': 'EM_FHSolver',
    'EMFHSOLVER_DEFNWINC': 'EM_FHSolver',
    'EMFHSOLVER_DEFRH': 'EM_FHSolver',
    'EMFHSOLVER_DEFRW': 'EM_FHSolver',
    'EMFHSOLVER_DEFUNITS': 'EM_FHSolver',
    'EMFHSOLVER_DEF_FILENAME': 'EM_FHSolver',
    'EMFHSOLVER_DEF_SEGSIGMA': 'EM_FHSolver',
    'EMFHSOLVER_UNITS': 'EM_FHSolver',
    'EMFHSOLVER_UNITS_VALS': 'EM_FHSolver',
    'EMVHPORT_DEF_LINECOLOR': 'EM_VHPort',
    'EMVHPORT_DEF_NEGPORTCOLOR': 'EM_VHPort',
    'EMVHPORT_DEF_POSPORTCOLOR': 'EM_VHPort',
    'EMVHPORT_EPSDELTA': 'EM_VHPort',
    'EMVHPORT_SIDESTRS': 'EM_VHPort',
    'EMVHSOLVER_COND_ID_OVERFLOW': 'EM_VHSolver',
    'EMVHSOLVER_DEFFMAX': 'EM_VHSolver',
    'EMVHSOLVER_DEFFMIN': 'EM_VHSolver',
    'EMVHSOLVER_DEFNDEC': 'EM_VHSolver',
    'EMVHSOLVER_DEFNHINC': 'EM_VHSolver',
    'EMVHSOLVER_DEFNWINC': 'EM_VHSolver',
    'EMVHSOLVER_DEFRH': 'EM_VHSolver',
    'EMVHSOLVER_DEFRW': 'EM_VHSolver',
    'EMVHSOLVER_DEFUNITS': 'EM_VHSolver',
    'EMVHSOLVER_DEF_DELTA': 'EM_VHSolver',
    'EMVHSOLVER_DEF_FILENAME': 'EM_VHSolver',
    'EMVHSOLVER_DEF_MINFREQ': 'EM_VHSolver',
    'EMVHSOLVER_DEF_SHAPECOLOR': 'EM_VHSolver',
    'EMVHSOLVER_DEF_SIGMA': 'EM_VHConductor',
    'EMVHSOLVER_DEF_TRANSPARENCY': 'EM_VHSolver',
    'EMVHSOLVER_UNITS': 'EM_VHSolver',
    'EMVHSOLVER_UNITS_VALS': 'EM_VHSolver',
    'EM_AUTHOR': 'EM_About',
    'EM_FCIMPORT_COMMENT_COLOR': 'EM_FCImport',
    'EM_FCIMPORT_COMPLEX_COLOR': 'EM_FCImport',
    'EM_FCIMPORT_CONDUCTOR_COLOR': 'EM_FCImport',
    'EM_FCIMPORT_CONTAINER_COLOR': 'EM_FCImport',
    'EM_FCIMPORT_HEX_COLOR': 'EM_FCImport',
    'EM_FCIMPORT_NUMBER_COLOR': 'EM_FCImport',
    'EM_FCIMPORT_PANEL_COLOR': 'EM_FCImport',
    'EM_FCIMPORT_REFERENCE_COLOR': 'EM_FCImport',
    'EM_LICENSE': 'EM_About',
    'EM_VERSION': 'EM_Globals',
    'FCBoundingBox': 'EM_FCGeometry',
    'FCBoundingBoxIndex': 'EM_FCGeometry',
    'FCClassifierSolid': 'EM_FCGeometry',
    'FCDiagnostic': 'EM_FCGeometry',
    'FCDielectricPanelGroup': 'EM_FCPanelization',
    'FCEntityGeometry': 'EM_FCGeometry',
    'FCExportPanelizationErrors': 'EM_FCExport',
    'FCFaceGeometry': 'EM_FCGeometry',
    'FCGeometryComponent': 'EM_FCGeometry',
    'FCGeometryConfigurationError': 'EM_FCGeometry',
    'FCGeometryModel': 'EM_FCGeometry',
    'FCIMPORT_FILTER': 'EM_FCImport',
    'FCIMPORT_MAX_PARSE_LEVEL': 'EM_FCImport',
    'FCMeshingIsland': 'EM_FCPanelization',
    'FCPANEL_DEF_CURVATURE_TOLERANCE': 'EM_FCPanelization',
    'FCPANEL_FASTER_CAP_QUAD_ASPECT': 'EM_FCPanelization',
    'FCPANEL_GROUP_CANDIDATE_BLOCK': 'EM_FCPanelization',
    'FCPANEL_GROUP_PANEL_BLOCK': 'EM_FCPanelization',
    'FCPANEL_MESH_ALLOW_QUADS': 'EM_FCPanelization',
    'FCPANEL_MESH_GROWTH_RATE': 'EM_FCPanelization',
    'FCPANEL_MESH_OPTIMIZE': 'EM_FCPanelization',
    'FCPANEL_MESH_SECOND_ORDER': 'EM_FCPanelization',
    'FCPANEL_MESH_SEGMENTS_PER_EDGE': 'EM_FCPanelization',
    'FCPANEL_MIN_TRIANGLE_ANGLE': 'EM_FCPanelization',
    'FCPANEL_PATHOLOGICAL_ASPECT': 'EM_FCPanelization',
    'FCPANEL_PROGRESS_STRIDE': 'EM_FCPanelization',
    'FCPANEL_RECOVERY_MAX_FRAGMENTS': 'EM_FCPanelization',
    'FCPANEL_RECOVERY_MAX_INPUTS': 'EM_FCPanelization',
    'FCPANEL_RECOVERY_MAX_SOURCES': 'EM_FCPanelization',
    'FCPANEL_TESSELLATION_REFINEMENTS': 'EM_FCPanelization',
    'FCPanel': 'EM_FCPanelization',
    'FCPanelization': 'EM_FCPanelization',
    'FCPanelizationCancelled': 'EM_FCPanelization',
    'FCPanelizationError': 'EM_FCPanelization',
    'FCSolverContext': 'EM_FCGeometry',
    'FCSourceReference': 'EM_FCGeometry',
    'FCSurfacePatch': 'EM_FCPanelization',
    'FC_DIAGNOSTIC_ERROR': 'EM_FCGeometry',
    'FC_DIAGNOSTIC_INFO': 'EM_FCGeometry',
    'FC_DIAGNOSTIC_WARNING': 'EM_FCGeometry',
    'FC_ELEMENT_QUAD': 'EM_FCPanelization',
    'FC_ELEMENT_SEGMENT': 'EM_FCPanelization',
    'FC_ELEMENT_TRIANGLE': 'EM_FCPanelization',
    'FC_ENTITY_TYPES': 'EM_FCGeometry',
    'FC_POINT_BOUNDARY': 'EM_FCGeometry',
    'FC_POINT_INSIDE': 'EM_FCGeometry',
    'FC_POINT_OUTSIDE': 'EM_FCGeometry',
    'FC_POINT_UNKNOWN': 'EM_FCGeometry',
    'addToFCConductor': 'EM_FCConductor',
    'addToFCConductorFromSelection': 'EM_FCConductor',
    'addToFCDielectric': 'EM_FCDielectric',
    'addToFCDielectricFromSelection': 'EM_FCDielectric',
    'buildFCSolverContext': 'EM_FCGeometry',
    'clearFCPanelization': 'EM_FCPanelization',
    'createFCPanelization': 'EM_FCPanelization',
    'createFHInputFile': 'EM_FHInputFile',
    'createVHInputFile': 'EM_VHInputFile',
    'exportFCPanelization': 'EM_FCExport',
    'extractFCGeometry': 'EM_FCGeometry',
    'getAbsCoordBodyPart': 'EM_Globals',
    'getFCInputFiles': 'EM_FCImport',
    'getFCPanelization': 'EM_FCPanelization',
    'getFCPanelizationSignature': 'EM_FCPanelization',
    'getFCSolver': 'EM_FCSolver',
    'getFCSpacePermittivity': 'EM_FCSolver',
    'getVHSolver': 'EM_Globals',
    'get_voxel_center': 'EM_VHConductor',
    'importFCInputFile': 'EM_FCImport',
    'intersects_box': 'EM_VHConductor',
    'invalidateFCPanelizationForObject': 'EM_FCPanelization',
    'makeFCConductor': 'EM_FCConductor',
    'makeFCConductorFromSelection': 'EM_FCConductor',
    'makeFCDielectric': 'EM_FCDielectric',
    'makeFCDielectricFromSelection': 'EM_FCDielectric',
    'makeFCSolver': 'EM_FCSolver',
    'makeFHEquiv': 'EM_FHEquiv',
    'makeFHNode': 'EM_FHNode',
    'makeFHPath': 'EM_FHPath',
    'makeFHPlane': 'EM_FHPlane',
    'makeFHPlaneHole': 'EM_FHPlaneHole',
    'makeFHPort': 'EM_FHPort',
    'makeFHSegment': 'EM_FHSegment',
    'makeFHSolver': 'EM_FHSolver',
    'makeSegShape': 'EM_Globals',
    'makeVHConductor': 'EM_VHConductor',
    'makeVHPort': 'EM_VHPort',
    'makeVHPortFromSel': 'EM_VHPort',
    'makeVHSolver': 'EM_VHSolver',
    'openFCTextFiles': 'EM_FCImport',
}
__all__ = tuple(_EXPORTS)


def __getattr__(name):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(_import_module("." + module_name, __package__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
