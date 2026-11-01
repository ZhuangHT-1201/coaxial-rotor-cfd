// SPDX-License-Identifier: MIT
// Diagnostic binding tool for extracted SolidWorks/Parasolid payloads.

#include <cstdint>
#include <filesystem>
#include <iostream>
#include <string>
#include <variant>

#include "openparasolid/brep.h"
#include "openparasolid/model.h"
#include "openparasolid/schema.h"
#include "openswx/container.h"

namespace {
const char* SurfaceKind(const openparasolid::GeometryPayload& payload) {
  using namespace openparasolid;
  if (std::holds_alternative<PlaneGeometry>(payload)) return "plane";
  if (std::holds_alternative<CylinderGeometry>(payload)) return "cylinder";
  if (std::holds_alternative<ConeGeometry>(payload)) return "cone";
  if (std::holds_alternative<SphereGeometry>(payload)) return "sphere";
  if (std::holds_alternative<TorusGeometry>(payload)) return "torus";
  if (std::holds_alternative<NurbsSurfaceGeometry>(payload)) return "nurbs";
  if (std::holds_alternative<SpunSurfaceGeometry>(payload)) return "spun";
  if (std::holds_alternative<SweptSurfaceGeometry>(payload)) return "swept";
  if (std::holds_alternative<OffsetSurfaceGeometry>(payload)) return "offset";
  return "other";
}
}  // namespace

int main(int argc, char** argv) {
  if (argc != 6) {
    std::cerr << "usage: xb_bind_inspect INPUT.SLDPRT PAYLOAD_INDEX BODY_ID "
                 "TOLERANCE GEOMETRY_ONLY\n";
    return 2;
  }

  using namespace openparasolid;
  const std::filesystem::path input = argv[1];
  const std::size_t payload_index =
      static_cast<std::size_t>(std::stoull(argv[2]));
  const NodeId body{static_cast<uint32_t>(std::stoull(argv[3]))};
  const double tolerance = std::stod(argv[4]);
  const bool geometry_only = std::string(argv[5]) == "geometry";

  const auto container = openswx::InspectContainer(input);
  if (!container.ok()) {
    std::cerr << "container: " << container.error() << '\n';
    return 1;
  }
  const auto extraction =
      openswx::ExtractParasolidStreams(container.value());
  if (payload_index >= extraction.payloads.size()) {
    std::cerr << "payload index out of range\n";
    return 1;
  }
  const auto& payload = extraction.payloads[payload_index];
  const auto parsed = SchemaParser::Parse(payload.payload.data);
  if (!parsed.ok()) {
    std::cerr << "parse: " << parsed.error().message << '\n';
    return 1;
  }
  const auto built = ModelBuilder::Build(parsed.value());
  if (!built.ok()) {
    std::cerr << "model: " << built.error().message << '\n';
    return 1;
  }
  const Model& model = built.value();
  std::cout << "nodes=" << model.nodes().size()
            << " geometry=" << model.geometry().size()
            << " issues=" << model.statistics().total_issues << '\n';

  if (!geometry_only) {
    const auto topology = ValidateBodyTopology(model, body);
    if (!topology.ok()) {
      std::cerr << "topology: " << topology.error().message << '\n';
      return 1;
    }
    std::cout << "topology_edges=" << topology.value().edges.size()
              << " topology_vertices=" << topology.value().vertices.size()
              << '\n';
  }

  BodyGeometryBindingOptions options;
  IntersectionEvaluationOptions intersection;
  intersection.chart_tolerance = 1e-8;
  intersection.solve_tolerance = 1e-8;
  intersection.chart_parameter_tolerance = 1e-8;
  intersection.minimum_normal_sine = 1e-8;
  intersection.minimum_chord_projection = 1e-8;
  options.intersection = intersection;

  const auto bound = BindBodyGeometry(model, body, tolerance, options);
  if (!bound.ok()) {
    std::cerr << "bind: " << bound.error().message << '\n';
    return 1;
  }

  std::cout << "faces=" << bound.value().faces.size()
            << " wires=" << bound.value().wires.size()
            << " vertices=" << bound.value().vertices.size() << '\n';
  for (const auto& face : bound.value().faces) {
    std::size_t fins = 0;
    for (const auto& loop : face.loops) fins += loop.fins.size();
    const auto* surface_node = model.FindNode(face.surface);
    const char* kind = "missing";
    if (surface_node && surface_node->geometry) {
      kind = SurfaceKind(model.geometry()[surface_node->geometry.value()].payload);
    }
    std::cout << "face=" << face.face.value
              << " surface=" << face.surface.value
              << " kind=" << kind
              << " loops=" << face.loops.size() << " fins=" << fins << '\n';
    if (surface_node && surface_node->geometry) {
      const auto& payload =
          model.geometry()[surface_node->geometry.value()].payload;
      if (const auto* cylinder =
              std::get_if<openparasolid::CylinderGeometry>(&payload)) {
        std::cout << "  cylinder_radius=" << cylinder->radius
                  << " origin=" << cylinder->origin.x << ","
                  << cylinder->origin.y << "," << cylinder->origin.z
                  << " axis=" << cylinder->axis.x << ","
                  << cylinder->axis.y << "," << cylinder->axis.z << '\n';
      } else if (const auto* torus =
                     std::get_if<openparasolid::TorusGeometry>(&payload)) {
        std::cout << "  torus_R=" << torus->major_radius
                  << " r=" << torus->minor_radius
                  << " center=" << torus->center.x << ","
                  << torus->center.y << "," << torus->center.z
                  << " axis=" << torus->axis.x << ","
                  << torus->axis.y << "," << torus->axis.z << '\n';
      } else if (const auto* sphere =
                     std::get_if<openparasolid::SphereGeometry>(&payload)) {
        std::cout << "  sphere_radius=" << sphere->radius
                  << " center=" << sphere->center.x << ","
                  << sphere->center.y << "," << sphere->center.z << '\n';
      }
    }
  }
  return 0;
}
