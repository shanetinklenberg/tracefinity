"""CadQuery + cq-gridfinity bin generator."""
import logging
import math
import os
import tempfile
import time
from functools import reduce

import cadquery as cq
import cadquery.exporters as cq_exporters
from cqgridfinity import GridfinityBox

from app.models.schemas import GenerateRequest
from app.services.polygon_scaler import ScaledPolygon
from app.services.stl_generator_base import BinGenerator, GeneratorCapability

logger = logging.getLogger(__name__)

GF_GRID = 42.0
GF_HEIGHT_UNIT = 7.0
GF_BASE_HEIGHT = 4.75

# gridfinity stacking lip dimensions (LIP_D3 + LIP_D4 deducted from max pocket depth)
LIP_D3 = 1.2
LIP_D4 = 2.6
_LIP_DEPTH_DEDUCTION = LIP_D3 + LIP_D4


def _transform_pt(x: float, y: float, center_x: float, center_y: float) -> tuple[float, float]:
    """Bin-space (origin=bottom-left, Y-down) → CadQuery space (centered, Y-up)."""
    return (x - center_x, center_y - y)


def _resolve_pocket_depth(override: float | None, config, max_depth: float) -> float:
    base = override if override is not None else config.cutout_depth
    if getattr(config, "insert_enabled", False):
        base += getattr(config, "insert_height", 1.0)
    return max(5.0, min(base, max_depth))


