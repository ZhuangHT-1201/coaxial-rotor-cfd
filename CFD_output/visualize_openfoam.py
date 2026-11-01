#!/usr/bin/env python3
"""Render meridional flow slices from OpenFOAM VTK output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
import vtk
from scipy.interpolate import griddata


def read_cut(path: Path, normal: tuple[float, float, float]) -> dict[str, np.ndarray]:
    reader = vtk.vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    plane = vtk.vtkPlane()
    plane.SetOrigin(0.0, 0.0, 0.0)
    plane.SetNormal(*normal)
    cutter = vtk.vtkCutter()
    cutter.SetInputData(reader.GetOutput())
    cutter.SetCutFunction(plane)
    cutter.Update()
    output = cutter.GetOutput()
    count = output.GetNumberOfCells()
    centers = []
    for cell_id in range(count):
        cell = output.GetCell(cell_id)
        cell_points = np.asarray(
            [
                output.GetPoint(cell.GetPointId(j))
                for j in range(cell.GetNumberOfPoints())
            ],
            dtype=float,
        )
        centers.append(cell_points.mean(axis=0))
    centers = np.asarray(centers)
    pressure_kinematic = np.asarray(
        [
            output.GetCellData().GetArray("p").GetComponent(i, 0)
            for i in range(count)
        ]
    )
    velocity = np.asarray(
        [
            [
                output.GetCellData().GetArray("U").GetComponent(i, 0),
                output.GetCellData().GetArray("U").GetComponent(i, 1),
                output.GetCellData().GetArray("U").GetComponent(i, 2),
            ]
            for i in range(count)
        ]
    )
    return {
        "centers": centers,
        "p": pressure_kinematic,
        "U": velocity,
    }


def interpolate(
    points: np.ndarray,
    values: np.ndarray,
    grid_x: np.ndarray,
    grid_y: np.ndarray,
) -> np.ndarray:
    gx, gy = np.meshgrid(grid_x, grid_y)
    result = griddata(points[:, :2], values, (gx, gy), method="linear")
    nearest = griddata(points[:, :2], values, (gx, gy), method="nearest")
    result[np.isnan(result)] = nearest[np.isnan(result)]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--time", type=int, required=True)
    parser.add_argument("--vtu", type=Path)
    parser.add_argument("--stl", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rpm", type=float, required=True)
    parser.add_argument("--force-json", type=Path)
    args = parser.parse_args()

    rho = 1.204
    vtu = args.vtu
    if vtu is None:
        candidates = sorted(
            (args.case / "VTK_volume").glob(f"*_{args.time}/internal.vtu")
        )
        if not candidates:
            raise FileNotFoundError("could not find internal.vtu")
        vtu = candidates[0]
    data = read_cut(vtu, (0.0, 0.0, 1.0))
    points = data["centers"]
    velocity = data["U"]
    pressure = rho * data["p"]
    speed = np.linalg.norm(velocity, axis=1)

    x = np.linspace(-5.5, 5.5, 441)
    y = np.linspace(-4.5, 4.5, 361)
    speed_grid = interpolate(points, speed, x, y)
    ux_grid = interpolate(points, velocity[:, 0], x, y)
    uy_grid = interpolate(points, velocity[:, 1], x, y)
    pressure_grid = interpolate(points, pressure, x, y)
    xx, yy = np.meshgrid(x, y)

    mesh = trimesh.load(args.stl, process=True)
    section = mesh.section(
        plane_origin=(0.0, 0.0, 0.0), plane_normal=(0.0, 0.0, 1.0)
    )

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.6), constrained_layout=True)
    speed_limit = float(np.nanpercentile(speed_grid, 99.0))
    contour_speed = axes[0].contourf(
        xx,
        yy,
        speed_grid,
        levels=np.linspace(0.0, speed_limit, 26),
        cmap="viridis",
        extend="max",
    )
    axes[0].streamplot(
        x,
        y,
        ux_grid,
        uy_grid,
        density=(1.2, 1.4),
        color="white",
        linewidth=0.5,
        arrowsize=0.55,
    )
    fig.colorbar(contour_speed, ax=axes[0], label="Speed (m/s)")
    axes[0].set_title("Velocity magnitude")

    pressure_limit = float(np.nanpercentile(np.abs(pressure_grid), 99.0))
    contour_pressure = axes[1].contourf(
        xx,
        yy,
        pressure_grid,
        levels=np.linspace(-pressure_limit, pressure_limit, 31),
        cmap="RdBu_r",
        extend="both",
    )
    fig.colorbar(contour_pressure, ax=axes[1], label="Gauge pressure (Pa)")
    axes[1].set_title("Static pressure")

    if section is not None:
        for entities in section.discrete:
            profile = np.asarray(entities)
            if profile.ndim != 2 or profile.shape[1] != 3:
                profile = section.vertices[profile.astype(np.int64)]
            for axis in axes:
                axis.plot(
                    profile[:, 0],
                    profile[:, 1],
                    color="black",
                    linewidth=1.2,
                    alpha=0.9,
                )

    for axis in axes:
        axis.axhline(-0.28, color="#f4a261", linewidth=0.8, linestyle="--")
        axis.axhline(0.28, color="#f4a261", linewidth=0.8, linestyle="--")
        axis.set_xlim(-4.0, 4.0)
        axis.set_ylim(-1.6, 1.6)
        axis.set_xlabel("x (m)")
        axis.set_ylabel("y (rotor axis, m)")

    fig.suptitle(
        f"Coaxial rotor hover baseline, {args.rpm:g} rpm, meridional slice z = 0"
    )
    fig.savefig(output_dir / "velocity_pressure_slice.png", dpi=190)
    plt.close(fig)

    axis_x = 0.015
    line_points = points[np.abs(points[:, 0] - axis_x) < 0.10]
    order = np.argsort(line_points[:, 1])
    line_points = line_points[order]
    line_uy = griddata(
        points[:, :2],
        velocity[:, 1],
        (np.full_like(line_points[:, 1], axis_x), line_points[:, 1]),
        method="linear",
    )
    line_p = griddata(
        points[:, :2],
        pressure,
        (np.full_like(line_points[:, 1], axis_x), line_points[:, 1]),
        method="linear",
    )

    fig, ax1 = plt.subplots(figsize=(8.2, 4.5), constrained_layout=True)
    ax1.plot(line_points[:, 1], line_uy, color="#1d3557", linewidth=2)
    ax1.axvline(-0.28, color="#e76f51", linestyle="--", label="Lower disk")
    ax1.axvline(0.28, color="#2a9d8f", linestyle="--", label="Upper disk")
    ax1.set_xlabel("y (rotor axis, m)")
    ax1.set_ylabel("Axial velocity (m/s)")
    ax1.grid(alpha=0.2)
    ax2 = ax1.twinx()
    ax2.plot(line_points[:, 1], line_p, color="#e9c46a", linewidth=1.5)
    ax2.set_ylabel("Gauge pressure (Pa)")
    ax1.legend(loc="upper right")
    ax1.set_title("Near-axis velocity and pressure")
    fig.savefig(output_dir / "centerline.png", dpi=190)
    plt.close(fig)

    if args.force_json:
        forces = json.loads(args.force_json.read_text(encoding="utf-8"))
        lower_thrust = forces["lower"]["total_force_n"][1]
        upper_thrust = forces["upper"]["total_force_n"][1]
        total_thrust = forces["total"]["force_n"][1]
        lower_torque = forces["lower"]["total_torque_nm"][1]
        upper_torque = forces["upper"]["total_torque_nm"][1]
        total_torque = forces["total"]["torque_nm"][1]
        target_weight = 25.489779 * 9.80665

        fig, axes = plt.subplots(
            1, 2, figsize=(10.5, 4.2), constrained_layout=True
        )
        axes[0].bar(
            ["Lower", "Upper", "Total", "Weight"],
            [lower_thrust, upper_thrust, total_thrust, target_weight],
            color=["#457b9d", "#2a9d8f", "#1d3557", "#e76f51"],
        )
        axes[0].set_ylabel("Axial force (N)")
        axes[0].set_title("Hover lift")
        axes[0].grid(axis="y", alpha=0.2)

        axes[1].bar(
            ["Lower", "Upper", "Net"],
            [lower_torque, upper_torque, total_torque],
            color=["#457b9d", "#2a9d8f", "#1d3557"],
        )
        axes[1].axhline(0.0, color="black", linewidth=0.8)
        axes[1].set_ylabel("Torque about rotor axis (N m)")
        axes[1].set_title("Torque cancellation")
        axes[1].grid(axis="y", alpha=0.2)
        fig.suptitle(f"Corrected coaxial rotor performance at {args.rpm:g} rpm")
        fig.savefig(output_dir / "performance_summary.png", dpi=190)
        plt.close(fig)

    summary = {
        "time": args.time,
        "slice": "z=0",
        "speed_max_m_s": float(np.nanmax(speed_grid)),
        "speed_p99_m_s": float(np.nanpercentile(speed_grid, 99.0)),
        "pressure_min_pa": float(np.nanmin(pressure_grid)),
        "pressure_max_pa": float(np.nanmax(pressure_grid)),
    }
    (output_dir / "slice_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
