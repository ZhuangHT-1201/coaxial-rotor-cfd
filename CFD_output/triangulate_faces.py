#!/usr/bin/env python3
"""Triangulate sampled SolidWorks face descriptors into closed STL parts."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import triangle as tr
import trimesh
import networkx as nx
import pymeshfix


ROOT = Path(__file__).resolve().parent
DESCRIPTOR_DIR = ROOT / "cache" / "mesh_descriptors"
GEOMETRY_DIR = ROOT / "geometry"


def polygon_area(points: np.ndarray) -> float:
    x = points[:, 0]
    y = points[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def point_in_loops(u: float, v: float, loops: list[np.ndarray]) -> bool:
    inside = False
    for loop in loops:
        x = loop[:, 0]
        y = loop[:, 1]
        xj = np.roll(x, 1)
        yj = np.roll(y, 1)
        crossing = ((y > v) != (yj > v)) & (
            u < (xj - x) * (v - y) / np.where(yj == y, 1e-300, yj - y) + x
        )
        if np.count_nonzero(crossing) % 2:
            inside = not inside
    return inside


def polygon_centroid(points: np.ndarray) -> np.ndarray:
    area = polygon_area(points)
    if abs(area) < 1e-16:
        return points.mean(axis=0)
    x = points[:, 0]
    y = points[:, 1]
    xj = np.roll(x, 1)
    yj = np.roll(y, 1)
    cross = xj * y - x * yj
    return np.array([
        np.sum((xj + x) * cross) / (6.0 * area),
        np.sum((yj + y) * cross) / (6.0 * area),
    ])


def cap_boundary_loops(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, list[dict]]:
    """Triangulate residual open loops left by independently sampled faces."""
    reports = []
    for iteration in range(3):
        edges, counts = np.unique(
            mesh.edges_sorted, axis=0, return_counts=True
        )
        boundary = edges[counts == 1]
        if len(boundary) == 0:
            break

        graph = nx.Graph()
        graph.add_edges_from(boundary.tolist())
        new_faces = []
        for component in sorted(
            nx.connected_components(graph), key=len, reverse=True
        ):
            nodes = list(component)
            if len(nodes) < 3:
                continue
            subgraph = graph.subgraph(component)
            if any(degree != 2 for _, degree in subgraph.degree()):
                reports.append(
                    {
                        "iteration": iteration,
                        "vertices": len(nodes),
                        "filled": False,
                        "reason": "non_manifold_boundary_graph",
                    }
                )
                continue

            start = nodes[0]
            ordered = [start]
            previous = None
            current = start
            while True:
                candidates = [
                    neighbor
                    for neighbor in subgraph.neighbors(current)
                    if neighbor != previous
                ]
                following = candidates[0]
                if following == start:
                    break
                ordered.append(following)
                previous, current = current, following

            points = mesh.vertices[np.asarray(ordered)]
            center = points.mean(axis=0)
            _, _, vh = np.linalg.svd(points - center)
            basis = vh[:2]
            projected = (points - center) @ basis.T
            segments = np.column_stack(
                [np.arange(len(ordered)), np.roll(np.arange(len(ordered)), -1)]
            )
            try:
                result = tr.triangulate(
                    {"vertices": projected, "segments": segments}, "p"
                )
                triangles = np.asarray(result["triangles"], dtype=np.int64)
                out_vertices = np.asarray(result["vertices"], dtype=np.float64)
                lookup = {
                    (round(float(point[0]), 12), round(float(point[1]), 12)): index
                    for index, point in enumerate(projected)
                }
                out_to_original = np.asarray(
                    [
                        lookup[(round(float(point[0]), 12), round(float(point[1]), 12))]
                        for point in out_vertices
                    ],
                    dtype=np.int64,
                )
                mapped = np.asarray(ordered, dtype=np.int64)[
                    out_to_original[triangles]
                ]
                triangle_points = mesh.vertices[mapped]
                areas = 0.5 * np.linalg.norm(
                    np.cross(
                        triangle_points[:, 1] - triangle_points[:, 0],
                        triangle_points[:, 2] - triangle_points[:, 0],
                    ),
                    axis=1,
                )
                mapped = mapped[areas > 1e-14]
                new_faces.extend(mapped.tolist())
                reports.append(
                    {
                        "iteration": iteration,
                        "vertices": len(nodes),
                        "filled": True,
                        "triangles": len(mapped),
                    }
                )
            except Exception as error:
                reports.append(
                    {
                        "iteration": iteration,
                        "vertices": len(nodes),
                        "filled": False,
                        "reason": str(error),
                    }
                )

        if not new_faces:
            break
        mesh = trimesh.Trimesh(
            vertices=mesh.vertices,
            faces=np.vstack([mesh.faces, np.asarray(new_faces)]),
            process=False,
        )
        trimesh.repair.fix_normals(mesh, multibody=True)
    return mesh, reports


def triangulate_descriptor(path: Path, part_name: str) -> dict[str, object]:
    descriptor = json.loads(path.read_text(encoding="utf-8"))
    global_vertices: list[np.ndarray] = []
    global_faces: list[list[int]] = []
    face_reports: list[dict[str, object]] = []

    for face_data in descriptor["faces"]:
        uv = np.asarray(
            [[v[0], v[1]] for v in face_data["vertices"]], dtype=np.float64
        )
        xyz = np.asarray(
            [[v[2], v[3], v[4]] for v in face_data["vertices"]],
            dtype=np.float64,
        )
        source_normals = []
        for normal in face_data["surface_normals"]:
            if normal[0] is None:
                source_normals.append(None)
            else:
                source_normals.append(np.asarray(normal, dtype=np.float64))

        loops = [
            np.asarray(loop, dtype=np.int32) for loop in face_data["loops"]
        ]
        loop_areas = [abs(polygon_area(uv[loop])) for loop in loops]
        outer_index = int(np.argmax(loop_areas))
        holes = []
        for index, loop in enumerate(loops):
            if index == outer_index:
                continue
            marker = polygon_centroid(uv[loop])
            if not point_in_loops(marker[0], marker[1], [uv[loop]]):
                marker = uv[loop].mean(axis=0)
            holes.append(marker)

        segments = np.asarray(face_data["segments"], dtype=np.int32)
        if segments.size:
            # Triangle rejects zero-length constraints.
            delta = uv[segments[:, 1]] - uv[segments[:, 0]]
            keep = np.einsum("ij,ij->i", delta, delta) > 1e-18
            segments = segments[keep]

        tri_input: dict[str, np.ndarray] = {
            "vertices": uv,
            "segments": segments,
        }
        if holes:
            tri_input["holes"] = np.asarray(holes, dtype=np.float64)

        try:
            result = tr.triangulate(tri_input, "p")
        except Exception as error:
            face_reports.append(
                {
                    "face": face_data["face"],
                    "kind": face_data["kind"],
                    "triangles": 0,
                    "input_points": len(uv),
                    "skipped": f"triangulation_failed: {error}",
                }
            )
            continue

        out_uv = np.asarray(result["vertices"], dtype=np.float64)
        if "triangles" not in result:
            face_reports.append(
                {
                    "face": face_data["face"],
                    "kind": face_data["kind"],
                    "triangles": 0,
                    "input_points": len(uv),
                    "skipped": "triangle returned no triangles",
                }
            )
            continue
        out_triangles = np.asarray(result["triangles"], dtype=np.int32)

        # Map the triangulator's possibly reordered vertices back to the
        # descriptor's pre-evaluated 3D samples.
        uv_lookup = {
            (round(float(point[0]), 11), round(float(point[1]), 11)): index
            for index, point in enumerate(uv)
        }
        out_to_source = np.full(len(out_uv), -1, dtype=np.int32)
        for index, point in enumerate(out_uv):
            key = (round(float(point[0]), 11), round(float(point[1]), 11))
            if key in uv_lookup:
                out_to_source[index] = uv_lookup[key]

        accepted = []
        normal_sign = int(face_data["normal_sign"])
        loop_points = [uv[loop] for loop in loops]
        for triangle_indices in out_triangles:
            source_indices = out_to_source[triangle_indices]
            if np.any(source_indices < 0):
                continue
            centroid = uv[source_indices].mean(axis=0)
            if not point_in_loops(centroid[0], centroid[1], loop_points):
                continue
            points = xyz[source_indices]
            geometric_normal = np.cross(points[1] - points[0], points[2] - points[0])
            area = 0.5 * float(np.linalg.norm(geometric_normal))
            if area < 1e-12:
                continue

            available_normals = [
                source_normals[i]
                for i in source_indices
                if source_normals[i] is not None
            ]
            if available_normals:
                expected_normal = normal_sign * np.mean(available_normals, axis=0)
                if float(np.dot(geometric_normal, expected_normal)) < 0:
                    source_indices = source_indices[[0, 2, 1]]
            accepted.append(source_indices)

        if not accepted:
            face_reports.append(
                {
                    "face": face_data["face"],
                    "kind": face_data["kind"],
                    "triangles": 0,
                    "input_points": len(uv),
                    "skipped": "no_valid_triangles",
                }
            )
            continue

        base = len(global_vertices)
        global_vertices.extend(point.copy() for point in xyz)
        global_faces.extend(
            [int(base + index) for index in triangle]
            for triangle in accepted
        )
        face_reports.append(
            {
                "face": face_data["face"],
                "kind": face_data["kind"],
                "triangles": len(accepted),
                "input_points": len(uv),
            }
        )

    vertices = np.asarray(global_vertices, dtype=np.float64)
    faces = np.asarray(global_faces, dtype=np.int64)

    # Weld equivalent points from adjacent faces. The tolerance is 1 um.
    quantized = np.round(vertices / 1e-6).astype(np.int64)
    _, first, inverse = np.unique(
        quantized, axis=0, return_index=True, return_inverse=True
    )
    vertices = vertices[first]
    faces = inverse[faces]
    nondegenerate = (
        (faces[:, 0] != faces[:, 1])
        & (faces[:, 1] != faces[:, 2])
        & (faces[:, 2] != faces[:, 0])
    )
    faces = faces[nondegenerate]

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    before = {
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "boundary_edges": int(len(trimesh.grouping.group_rows(
            mesh.edges_sorted, require_count=1
        ))),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "volume_m3": float(mesh.volume),
    }

    trimesh.repair.fix_normals(mesh, multibody=True)
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
    raw_path = GEOMETRY_DIR / f"{part_name}_raw.stl"
    mesh.export(raw_path, file_type="stl")
    mesh = trimesh.load(raw_path, file_type="stl", process=True)
    pymeshfix_applied = False
    if not mesh.is_watertight:
        repair = pymeshfix.MeshFix(mesh.vertices, mesh.faces)
        repair.repair(joincomp=True, remove_smallest_components=False)
        mesh = trimesh.Trimesh(
            vertices=repair.points, faces=repair.faces, process=True
        )
        pymeshfix_applied = True
    trimesh.repair.fix_normals(mesh, multibody=True)
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()

    output = GEOMETRY_DIR / f"{part_name}.stl"
    mesh.export(output, file_type="stl")
    after = {
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "boundary_edges": int(len(trimesh.grouping.group_rows(
            mesh.edges_sorted, require_count=1
        ))),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "volume_m3": float(mesh.volume),
        "bounds": mesh.bounds.tolist(),
        "area_m2": float(mesh.area),
        "output": str(output),
    }
    report = {
        "part": part_name,
        "source_descriptor": str(path),
        "faces": face_reports,
        "before_repair": before,
        "after_repair": after,
        "boundary_caps": [],
        "pymeshfix_applied": pymeshfix_applied,
    }
    report_path = GEOMETRY_DIR / f"{part_name}_mesh_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    GEOMETRY_DIR.mkdir(parents=True, exist_ok=True)
    reports = {}
    for part_name in ("blade", "hub"):
        reports[part_name] = triangulate_descriptor(
            DESCRIPTOR_DIR / f"{part_name}.json", part_name
        )
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