class CQGridfinityGenerator(BinGenerator):
    @classmethod
    def capabilities(cls) -> frozenset[GeneratorCapability]:
        return frozenset(GeneratorCapability)  # supports all features

    def generate_bin(
        self,
        polygons: list[ScaledPolygon],
        config: GenerateRequest,
        output_path: str,
        threemf_path: str | None = None,
        step_path: str | None = None,
    ):
        """Generate bin using cq-gridfinity. Returns (bin_shape, text_shape | None)."""
        t0 = time.monotonic()

        grid_x, grid_y = config.grid_x, config.grid_y

        # cq-gridfinity hardcodes 6mm/2.4mm magnets; use its holes=True only when sizes match
        std_magnet = (
            abs(getattr(config, "magnet_diameter", 6.0) - 6.0) < 0.01
            and abs(getattr(config, "magnet_depth", 2.4) - 2.4) < 0.01
            and not getattr(config, "magnet_corners_only", False)
        )
        use_cq_holes = config.magnets and std_magnet

        box = GridfinityBox(
            grid_x,
            grid_y,
            config.height_units,
            holes=use_cq_holes,
            no_lip=not config.stacking_lip,
            wall_th=config.wall_thickness,
            scoops=getattr(config, "scoops", False),
            scoop_rad=getattr(config, "scoop_rad", 11.0),
            labels=getattr(config, "front_label", False),
            label_width=getattr(config, "label_width", 12.0),
            length_div=getattr(config, "length_div", 0),
            width_div=getattr(config, "width_div", 0),
            lite_style=getattr(config, "lite_style", False),
        )
        logger.info("GridfinityBox shell: %.2fs", time.monotonic() - t0)

        bin_solid = box.cq_obj.val()

        center_x = grid_x * GF_GRID / 2
        center_y = grid_y * GF_GRID / 2
        wall_top_z = config.height_units * GF_HEIGHT_UNIT
        lip_deduction = _LIP_DEPTH_DEDUCTION if config.stacking_lip else 0.0
        max_depth = wall_top_z - GF_BASE_HEIGHT - 2.0 - lip_deduction
        z_cut = box.top_ref_height

        # custom magnet holes when size differs from gridfinity standard
        if config.magnets and not use_cq_holes:
            t1 = time.monotonic()
            bin_solid = self._cut_magnet_holes(bin_solid, config)
            logger.info("magnet holes (custom): %.2fs", time.monotonic() - t1)

        # raised rim collar (hollow wall above floor)
        rim_units = (getattr(config, "rim_units", 0) or 0) if config.stacking_lip else 0
        if rim_units > 0:
            t1 = time.monotonic()
            bin_solid = self._add_rim_collar(bin_solid, config, rim_units, wall_top_z)
            logger.info("rim collar (%du): %.2fs", rim_units, time.monotonic() - t1)

        if polygons:
            t1 = time.monotonic()
            for sp in polygons:
                pts = [_transform_pt(p[0], p[1], center_x, center_y) for p in sp.points_mm]
                inner_rings = [
                    [_transform_pt(p[0], p[1], center_x, center_y) for p in ring]
                    for ring in sp.interior_rings_mm
                ]
                depth = _resolve_pocket_depth(sp.depth_override, config, max_depth)
                cutter = self._make_polygon_cutter(pts, inner_rings, z_cut, depth)
                if cutter is not None:
                    bin_solid = bin_solid.cut(cutter)
            logger.info("polygon cutouts (%d): %.2fs", len(polygons), time.monotonic() - t1)

            t1 = time.monotonic()
            for sp in polygons:
                for fh in sp.finger_holes:
                    fh_x, fh_y = _transform_pt(fh.x_mm, fh.y_mm, center_x, center_y)
                    fh_depth = _resolve_pocket_depth(fh.depth_override, config, max_depth)
                    cutter = self._make_finger_hole_cutter(fh, fh_x, fh_y, z_cut, fh_depth)
                    if cutter is not None:
                        bin_solid = bin_solid.cut(cutter)
            logger.info("finger holes: %.2fs", time.monotonic() - t1)

            chamfer = getattr(config, "cutout_chamfer", 0.0)
            if chamfer > 0:
                t1 = time.monotonic()
                for sp in polygons:
                    pts = [_transform_pt(p[0], p[1], center_x, center_y) for p in sp.points_mm]
                    inner_rings = [
                        [_transform_pt(p[0], p[1], center_x, center_y) for p in ring]
                        for ring in sp.interior_rings_mm
                    ]
                    c = self._make_chamfer_cutter(pts, inner_rings, z_cut, chamfer)
                    if c is not None:
                        bin_solid = bin_solid.cut(c)
                    for fh in sp.finger_holes:
                        fh_x, fh_y = _transform_pt(fh.x_mm, fh.y_mm, center_x, center_y)
                        fc = self._make_fh_chamfer_cutter(fh, fh_x, fh_y, z_cut, chamfer)
                        if fc is not None:
                            bin_solid = bin_solid.cut(fc)
                logger.info("chamfer cutouts: %.2fs", time.monotonic() - t1)

        text_body = None
        if config.text_labels:
            t1 = time.monotonic()
            bin_solid, text_body = self._apply_text_labels(
                bin_solid, config, z_cut, center_x, center_y
            )
            logger.info("text labels: %.2fs", time.monotonic() - t1)

        logger.info("total generate_bin: %.2fs", time.monotonic() - t0)

        out_wp = cq.Workplane().add(bin_solid)
        if text_body is not None:
            cq_exporters.export(cq.Workplane().add(bin_solid).add(text_body), output_path)
        else:
            cq_exporters.export(out_wp, output_path)
        logger.info("export_stl: %.2fs", time.monotonic() - t0)

        if step_path:
            try:
                cq_exporters.export(out_wp, step_path)
                logger.info("export_step done")
            except Exception:
                logger.warning("STEP export failed", exc_info=True)

        if text_body is not None and threemf_path:
            try:
                import trimesh
                scene = trimesh.Scene()
                scene.add_geometry(self._cq_to_trimesh(bin_solid), node_name="bin", geom_name="bin")
                scene.add_geometry(self._cq_to_trimesh(text_body), node_name="text", geom_name="text")
                data = scene.export(file_type="3mf")
                with open(threemf_path, "wb") as f:
                    f.write(data)
            except Exception:
                logger.warning("3MF export failed", exc_info=True)

        return bin_solid, text_body

    # ── cutter builders ───────────────────────────────────────────────────────

    def _make_polygon_cutter(
        self,
        pts: list[tuple[float, float]],
        inner_rings: list[list[tuple[float, float]]],
        z_start: float,
        depth: float,
    ):
        if len(pts) < 3:
            return None
        try:
            outer_wire = cq.Wire.makePolygon([cq.Vector(x, y, z_start) for x, y in pts])
            inner_wires = [
                cq.Wire.makePolygon([cq.Vector(x, y, z_start) for x, y in ring])
                for ring in inner_rings
                if len(ring) >= 3
            ]
            return cq.Solid.extrudeLinear(outer_wire, inner_wires, cq.Vector(0, 0, -depth))
        except Exception:
            logger.warning("polygon cutter failed (%d pts), skipping", len(pts), exc_info=True)
            return None

    def _make_finger_hole_cutter(
        self, fh, x: float, y: float, z_start: float, depth: float
    ):
        try:
            shape = getattr(fh, "shape", "circle")
            rot = getattr(fh, "rotation", 0.0)
            eps = 0.01

            if shape in ("circle", "cylinder"):
                r = fh.radius_mm
                solid = (
                    cq.Workplane("XY")
                    .workplane(offset=z_start)
                    .moveTo(x, y)
                    .circle(r)
                    .extrude(-(depth + eps), combine=False)
                    .val()
                )
                return solid

            elif shape == "square":
                w = fh.radius_mm * 2
                solid = (
                    cq.Workplane("XY")
                    .workplane(offset=z_start)
                    .moveTo(x, y)
                    .rect(w, w)
                    .extrude(-(depth + eps), combine=False)
                    .val()
                )

            elif shape == "rectangle":
                w = fh.width_mm or fh.radius_mm * 2
                h = fh.height_mm or fh.radius_mm * 2
                solid = (
                    cq.Workplane("XY")
                    .workplane(offset=z_start)
                    .moveTo(x, y)
                    .rect(w, h)
                    .extrude(-(depth + eps), combine=False)
                    .val()
                )

            elif shape == "filleted_rectangle":
                w = fh.width_mm or fh.radius_mm * 2
                h = fh.height_mm or fh.radius_mm * 2
                fillet_r = min(w / 3.0, depth / 2.0, min(w, h) / 2.0 - 0.01)
                solid = (
                    cq.Workplane("XY")
                    .workplane(offset=z_start)
                    .moveTo(x, y)
                    .rect(w, h)
                    .extrude(-(depth + eps), combine=False)
                    .edges("|Z")
                    .fillet(max(0.01, fillet_r))
                    .val()
                )

            else:
                return None

            if rot != 0:
                solid = solid.rotate(cq.Vector(x, y, 0), cq.Vector(x, y, 1), rot)
            return solid

        except Exception:
            logger.warning("finger hole cutter failed (%s), skipping", shape, exc_info=True)
            return None

    def _make_chamfer_cutter(
        self,
        pts: list[tuple[float, float]],
        inner_rings: list[list[tuple[float, float]]],
        z_start: float,
        chamfer: float,
    ):
        if len(pts) < 3:
            return None
        try:
            from shapely.geometry import Polygon as SPoly
            from shapely.validation import make_valid

            sp = SPoly(pts, holes=inner_rings or [])
            if not sp.is_valid:
                sp = make_valid(sp)
            expanded = sp.buffer(chamfer, join_style=2)
            if expanded.is_empty or expanded.geom_type != "Polygon":
                return None

            top_pts = list(expanded.exterior.coords)[:-1]
            top_wire = cq.Wire.makePolygon(
                [cq.Vector(x, y, z_start + chamfer) for x, y in top_pts]
            )
            bot_wire = cq.Wire.makePolygon([cq.Vector(x, y, z_start) for x, y in pts])
            return cq.Solid.makeLoft([top_wire, bot_wire])
        except Exception:
            logger.warning("chamfer cutter failed, skipping", exc_info=True)
            return None

    def _make_fh_chamfer_cutter(
        self, fh, x: float, y: float, z_start: float, chamfer: float
    ):
        try:
            shape = getattr(fh, "shape", "circle")
            if shape in ("circle", "cylinder"):
                r = fh.radius_mm
                top_wire = cq.Wire.makeCircle(
                    r + chamfer, cq.Vector(x, y, z_start + chamfer), cq.Vector(0, 0, 1)
                )
                bot_wire = cq.Wire.makeCircle(r, cq.Vector(x, y, z_start), cq.Vector(0, 0, 1))
                return cq.Solid.makeLoft([top_wire, bot_wire])
        except Exception:
            logger.warning("fh chamfer cutter failed (%s), skipping", shape, exc_info=True)
        return None

    # ── geometry additions ────────────────────────────────────────────────────

    def _add_rim_collar(self, bin_solid, config, rim_units: int, wall_top_z: float):
        """Hollow collar above the floor for rim_units > 0."""
        try:
            outer_w = config.grid_x * GF_GRID - 0.5
            outer_h = config.grid_y * GF_GRID - 0.5
            # inner opening matches the stacking lip inner face (LIP_D0=1.9 + LIP_D2=0.7 = 2.6)
            lip_inset = 2.6
            inner_w = outer_w - 2 * lip_inset
            inner_h = outer_h - 2 * lip_inset
            rim_h = rim_units * GF_HEIGHT_UNIT

            outer_solid = (
                cq.Workplane("XY")
                .workplane(offset=wall_top_z)
                .rect(outer_w, outer_h)
                .extrude(rim_h, combine=False)
                .val()
            )
            inner_solid = (
                cq.Workplane("XY")
                .workplane(offset=wall_top_z)
                .rect(inner_w, inner_h)
                .extrude(rim_h + 0.01, combine=False)
                .val()
            )
            collar = outer_solid.cut(inner_solid)
            return bin_solid.union(collar)
        except Exception:
            logger.warning("rim collar failed, skipping", exc_info=True)
            return bin_solid

    def _cut_magnet_holes(self, bin_solid, config):
        """Custom-size magnet holes at standard gridfinity positions."""
        try:
            diameter = getattr(config, "magnet_diameter", 6.0)
            depth = getattr(config, "magnet_depth", 2.4)
            corners_only = getattr(config, "magnet_corners_only", False)
            grid_x, grid_y = config.grid_x, config.grid_y
            r = diameter / 2

            outer_corners: set = set()
            if corners_only:
                for ix, iy, dx, dy in [
                    (0, 0, -13.0, -13.0),
                    (grid_x - 1, 0, 13.0, -13.0),
                    (grid_x - 1, grid_y - 1, 13.0, 13.0),
                    (0, grid_y - 1, -13.0, 13.0),
                ]:
                    cx = (ix - (grid_x - 1) / 2.0) * GF_GRID
                    cy = (iy - (grid_y - 1) / 2.0) * GF_GRID
                    outer_corners.add((round(cx + dx, 4), round(cy + dy, 4)))

            for iy in range(grid_y):
                for ix in range(grid_x):
                    cx = (ix - (grid_x - 1) / 2.0) * GF_GRID
                    cy = (iy - (grid_y - 1) / 2.0) * GF_GRID
                    for dx, dy in [(-13.0, -13.0), (13.0, -13.0), (13.0, 13.0), (-13.0, 13.0)]:
                        pos = (round(cx + dx, 4), round(cy + dy, 4))
                        if corners_only and pos not in outer_corners:
                            continue
                        hole = (
                            cq.Workplane("XY")
                            .moveTo(pos[0], pos[1])
                            .circle(r)
                            .extrude(depth + 0.01, combine=False)
                            .val()
                        )
                        bin_solid = bin_solid.cut(hole)
            return bin_solid
        except Exception:
            logger.warning("custom magnet holes failed, skipping", exc_info=True)
            return bin_solid

    def _apply_text_labels(self, bin_solid, config, z_cut, center_x, center_y):
        """Apply text labels using CadQuery native font rendering."""
        text_shapes = []
        for tl in config.text_labels:
            try:
                lx, ly = _transform_pt(tl.x, tl.y, center_x, center_y)
                extrude_dist = tl.depth if tl.emboss else -tl.depth

                text_solid = (
                    cq.Workplane("XY")
                    .text(tl.text, tl.font_size, extrude_dist, cut=False, combine=False)
                    .val()
                )
                if tl.rotation != 0:
                    text_solid = text_solid.rotate(
                        cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), tl.rotation
                    )
                text_solid = text_solid.translate(cq.Vector(lx, ly, z_cut))

                if tl.emboss:
                    text_shapes.append(text_solid)
                    bin_solid = bin_solid.union(text_solid)
                else:
                    bin_solid = bin_solid.cut(text_solid)
            except Exception:
                logger.warning("text label '%s' failed, skipping", tl.text, exc_info=True)

        text_body = None
        if text_shapes:
            text_body = reduce(lambda a, b: a.union(b), text_shapes)

        return bin_solid, text_body

    # ── insert ────────────────────────────────────────────────────────────────

    def generate_insert(
        self,
        polygons: list[ScaledPolygon],
        config,
        output_path: str,
        offset_x: float,
        offset_y: float,
    ) -> bool:
        """Generate a thin insert plate for the bin cutouts."""
        try:
            from shapely.geometry import Polygon as SPoly
            from shapely.validation import make_valid

            insert_height = getattr(config, "insert_height", 1.0)
            fit_clearance = getattr(config, "insert_clearance", 0.2)

            shapes = []
            for sp in polygons:
                # same coordinate transform as manifold: (x+offset_x, -(y+offset_y))
                pts_2d = [(p[0] + offset_x, -(p[1] + offset_y)) for p in sp.points_mm]
                if len(pts_2d) < 3:
                    continue
                holes_2d = [
                    [(p[0] + offset_x, -(p[1] + offset_y)) for p in ring]
                    for ring in (sp.interior_rings_mm or [])
                    if len(ring) >= 3
                ]

                if fit_clearance > 0:
                    poly = SPoly(pts_2d, holes=holes_2d)
                    if not poly.is_valid:
                        poly = make_valid(poly)
                    shrunk = poly.buffer(-fit_clearance, join_style=2)
                    if shrunk.is_empty:
                        continue
                    pieces = (
                        [shrunk]
                        if shrunk.geom_type == "Polygon"
                        else [g for g in getattr(shrunk, "geoms", []) if g.geom_type == "Polygon"]
                    )
                    for piece in pieces:
                        piece_pts = list(piece.exterior.coords)[:-1]
                        piece_holes = [list(i.coords)[:-1] for i in piece.interiors]
                        solid = self._extrude_polygon(piece_pts, piece_holes, 0.0, insert_height)
                        if solid is not None:
                            shapes.append(solid)
                else:
                    solid = self._extrude_polygon(pts_2d, holes_2d, 0.0, insert_height)
                    if solid is not None:
                        shapes.append(solid)

            if not shapes:
                return False

            result = reduce(lambda a, b: a.union(b), shapes)
            cq_exporters.export(cq.Workplane().add(result), output_path)
            return True
        except Exception:
            logger.exception("insert generation failed")
            return False

    def _extrude_polygon(
        self,
        pts: list[tuple[float, float]],
        inner_rings: list[list[tuple[float, float]]],
        z_start: float,
        height: float,
    ):
        if len(pts) < 3:
            return None
        try:
            outer_wire = cq.Wire.makePolygon([cq.Vector(x, y, z_start) for x, y in pts])
            inner_wires = [
                cq.Wire.makePolygon([cq.Vector(x, y, z_start) for x, y in ring])
                for ring in inner_rings
                if len(ring) >= 3
            ]
            return cq.Solid.extrudeLinear(outer_wire, inner_wires, cq.Vector(0, 0, height))
        except Exception:
            return None

    # ── splitting ─────────────────────────────────────────────────────────────

    def split_bin(
        self,
        bin_body,
        text_body,
        config: GenerateRequest,
        bed_size: float,
        output_dir: str,
        session_id: str,
    ) -> list[str]:
        """Split bin into bed-sized pieces. Returns list of output STL paths."""
        bin_width = config.grid_x * GF_GRID
        bin_depth = config.grid_y * GF_GRID

        if (bin_width + bin_depth) / math.sqrt(2) <= bed_size:
            return []

        x_cuts = self._compute_split_points(bin_width, config.grid_x, bed_size)
        y_cuts = self._compute_split_points(bin_depth, config.grid_y, bed_size)

        if not x_cuts and not y_cuts:
            return []

        part = bin_body.union(text_body) if text_body is not None else bin_body

        x_pieces = self._split_along_axis(part, x_cuts, axis="x")
        pieces = []
        for xp in x_pieces:
            pieces.extend(self._split_along_axis(xp, y_cuts, axis="y"))

        paths = []
        for i, piece in enumerate(pieces):
            path = f"{output_dir}/{session_id}_part{i + 1}.stl"
            cq_exporters.export(cq.Workplane().add(piece), path)
            paths.append(path)

        return paths

    @staticmethod
    def _compute_split_points(total_mm: float, grid_count: int, bed_size: float) -> list[float]:
        max_units = max(1, int(bed_size // GF_GRID))
        num_pieces = math.ceil(grid_count / max_units)
        if num_pieces <= 1:
            return []
        base = grid_count // num_pieces
        extra = grid_count % num_pieces
        sizes = [base + (1 if i < extra else 0) for i in range(num_pieces)]
        points: list[float] = []
        pos = -total_mm / 2
        for s in sizes[:-1]:
            pos += s * GF_GRID
            points.append(pos)
        return points

    @staticmethod
    def _split_along_axis(part, cut_points: list[float], axis: str) -> list:
        if not cut_points:
            return [part]

        SIZE = 1000.0
        pieces = []
        all_bounds = [-SIZE] + list(cut_points) + [SIZE]

        for i in range(len(all_bounds) - 1):
            lo, hi = all_bounds[i], all_bounds[i + 1]
            center = (lo + hi) / 2
            width = hi - lo

            if axis == "x":
                slab = (
                    cq.Workplane("XY")
                    .box(width, SIZE * 2, SIZE * 2)
                    .translate((center, 0, SIZE))
                    .val()
                )
            else:
                slab = (
                    cq.Workplane("XY")
                    .box(SIZE * 2, width, SIZE * 2)
                    .translate((0, center, SIZE))
                    .val()
                )

            try:
                piece = part.intersect(slab)
                try:
                    vol = piece.Volume
                except Exception:
                    vol = 1.0
                if vol > 0.01:
                    pieces.append(piece)
            except Exception:
                logger.warning("split slab %d failed, skipping", i, exc_info=True)

        return pieces if pieces else [part]

    # ── trimesh helper for 3MF ────────────────────────────────────────────────

    def _cq_to_trimesh(self, shape):
        import trimesh
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
            tmp = f.name
        try:
            cq_exporters.export(cq.Workplane().add(shape), tmp)
            return trimesh.load(tmp)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
