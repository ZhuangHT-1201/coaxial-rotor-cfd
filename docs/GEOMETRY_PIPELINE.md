# Geometry pipeline

The prepared STL files are included so that the CFD case can be reproduced
without repeating the native CAD conversion. This page documents the
conversion path used to produce them.

## Inputs

- `共轴双旋翼.SLDASM`
- `桨叶.SLDPRT`
- `桨毂.SLDPRT`

The source models were created with a modern SolidWorks document version
(model version `12000`).

## SolidWorks inspection

The MIT-licensed `openswx` project was used locally to:

1. identify modern SolidWorks container streams;
2. extract configuration metadata and component transforms;
3. decode the binary Parasolid partition streams;
4. inspect body topology and supporting surfaces;
5. sample trimmed blade faces.

The extracted blade partition contains nine faces: seven planar faces and two
NURBS surfaces. The hub partition contains thirty faces, including planes,
cylinders and tori.

The native partition includes vendor-specific trim records that are not
accepted unmodified by every open-source OpenCASCADE converter. The blade
surface path was therefore processed with the included diagnostic C++ tools
and a locally built `openswx` parser. The public source archive includes the
original CAD, extracted component placement and final STL surfaces so users
are not required to repeat that parser-specific step.

## Triangulation and repair

`CFD_output/triangulate_faces.py` performs:

1. trimmed UV loop sampling;
2. constrained triangulation with Triangle;
3. rejection of triangles outside the trimmed region;
4. welding of adjacent face boundaries;
5. repair with PyMeshFix;
6. watertightness, volume and area reporting.

The resulting blade volume is within about 0.69% of the stored SolidWorks
mass-property volume.

## Hub

Several native hub trim surfaces could not be reconstructed reliably by the
available open-source conversion path. `CFD_output/assemble_rotor.py` creates
a closed three-arm fairing with the extracted outer dimensions and unions it
with the actual blade surfaces.

## Upper-stage correction

The original component transforms and blade orientation are retained for the
as-modeled comparison. For the corrected case, only the upper blade geometry
is reflected about the upper rotor plane. The lower blades, hub dimensions and
0.56 m stage separation remain unchanged.
