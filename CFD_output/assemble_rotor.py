#!/usr/bin/env python3
"""Assemble the coaxial rotor from the converted blade and simplified hub."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import trimesh


ROOT = Path(__file__).resolve().parent
GEOMETRY = ROOT / "geometry"
COMPONENTS = ROOT / "data" / "assembly_components.json"

ROTOR_AXIS_X = -0.1050414183508811
ROTOR_MID_Y = 0.5 * (0.06792009041591321 - 0.4920799095840871)


def cylinder_between(
    start: np.ndarray, end: np.ndarray, radius: float, sections: int = 64
) -> trimesh.Trimesh:
    direction = end - start
    height = float(np.linalg.norm(direction))
    if height <= 0:
        raise ValueError("zero-length cylinder")
    axis = direction / height
    z_axis = np.array([0.0, 0.0, 1.0])
    cross = np.cross(z_axis, axis)
    dot = float(np.clip(np.dot(z_axis, axis), -1.0, 1.0))
    if np.linalg.norm(cross) < 1e-12:
        rotation = np.eye(4)
        if dot < 0:
            rotation[:3, :3] = np.diag([1.0, -1.0, -1.0])
    else:
        skew = np.array([
            [0.0, -cross[2], cross[1]],
            [cross[2], 0.0, -cross[0]],
            [-cross[1], cross[0], 0.0],
        ])
        rotation = np.eye(4)
        rotation[:3, :3] = (
            np.eye(3)
            + skew
            + skew @ skew * ((1.0 - dot) / np.dot(cross, cross))
        )
    rotation[:3, 3] = 0.5 * (start + end)
    cylinder = trimesh.creation.cylinder(
        radius=radius, height=height, sections=sections
    )
    cylinder.apply_transform(rotation)
    return cylinder


def build_simplified_hub() -> trimesh.Trimesh:
    # A closed aerodynamic fairing matched to the extracted outer bounds:
    # 0.28 m radial arms, 0.09 m central fairing, and a 0.025 m shaft.
    fairing = trimesh.creation.icosphere(subdivisions=4, radius=1.0)
    fairing.apply_scale([0.09, 0.05, 0.09])

    parts = [fairing]
    for angle in (0.0, 2.0 * math.pi / 3.0, 4.0 * math.pi / 3.0):
        end = np.array([
            0.28 * math.cos(angle),
            0.0,
            0.28 * math.sin(angle),
        ])
        parts.append(cylinder_between(np.zeros(3), end, 0.025))
    parts.append(
        cylinder_between(
            np.array([0.0, -0.255, 0.0]),
            np.array([0.0, 0.05, 0.0]),
            0.025,
        )
    )
    hub = trimesh.boolean.union(parts, engine="manifold")
    hub.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(hub, multibody=True)
    if not hub.is_watertight:
        raise RuntimeError("simplified hub is not watertight")
    return hub


def sw_transform(values: list[float]) -> np.ndarray:
    # SolidWorks serializes row-vector transforms; trimesh uses column vectors.
    return np.asarray(values, dtype=np.float64).reshape((4, 4)).T


def transformed(mesh: trimesh.Trimesh, transform: np.ndarray) -> trimesh.Trimesh:
    result = mesh.copy()
    result.apply_transform(transform)
    return result


def rotor_from_parts(
    hub: trimesh.Trimesh,
    blade: trimesh.Trimesh,
    parts: list[dict],
    global_transform: np.ndarray,
    mirror_blades: bool = False,
) -> trimesh.Trimesh:
    hub_parts = []
    blade_parts = []
    for part in parts:
        matrix = sw_transform([float(v) for v in part["swTransform"].split()])
        source = hub if part["swName"] == "桨毂" else blade
        item = transformed(source, matrix)
        (hub_parts if part["swName"] == "桨毂" else blade_parts).append(item)

    if mirror_blades:
        rotor_plane_y = float(
            np.mean(
                [
                    sw_transform(
                        [float(v) for v in part["swTransform"].split()]
                    )[1, 3]
                    for part in parts
                    if part["swName"] == "桨叶"
                ]
            )
        )
        for item in blade_parts:
            item.vertices[:, 1] = 2.0 * rotor_plane_y - item.vertices[:, 1]
            item.faces = item.faces[:, [0, 2, 1]]
            trimesh.repair.fix_normals(item, multibody=True)

    hub_union = trimesh.boolean.union(hub_parts, engine="manifold")
    blade_union = trimesh.util.concatenate(blade_parts)
    assembled = [hub_union, blade_union]
    rotor = trimesh.boolean.union(assembled, engine="manifold")
    rotor.apply_transform(global_transform)
    rotor.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(rotor, multibody=True)
    if not rotor.is_watertight:
        raise RuntimeError("rotor assembly is not watertight after union")
    return rotor


def main() -> None:
    blade = trimesh.load(GEOMETRY / "blade.stl", process=True)
    if not blade.is_watertight:
        raise RuntimeError("blade mesh must be watertight")
    hub = build_simplified_hub()
    hub.export(GEOMETRY / "hub_simplified.stl", file_type="stl")

    parts = json.loads(COMPONENTS.read_text(encoding="utf-8"))
    if len(parts) != 8:
        raise RuntimeError(f"expected 8 assembly components, got {len(parts)}")

    recenter = np.eye(4)
    recenter[:3, 3] = [
        -ROTOR_AXIS_X,
        -ROTOR_MID_Y,
        0.0,
    ]
    upper = rotor_from_parts(hub, blade, parts[:4], recenter)
    upper_corrected = rotor_from_parts(
        hub, blade, parts[:4], recenter, mirror_blades=True
    )
    lower = rotor_from_parts(hub, blade, parts[4:], recenter)

    lower.export(GEOMETRY / "lower_rotor.stl", file_type="stl")
    upper.export(GEOMETRY / "upper_rotor.stl", file_type="stl")
    upper_corrected.export(
        GEOMETRY / "upper_rotor_corrected.stl", file_type="stl"
    )
    combined = trimesh.util.concatenate([lower, upper])
    combined.export(GEOMETRY / "coaxial_rotor.stl", file_type="stl")
    corrected_combined = trimesh.util.concatenate([lower, upper_corrected])
    corrected_combined.export(
        GEOMETRY / "coaxial_rotor_corrected.stl", file_type="stl"
    )

    summary = {
        "blade": {
            "volume_m3": float(blade.volume),
            "area_m2": float(blade.area),
            "watertight": bool(blade.is_watertight),
            "bounds_m": blade.bounds.tolist(),
        },
        "hub_simplified": {
            "volume_m3": float(hub.volume),
            "area_m2": float(hub.area),
            "watertight": bool(hub.is_watertight),
            "bounds_m": hub.bounds.tolist(),
            "note": "Geometric simplification; blades remain the converted CAD surface.",
        },
        "lower_rotor": {
            "volume_m3": float(lower.volume),
            "area_m2": float(lower.area),
            "watertight": bool(lower.is_watertight),
            "bounds_m": lower.bounds.tolist(),
        },
        "upper_rotor": {
            "volume_m3": float(upper.volume),
            "area_m2": float(upper.area),
            "watertight": bool(upper.is_watertight),
            "bounds_m": upper.bounds.tolist(),
        },
        "upper_rotor_corrected": {
            "volume_m3": float(upper_corrected.volume),
            "area_m2": float(upper_corrected.area),
            "watertight": bool(upper_corrected.is_watertight),
            "bounds_m": upper_corrected.bounds.tolist(),
            "note": "Upper blades mirrored about the rotor plane to restore a lifting coaxial installation.",
        },
        "recenter_translation_m": recenter[:3, 3].tolist(),
    }
    (GEOMETRY / "rotor_geometry_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
