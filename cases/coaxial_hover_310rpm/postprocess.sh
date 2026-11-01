#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

time="${1:-300}"

foamToVTK -time "$time" -no-internal \
    -patches '(lower_rotor upper_rotor)' \
    -fields '(p U nut)' -name VTK_final

foamToVTK -time "$time" -no-boundary \
    -fields '(U p nut)' -no-point-data -name VTK_final_volume

python ../../CFD_output/compute_total_forces.py \
    --boundary-dir "VTK_final/coaxial_hover_corrected_310_${time}/boundary" \
    --volume-vtu "VTK_final_volume/coaxial_hover_corrected_310_${time}/internal.vtu" \
    --omega 32.46308 \
    --output "total_force_${time}.json"
