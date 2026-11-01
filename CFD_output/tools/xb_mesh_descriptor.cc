// SPDX-License-Identifier: MIT
// Exports sampled trimmed faces from an extracted Parasolid body.

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <optional>
#include <string>
#include <tuple>
#include <variant>
#include <vector>

#include <nlohmann/json.hpp>

#include "openparasolid/brep.h"
#include "openparasolid/evaluate.h"
#include "openparasolid/model.h"
#include "openparasolid/schema.h"
#include "openswx/container.h"

namespace {
using json = nlohmann::json;
using openparasolid::Vector3;

constexpr double kPi = 3.14159265358979323846;
constexpr double kTwoPi = 2.0 * kPi;

json VecJson(const Vector3& v) { return json::array({v.x, v.y, v.z}); }

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

bool PeriodicU(const char* kind) {
  return std::string(kind) == "cylinder" || std::string(kind) == "cone" ||
         std::string(kind) == "sphere" || std::string(kind) == "torus" ||
         std::string(kind) == "spun";
}

bool PeriodicV(const char* kind) {
  return std::string(kind) == "torus" || std::string(kind) == "sphere";
}

double NearestPeriodic(double value, double reference) {
  return value + std::round((reference - value) / kTwoPi) * kTwoPi;
}

bool PointInLoop(double u, double v,
                 const std::vector<openparasolid::SurfaceParameters>& loop) {
  if (loop.size() < 3) return false;
  bool inside = false;
  for (std::size_t i = 0, j = loop.size() - 1; i < loop.size(); j = i++) {
    const double ui = loop[i].u;
    const double vi = loop[i].v;
    const double uj = loop[j].u;
    const double vj = loop[j].v;
    const bool crosses =
        ((vi > v) != (vj > v)) &&
        (u < (uj - ui) * (v - vi) / (vj - vi) + ui);
    if (crosses) inside = !inside;
  }
  return inside;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 8) {
    std::cerr << "usage: xb_mesh_descriptor INPUT.SLDPRT PAYLOAD_INDEX BODY_ID "
                 "TOLERANCE NU NV OUTPUT.json\n";
    return 2;
  }

  using namespace openparasolid;
  const std::filesystem::path input = argv[1];
  const std::size_t payload_index =
      static_cast<std::size_t>(std::stoull(argv[2]));
  const NodeId body{static_cast<uint32_t>(std::stoull(argv[3]))};
  const double tolerance = std::stod(argv[4]);
  const int nu = std::stoi(argv[5]);
  const int nv = std::stoi(argv[6]);
  const std::filesystem::path output = argv[7];

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
  const auto parsed =
      SchemaParser::Parse(extraction.payloads[payload_index].payload.data);
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

  json root;
  root["source"] = input.string();
  root["payload_index"] = payload_index;
  root["body_id"] = body.value;
  root["tolerance_m"] = tolerance;
  root["faces"] = json::array();

