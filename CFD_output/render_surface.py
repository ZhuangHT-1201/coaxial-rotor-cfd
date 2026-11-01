#!/usr/bin/env python3
"""Render an English-labelled 3D rotor surface pressure overview."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import vtk
from matplotlib import cm
from matplotlib.colors import Normalize
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def load_patch(path: Path) -> tuple[list[np.ndarray], np.ndarray]:
    reader = vtk.vtkXMLPolyDataReader()
    reader.SetFileName(str(path))
    reader.Update()
    data = reader.GetOutput()
    points = np.asarray(
        [data.GetPoint(i) for i in range(data.GetNumberOfPoints())], dtype=float
    )
    values = data.GetCellData().GetArray("p")
    polygons = []
    pressure = []
    for cell_id in range(data.GetNumberOfCells()):
        cell = data.GetCell(cell_id)
        if cell.GetNumberOfPoints() != 3:
            ids = [cell.GetPointId(j) for j in range(cell.GetNumberOfPoints())]
            for j in range(1, len(ids) - 1):
                polygons.append(points[[ids[0], ids[j], ids[j + 1]]])
                pressure.append(values.GetComponent(cell_id, 0))
        else:
            ids = [cell.GetPointId(j) for j in range(3)]
            polygons.append(points[ids])
            pressure.append(values.GetComponent(cell_id, 0))
    return polygons, np.asarray(pressure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rho", type=float, default=1.204)
    parser.add_argument("--rpm", type=float, default=310)
    args = parser.parse_args()

    lower_polygons, lower_p = load_patch(
        args.boundary_dir / "lower_rotor.vtp"
    )
    upper_polygons, upper_p = load_patch(
        args.boundary_dir / "upper_rotor.vtp"
    )
    polygons = lower_polygons + upper_polygons
    pressure = args.rho * np.concatenate([lower_p, upper_p])
    limit = float(np.percentile(np.abs(pressure), 99.0))
    norm = Normalize(vmin=-limit, vmax=limit)
    colors = cm.RdBu_r(norm(pressure))

    fig = plt.figure(figsize=(11, 7.2), facecolor="#081018")
    ax = fig.add_subplot(111, projection="3d", facecolor="#081018")
    ax.set_position([-0.03, -0.10, 0.90, 0.94])
    collection = Poly3DCollection(
        polygons,
        facecolors=colors,
        edgecolors="none",
        linewidths=0.0,
        antialiased=False,
        alpha=1.0,
    )
    ax.add_collection3d(collection)
    ax.set_xlim(-1.42, 1.42)
    ax.set_ylim(-0.48, 0.48)
    ax.set_zlim(-1.42, 1.42)
    ax.set_box_aspect((1.0, 0.38, 1.0))
    ax.view_init(elev=25, azim=-53)
    ax.dist = 6.15
    ax.set_axis_off()

    fig.text(
        0.04,
        0.94,
        "COAXIAL ROTOR CFD",
        color="white",
        fontsize=18,
        fontweight="bold",
    )
    fig.text(
        0.04,
        0.895,
        f"Corrected counter-rotating pitch  |  {args.rpm:g} rpm hover",
        color="#b8c7d9",
        fontsize=10,
    )
    ax.quiver(
        -1.45,
        -0.5,
        -1.45,
        0.0,
        0.9,
        0.0,
        color="#6ee7b7",
        arrow_length_ratio=0.18,
        linewidth=2,
    )
    ax.text(
        -1.42,
        -0.02,
        -1.38,
        "thrust axis",
        color="#6ee7b7",
        fontsize=8,
    )

    scalar_mappable = cm.ScalarMappable(norm=norm, cmap="RdBu_r")
    scalar_mappable.set_array(pressure)
    colorbar = fig.colorbar(
        scalar_mappable, ax=ax, shrink=0.63, pad=0.02, fraction=0.03
    )
    colorbar.set_label("Static gauge pressure (Pa)", color="white")
    colorbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(colorbar.ax.get_yticklabels(), color="white")
    colorbar.outline.set_edgecolor("white")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=220, facecolor=fig.get_facecolor())
    plt.close(fig)


if __name__ == "__main__":
    main()
