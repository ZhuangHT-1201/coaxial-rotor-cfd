# Coaxial rotor hover case

Steady multiple-reference-frame (MRF) hover case for the corrected coaxial
rotor geometry.

## Conditions

| Parameter | Value |
| --- | ---: |
| Rotor diameter | 2.80 m |
| Rotor spacing | 0.56 m |
| Lower rotor speed | +310 rpm |
| Upper rotor speed | -310 rpm |
| Fluid | Air at 20 °C |
| Density | 1.204 kg/m³ |
| Kinematic viscosity | 1.516e-5 m²/s |
| Turbulence model | kOmegaSST |

The supplied upper rotor includes a pitch-direction correction. With the
original assembly transforms and counter-rotation, the two stages produced
opposing axial forces.

## Run

Source your OpenFOAM environment first. The validation run used OpenFOAM v1912.

```bash
cd cases/coaxial_hover_310rpm
./run.sh
```

The script runs:

1. `blockMesh`
2. `surfaceFeatureExtract`
3. `snappyHexMesh -overwrite`
4. `checkMesh -allGeometry -allTopology`
5. `topoSet`
6. `simpleFoam`

This is a moderately large case (about 460k cells), so the mesh and solve can
take several minutes.

## Recover results

```bash
foamToVTK -time 300 -no-internal \
  -patches '(lower_rotor upper_rotor)' \
  -fields '(p U nut)' -name VTK_final

foamToVTK -time 300 -no-boundary \
  -fields '(U p nut)' -no-point-data -name VTK_final_volume
```

Then use the repository scripts:

```bash
python ../../CFD_output/compute_total_forces.py \
  --boundary-dir VTK_final/coaxial_hover_corrected_310_300/boundary \
  --volume-vtu VTK_final_volume/coaxial_hover_corrected_310_300/internal.vtu \
  --omega 32.46308 \
  --output total_force.json
```

## Mesh status

The mesh is suitable for engineering screening. `checkMesh` passes open-boundary,
negative-volume, face-pyramid and cell-determinant checks, but reports one
high-skew face and a population of concave polyhedral cells. The provided run
does not include boundary-layer prism layers.