  for (const auto& face : bound.value().faces) {
    const auto* surface_node = model.FindNode(face.surface);
    if (!surface_node || !surface_node->geometry) {
      std::cerr << "missing surface " << face.surface.value << '\n';
      return 1;
    }
    const auto& surface_object =
        model.geometry()[surface_node->geometry.value()];
    const char* kind = SurfaceKind(surface_object.payload);

    std::vector<std::vector<SurfaceParameters>> loops;
    double umin = INFINITY, umax = -INFINITY;
    double vmin = INFINITY, vmax = -INFINITY;

    for (const auto& loop : face.loops) {
      std::vector<SurfaceParameters> points;
      for (const auto& fin : loop.fins) {
        constexpr int kSamples = 64;
        for (int sample = 0; sample <= kSamples; ++sample) {
          const double fraction =
              static_cast<double>(sample) / kSamples;
          const auto evaluated =
              EvaluateBoundFin(model, fin, fraction, tolerance);
          if (!evaluated.ok()) {
            std::cerr << "face " << face.face.value
                      << " fin " << fin.use.fin.value
                      << " sample failed: "
                      << evaluated.error().message << '\n';
            return 1;
          }
          auto uv = evaluated.value().uv;
          if (!points.empty()) {
            const SurfaceParameterSeed seed{points.back().u, points.back().v};
            const auto inverted = InvertSurface(
                model, face.surface, evaluated.value().curve.position,
                std::max(tolerance, 1e-6), seed);
            if (inverted.ok()) uv = inverted.value();
          }
          if (!points.empty()) {
            if (PeriodicU(kind))
              uv.u = NearestPeriodic(uv.u, points.back().u);
            if (PeriodicV(kind))
              uv.v = NearestPeriodic(uv.v, points.back().v);
            const double du = uv.u - points.back().u;
            const double dv = uv.v - points.back().v;
            if (du * du + dv * dv < 1e-20) {
              if (sample == kSamples) points.back() = uv;
              continue;
            }
          }
          points.push_back(uv);
        }
      }
      if (points.size() >= 2) {
        const double du = points.front().u - points.back().u;
        const double dv = points.front().v - points.back().v;
        if (du * du + dv * dv < 1e-16) points.pop_back();
      }
      if (points.size() < 3) continue;
      for (const auto& p : points) {
        umin = std::min(umin, p.u);
        umax = std::max(umax, p.u);
        vmin = std::min(vmin, p.v);
        vmax = std::max(vmax, p.v);
      }
      loops.push_back(std::move(points));
    }

    // Put every loop on the same periodic surface branch.
    if (!loops.empty() && PeriodicU(kind)) {
      const auto& first = loops.front();
      const double reference =
          0.5 * (first.front().u + first.back().u);
      for (std::size_t loop_index = 1; loop_index < loops.size();
           ++loop_index) {
        if (loops[loop_index].empty()) continue;
        const double center =
            0.5 * (loops[loop_index].front().u +
                   loops[loop_index].back().u);
        const double shift = std::round((reference - center) / kTwoPi) * kTwoPi;
        for (auto& point : loops[loop_index]) point.u += shift;
      }
    }
    if (!loops.empty() && PeriodicV(kind)) {
      const auto& first = loops.front();
      const double reference =
          0.5 * (first.front().v + first.back().v);
      for (std::size_t loop_index = 1; loop_index < loops.size();
           ++loop_index) {
        if (loops[loop_index].empty()) continue;
        const double center =
            0.5 * (loops[loop_index].front().v +
                   loops[loop_index].back().v);
        const double shift = std::round((reference - center) / kTwoPi) * kTwoPi;
        for (auto& point : loops[loop_index]) point.v += shift;
      }
    }

    umin = INFINITY;
    umax = -INFINITY;
    vmin = INFINITY;
    vmax = -INFINITY;
    for (const auto& loop : loops) {
      for (const auto& point : loop) {
        umin = std::min(umin, point.u);
        umax = std::max(umax, point.u);
        vmin = std::min(vmin, point.v);
        vmax = std::max(vmax, point.v);
      }
    }

    if (loops.empty() || !std::isfinite(umin) || umax <= umin ||
        vmax <= vmin) {
      std::cerr << "face " << face.face.value
                << " has no usable trim bounds\n";
      return 1;
    }

    std::vector<SurfaceParameters> all_points;
    std::vector<Vector3> xyz;
    std::vector<Vector3> normals;
    std::vector<bool> normal_valid;
    std::vector<std::vector<std::size_t>> loop_indices;
    std::vector<std::vector<std::size_t>> segments;
    std::map<std::tuple<int64_t, int64_t>, std::size_t> point_map;

    auto add_point = [&](const SurfaceParameters& uv) -> std::optional<std::size_t> {
      const int64_t key_u =
          static_cast<int64_t>(std::llround(uv.u * 1e10));
      const int64_t key_v =
          static_cast<int64_t>(std::llround(uv.v * 1e10));
      const auto key = std::make_tuple(key_u, key_v);
      if (const auto found = point_map.find(key); found != point_map.end())
        return found->second;
      const auto evaluated = EvaluateSurface(model, face.surface, uv.u, uv.v);
      if (!evaluated.ok()) {
        std::cerr << "face " << face.face.value << " surface "
                  << face.surface.value << " uv " << uv.u << ", " << uv.v
                  << " failed: " << evaluated.error().message << '\n';
        return std::nullopt;
      }
      const auto normal =
          EvaluateSurfaceNormal(model, face.surface, uv.u, uv.v);
      const std::size_t index = xyz.size();
      all_points.push_back(uv);
      xyz.push_back(evaluated.value().position);
      normals.push_back(normal.ok() ? normal.value() : Vector3{});
      normal_valid.push_back(normal.ok());
      point_map.emplace(key, index);
      return index;
    };

    for (const auto& loop_points : loops) {
      std::vector<std::size_t> indices;
      for (const auto& uv : loop_points) {
        const auto index = add_point(uv);
        if (!index) return 1;
        if (indices.empty() || indices.back() != *index)
          indices.push_back(*index);
      }
      if (indices.size() > 1 && indices.front() == indices.back())
        indices.pop_back();
      loop_indices.push_back(indices);
      for (std::size_t i = 0; i < indices.size(); ++i) {
        segments.push_back(
            {indices[i], indices[(i + 1) % indices.size()]});
      }
    }

    const double du = (umax - umin) / std::max(nu, 2);
    const double dv = (vmax - vmin) / std::max(nv, 2);
    for (int iu = 0; iu < nu; ++iu) {
      const double u = umin + (iu + 0.5) * du;
      for (int iv = 0; iv < nv; ++iv) {
        const double v = vmin + (iv + 0.5) * dv;
        bool inside = false;
        for (const auto& loop : loops) {
          if (PointInLoop(u, v, loop)) inside = !inside;
        }
        if (!inside) continue;
        auto added = add_point({u, v, 0.0});
        if (!added) return 1;
      }
    }

    const bool natural_sense =
        face.face_sense && surface_object.sense &&
        *face.face_sense == *surface_object.sense;

    json json_vertices = json::array();
    json json_normals = json::array();
    for (std::size_t i = 0; i < xyz.size(); ++i) {
      json_vertices.push_back(
          {all_points[i].u, all_points[i].v, xyz[i].x, xyz[i].y, xyz[i].z});
      json_normals.push_back(
          normal_valid[i]
              ? VecJson(normals[i])
              : json::array({nullptr, nullptr, nullptr}));
    }

    root["faces"].push_back(
        {{"face", face.face.value},
         {"surface", face.surface.value},
         {"kind", kind},
         {"normal_sign", natural_sense ? 1 : -1},
         {"uv_bounds", {umin, umax, vmin, vmax}},
         {"vertices", std::move(json_vertices)},
         {"surface_normals", std::move(json_normals)},
         {"loops", std::move(loop_indices)},
         {"segments", std::move(segments)}});
  }

  std::ofstream out(output, std::ios::binary | std::ios::trunc);
  if (!out) {
    std::cerr << "cannot open output\n";
    return 1;
  }
  out << root.dump(1) << '\n';
  if (!out) {
    std::cerr << "cannot write output\n";
    return 1;
  }
  std::cout << "wrote " << output << " faces=" << root["faces"].size() << '\n';
  return 0;
}
