#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

if ! command -v blockMesh >/dev/null 2>&1; then
    echo "OpenFOAM environment is not loaded." >&2
    echo "Source your OpenFOAM v1912 environment, then rerun this script." >&2
    exit 1
fi

blockMesh
surfaceFeatureExtract
snappyHexMesh -overwrite
checkMesh -allGeometry -allTopology | tee log.checkMesh
topoSet
simpleFoam | tee log.simpleFoam
