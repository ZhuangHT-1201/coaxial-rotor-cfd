# Validation and limitations

## Numerical stability

At iteration 300:

| Quantity | Value |
| --- | ---: |
| `Ux` residual | `9.34e-5` |
| `Uy` residual | `4.36e-5` |
| `Uz` residual | `1.06e-4` |
| `p` residual | `9.50e-6` |
| local continuity error | `1.97e-6` |
| global continuity error | `7.56e-7` |

The total axial force was `257.12 N` at iteration 200 and `257.07 N` at
iteration 300.

## Mesh status

`checkMesh` passes:

- boundary topology;
- cell connectivity;
- boundary openness;
- negative-volume checks;
- face-pyramid checks;
- cell-determinant checks.

It also reports:

- one highly skew face with maximum skewness `4.20`;
- 207 faces with concave angles;
- 29 warped faces;
- 5,260 concave polyhedral cells.

These warnings are material. A production study should improve the mesh before
using the result for certification or detailed blade-load distributions.

## Known limitations

1. The hub is a closed three-arm fairing reconstructed from the extracted
   outer dimensions rather than the full native hub BRep.
2. The upper blade pitch is intentionally corrected for a lifting coaxial
   configuration.
3. The analysis is steady MRF; blade-passage and transient wake effects are not
   resolved.
4. No boundary-layer prism layers are present.
5. Wall shear is approximated from the first-cell gradient and wall-function
   viscosity.
6. The 310 rpm operating point is an engineering baseline selected to match
   the 25.49 kg assembly weight, not a measured flight condition.

## Reproducibility artifacts

- Case dictionaries: `cases/coaxial_hover_310rpm`
- Force data: `CFD_output/results/coaxial_hover_310rpm/total_force.json`
- Metrics: `CFD_output/results/coaxial_hover_310rpm/summary.json`
- Solver log: `CFD_output/results/coaxial_hover_310rpm/solver.log`
- Full generated case: release asset
