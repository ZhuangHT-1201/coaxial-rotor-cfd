#!/usr/bin/env python3
"""Estimate pressure and wall-shear forces from exported OpenFOAM VTK data."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import vtk
from scipy.spatial import cKDTree


def read_unstructured(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    reader = vtk.vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    data = reader.GetOutput()
    centers = []
    for cell_id in range(data.GetNumberOfCells()):
        cell = data.GetCell(cell_id)
        polygon = np.asarray(
            [
                data.GetPoint(cell.GetPointId(j))
                for j in range(cell.GetNumberOfPoints())
            ],
            dtype=float,
        )
        centers.append(polygon.mean(axis=0))
    centers = np.asarray(centers)
    u_array = data.GetCellData().GetArray("U")
    nut_array = data.GetCellData().GetArray("nut")
    velocity = np.asarray(
        [
            [
                u_array.GetComponent(i, 0),
                u_array.GetComponent(i, 1),
                u_array.GetComponent(i, 2),
            ]
            for i in range(data.GetNumberOfCells())
        ]
    )
    nut = np.asarray(
        [nut_array.GetComponent(i, 0) for i in range(data.GetNumberOfCells())]
    )
    return centers, velocity, nut


def read_patch(path: Path) -> dict[str, object]:
    reader = vtk.vtkXMLPolyDataReader()
    reader.SetFileName(str(path))
    reader.Update()
    data = reader.GetOutput()
    points = np.asarray(
        [data.GetPoint(i) for i in range(data.GetNumberOfPoints())], dtype=float
    )
    polygons = []
    centers = []
    area_vectors = []
    for cell_id in range(data.GetNumberOfCells()):
        cell = data.GetCell(cell_id)
        ids = [cell.GetPointId(j) for j in range(cell.GetNumberOfPoints())]
        polygon = points[ids]
        area_vector = 0.5 * np.sum(
            np.cross(polygon, np.roll(polygon, -1, axis=0)), axis=0
        )
        polygons.append(ids)
        centers.append(polygon.mean(axis=0))
        area_vectors.append(area_vector)
    arrays = {}
    for name in ("p", "U", "nut"):
        array = data.GetCellData().GetArray(name)
        if array is not None:
            components = array.GetNumberOfComponents()
            arrays[name] = np.asarray(
                [
                    [
                        array.GetComponent(i, component)
                        for component in range(components)
                    ]
                    for i in range(data.GetNumberOfCells())
                ]
            )
    return {
        "centers": np.asarray(centers),
        "area_vectors": np.asarray(area_vectors),
        "arrays": arrays,
        "polygons": polygons,
    }


def integrate_patch(
    patch: dict[str, object],
    volume_centers: np.ndarray,
    volume_velocity: np.ndarray,
    volume_nut: np.ndarray,
    rho: float,
    nu: float,
    cof_r: np.ndarray,
    omega: np.ndarray,
) -> dict[str, object]:
    centers = np.asarray(patch["centers"])
    area_vectors = np.asarray(patch["area_vectors"])
    areas = np.linalg.norm(area_vectors, axis=1)
    normals = area_vectors / areas[:, None]
    boundary_p = np.asarray(patch["arrays"]["p"])[:, 0]
    boundary_nut = (
        np.asarray(patch["arrays"]["nut"])[:, 0]
        if "nut" in patch["arrays"]
        else np.zeros(len(centers))
    )

    tree = cKDTree(volume_centers)
    _, candidates = tree.query(centers, k=12)
    pressure_force = np.zeros(3)
    viscous_force = np.zeros(3)
    pressure_torque = np.zeros(3)
    viscous_torque = np.zeros(3)
    used_distances = []

    for index, center in enumerate(centers):
        normal = normals[index]
        pressure_force_i = rho * boundary_p[index] * area_vectors[index]
        pressure_force += pressure_force_i
        pressure_torque += np.cross(center - cof_r, pressure_force_i)

        owner = None
        owner_distance = None
        for candidate in np.atleast_1d(candidates[index]):
            delta = volume_centers[candidate] - center
            inward_distance = -float(np.dot(delta, normal))
            if inward_distance > 1e-9:
                owner = int(candidate)
                owner_distance = inward_distance
                break
        if owner is None:
            continue

        wall_velocity = np.cross(omega, center - cof_r)
        relative_velocity = volume_velocity[owner] - wall_velocity
        tangential_velocity = (
            relative_velocity - normal * np.dot(relative_velocity, normal)
        )
        speed = float(np.linalg.norm(tangential_velocity))
        if speed <= 1e-10:
            continue
        effective_nu = nu + max(float(boundary_nut[index]), 0.0)
        shear_on_solid = (
            -rho * effective_nu * tangential_velocity / owner_distance
        )
        viscous_force_i = shear_on_solid * areas[index]
        viscous_force += viscous_force_i
        viscous_torque += np.cross(center - cof_r, viscous_force_i)
        used_distances.append(owner_distance)

    total_force = pressure_force + viscous_force
    total_torque = pressure_torque + viscous_torque
    return {
        "pressure_force_n": pressure_force.tolist(),
        "viscous_force_n": viscous_force.tolist(),
        "total_force_n": total_force.tolist(),
        "pressure_torque_nm": pressure_torque.tolist(),
        "viscous_torque_nm": viscous_torque.tolist(),
        "total_torque_nm": total_torque.tolist(),
        "wall_distance_median_m": (
            float(np.median(used_distances)) if used_distances else None
        ),
        "faces": int(len(centers)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary-dir", type=Path, required=True)
    parser.add_argument("--volume-vtu", type=Path, required=True)
    parser.add_argument("--rho", type=float, default=1.204)
    parser.add_argument("--nu", type=float, default=1.516e-5)
    parser.add_argument("--omega", type=float, required=True, help="rad/s")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    volume_centers, volume_velocity, volume_nut = read_unstructured(
        args.volume_vtu
    )
    lower = read_patch(args.boundary_dir / "lower_rotor.vtp")
    upper = read_patch(args.boundary_dir / "upper_rotor.vtp")
    lower_report = integrate_patch(
        lower,
        volume_centers,
        volume_velocity,
        volume_nut,
        args.rho,
        args.nu,
        np.array([0.0, -0.28, 0.0]),
        np.array([0.0, args.omega, 0.0]),
    )
    upper_report = integrate_patch(
        upper,
        volume_centers,
        volume_velocity,
        volume_nut,
        args.rho,
        args.nu,
        np.array([0.0, 0.28, 0.0]),
        np.array([0.0, -args.omega, 0.0]),
    )
    lower_report["patch"] = "lower_rotor"
    upper_report["patch"] = "upper_rotor"
    total_force = np.asarray(lower_report["total_force_n"]) + np.asarray(
        upper_report["total_force_n"]
    )
    total_torque = np.asarray(lower_report["total_torque_nm"]) + np.asarray(
        upper_report["total_torque_nm"]
    )
    result = {
        "source_volume": str(args.volume_vtu),
        "source_boundary": str(args.boundary_dir),
        "pressure_only": False,
        "lower": lower_report,
        "upper": upper_report,
        "total": {
            "force_n": total_force.tolist(),
            "torque_nm": total_torque.tolist(),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
