# As-modeled counter-rotating comparison

This case keeps the original assembly transforms and counter-rotates the two
stages at `+800/-800 rpm`.

Result at iteration 800:

- lower-stage axial pressure force: `+900.55 N`;
- upper-stage axial pressure force: `-830.81 N`;
- combined axial pressure force: `+69.73 N`;
- combined axial pressure torque: `-14.64 N·m`.

The near-cancellation is caused by the upper-stage pitch orientation. The
corrected lifting configuration is documented under
`cases/coaxial_hover_310rpm`.

Run with:

```bash
source /path/to/OpenFOAM-v1912/etc/bashrc
cd cases/as_modeled_800rpm
./run.sh
```
