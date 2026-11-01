#!/usr/bin/env python3
"""Compute pressure force and torque from OpenFOAM boundary VTP output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import vtk


def read_patch(path: Path) -> tuple[np.ndarray, np.ndarray]:
    reader = vtk.vtkXMLPolyDataReader()
    reader.SetFileName(str(path))
    reader.Update()
    data = reader.GetOutput()
    points = np.asarray(
        [data.GetPoint(i) for i in range(data.GetNumberOfPoints())],
        dtype=np.float64,
    )
    pressure = np.asarray(
        [
            data.GetCellData().GetArray("p").GetComponent(i, 0)
            for i in range(data.GetNumberOfCells())
        ],
        dtype=np.float64,
    )
    return points, pressure


def patch_force(
    path: Path, rho: float, cof_r: np.ndarray
) -> dict[str, object]:
    reader = vtk.vtkXMLPolyDataReader()
    reader.SetFileName(str(path))
    reader.Update()
    data = reader.GetOutput()
    points = np.asarray(
        [data.GetPoint(i) for i in range(data.GetNumberOfPoints())],
        dtype=np.float64,
    )
    pressure_array = data.GetCellData().GetArray("p")
    force = np.zeros(3)
    torque = np.zeros(3)
    centers = []
    areas = []

    for cell_id in range(data.GetNumberOfCells()):
        cell = data.GetCell(cell_id)
        indices = [
            cell.GetPointId(j) for j in range(cell.GetNumberOfPoints())
        ]
        polygon = points[indices]
        area_vector = 0.5 * np.sum(
            np.cross(polygon, np.roll(polygon, -1, axis=0)), axis=0
        )
        area = float(np.linalg.norm(area_vector))
        if area <= 0:
            continue
        center = polygon.mean(axis=0)
        force_on_solid = (
            rho * pressure_array.GetComponent(cell_id, 0) * area_vector
        )
        force += force_on_solid
        torque += np.cross(center - cof_r, force_on_solid)
        centers.append(center)
        areas.append(area)

    pressures = np.asarray(
        [
            pressure_array.GetComponent(i, 0)
            for i in range(data.GetNumberOfCells())
        ],
        dtype=np.float64,
    )
    area_array = np.asarray(areas)
    centers_array = np.asarray(centers)
    weighted_pressure = (
        float(np.sum(area_array * pressures) / np.sum(area_array))
        if areas
        else 0.0
    )
    return {
        "patch": path.stem,
        "faces": int(len(areas)),
        "pressure_force_n": force.tolist(),
        "pressure_torque_nm": torque.tolist(),
        "pressure_area_mean_pa": rho * weighted_pressure,
        "pressure_min_pa": rho * float(np.min(pressures)),
        "pressure_max_pa": rho * float(np.max(pressures)),
        "centroid_m": (
            (
                np.sum(centers_array * area_array[:, None], axis=0)
                / np.sum(area_array)
            ).tolist()
            if areas
            else [None, None, None]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vtk-root", type=Path, required=True)
    parser.add_argument("--rho", type=float, default=1.204)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    reports = []
    for time_dir in sorted(
        (path for path in args.vtk_root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    ):
        boundary_dir = time_dir / "boundary"
        lower = boundary_dir / "lower_rotor.vtp"
        upper = boundary_dir / "upper_rotor.vtp"
        if not lower.exists() or not upper.exists():
            continue
        lower_report = patch_force(
            lower, args.rho, np.array([0.0, -0.28, 0.0])
        )
        upper_report = patch_force(
            upper, args.rho, np.array([0.0, 0.28, 0.0])
        )
        total_force = np.asarray(
            lower_report["pressure_force_n"]
        ) + np.asarray(upper_report["pressure_force_n"])
        total_torque = np.asarray(
            lower_report["pressure_torque_nm"]
        ) + np.asarray(upper_report["pressure_torque_nm"])
        reports.append(
            {
                "time": time_dir.name,
                "lower": lower_report,
                "upper": upper_report,
                "total": {
                    "pressure_force_n": total_force.tolist(),
                    "pressure_torque_nm": total_torque.tolist(),
                },
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(reports, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
