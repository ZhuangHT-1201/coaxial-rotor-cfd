# Methodology

## 1. Native geometry inspection

The modern SolidWorks files were read with `openswx`. Component transforms,
mass properties, document previews and Parasolid streams were extracted with
the diagnostic utilities under `CFD_output/tools`.

The default assembly contains:

- two hubs;
- six instances of `桨叶.SLDPRT`;
- three blades on each rotor.

## 2. Surface conversion

The selected solid parts in the Parasolid configuration partition contain:

- nine trimmed faces for one blade;
- thirty trimmed faces for the hub.

Blade faces were sampled in their native trimmed UV domains, triangulated with
Triangle, welded, and repaired with PyMeshFix. The resulting blade mesh is
watertight. Its volume differs from the stored SolidWorks mass property by
approximately 0.69%.

## 3. Coaxial assembly

The eight component transforms were taken directly from
`swxmContents/COMPINSTANCETREE`. The rotor is recentered so that:

- the shaft axis is the global `y` axis;
- the two rotor planes lie at `y = -0.28 m` and `y = +0.28 m`.

## 4. Pitch correction

When the two stages are counter-rotated in the original assembly, the pressure
forces on the stages point in opposite axial directions. The corrected case
mirrors only the upper blades about the upper rotor plane. This changes the
upper-stage pitch direction while preserving span, chord, thickness and hub
placement.

## 5. CFD model

- Solver: OpenFOAM v1912 `simpleFoam`
- Frame treatment: steady multiple reference frame
- Turbulence: `kOmegaSST`
- Fluid: air at 20 °C
- Density: `1.204 kg/m³`
- Kinematic viscosity: `1.516e-5 m²/s`
- Rotor speed: `±310 rpm`
- Domain: 11 m × 9 m × 11 m
- Cells: 461,545

The two rotor zones are cylindrical cell zones of radius 1.55 m.

## 6. Load integration

Pressure and wall-shear loads are integrated over the exported rotor surface
VTK. Pressure uses `rho * p * Sf`. Wall shear is estimated from
`rho * (nu + nut_wall) * tangential_velocity / first_cell_distance`.

The integrated estimates are engineering values, not a replacement for a
production CFD force audit.
