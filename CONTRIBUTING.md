# Contributing

Contributions are welcome, especially reproducible bug reports, validation
cases, mesh-quality improvements, and corrections to the geometry pipeline.

## Workflow

1. Open an issue describing the problem or proposed change.
2. Fork the repository and create a focused branch.
3. Keep changes limited to one topic.
4. Include the commands used to reproduce results.
5. For numerical changes, report mesh statistics and force/moment history.
6. Open a pull request with a concise summary and validation evidence.

## Numerical contributions

Please include:

- OpenFOAM version and compiler/platform.
- Boundary conditions, fluid properties, RPM and geometry revision.
- Mesh count and `checkMesh` result.
- Residual and force convergence history.
- A clear distinction between pressure-only loads, viscous loads, and total
  loads.

Do not present an engineering baseline as a certified design result.

## Licensing

By submitting a contribution, you agree that it may be distributed under the
repository's MIT License.
