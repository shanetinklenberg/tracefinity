"""printable marker sheet generation for fiducial paper detection.

generates an SVG with four ArUco DICT_4X4_50 markers positioned at the
corners of a paper sheet. the SVG is dimensioned in real-world mm so that
printing at "Actual size / 100% scale" produces physically correct markers.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.constants import PAPER_SIZES, PaperSize
from app.services.image_processor import _PAPER_MARKER_IDS

_MARKER_MM = 15.0
_MARKER_INSET_MM = 15.0


def _marker_center_offset() -> float:
    """distance from paper corner to marker centre along each axis (mm)."""
    return _MARKER_INSET_MM + _MARKER_MM / 2.0  # 22.5 mm


def _marker_svg_group(marker_id: int, dictionary: cv2.aruco.Dictionary) -> str:
    """return an SVG <image> element for a 15×15 mm ArUco marker.

    the marker is rendered at high resolution by OpenCV and embedded as a
    PNG data URI so the printed result matches exactly what the ArUco
    detector expects.  the SVG coordinates are in mm.
    """
    import base64
    import io

    # render at high resolution (divisible by 7 for correct ArUco cell grid)
    render_px = 126  # 7×18 — cleanly divisible, ~8.4 px/mm for 15 mm marker
    img = cv2.aruco.generateImageMarker(dictionary, marker_id, render_px)

    # encode as PNG data URI
    success, png_bytes = cv2.imencode(".png", img)
    if not success:
        # fallback: generate a larger version
        render_px = 210  # 7×30
        img = cv2.aruco.generateImageMarker(dictionary, marker_id, render_px)
        success, png_bytes = cv2.imencode(".png", img)

    b64 = base64.b64encode(png_bytes.tobytes()).decode("ascii")
    data_uri = f"data:image/png;base64,{b64}"

    return (
        f'<image x="0" y="0" width="{_MARKER_MM}" height="{_MARKER_MM}" '
        f'preserveAspectRatio="none" '
        f'href="{data_uri}"/>'
    )


def generate_marker_sheet_svg(paper_size: PaperSize) -> str:
    """generate a printable marker‑sheet SVG for *paper_size*.

    each paper size uses a unique set of four ArUco markers so the
    detector can auto-identify the paper format.  the SVG uses mm units
    so that a print dialog set to "Actual size" produces correct
    physical markers.
    """
    width_mm, height_mm = PAPER_SIZES[paper_size]
    offset = _marker_center_offset()

    # marker IDs for this paper size: (TL, TR, BR, BL)
    id_tl, id_tr, id_br, id_bl = _PAPER_MARKER_IDS[paper_size]

    # marker centre positions on the paper (mm from top‑left)
    positions: dict[int, tuple[float, float]] = {
        id_tl: (offset, offset),
        id_tr: (width_mm - offset, offset),
        id_br: (width_mm - offset, height_mm - offset),
        id_bl: (offset, height_mm - offset),
    }

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

    marker_groups: list[str] = []
    for marker_id in [id_tl, id_tr, id_br, id_bl]:
        cx, cy = positions[marker_id]
        # position the marker group so its top‑left corner is at (cx, cy)
        # offset by half the marker size to centre it
        x = cx - _MARKER_MM / 2.0
        y = cy - _MARKER_MM / 2.0
        marker_groups.append(
            f'<g transform="translate({x:.2f}, {y:.2f})">'
            f"{_marker_svg_group(marker_id, aruco_dict)}"
            f"</g>"
        )

    # registration marks at the exact paper corners for visual reference
    corner_marks = []
    for cx, cy in [
        (0, 0),
        (width_mm, 0),
        (width_mm, height_mm),
        (0, height_mm),
    ]:
        corner_marks.append(
            f'<line x1="{cx - 3}" y1="{cy}" x2="{cx + 3}" y2="{cy}" '
            f'stroke="black" stroke-width="0.5"/>'
            f'<line x1="{cx}" y1="{cy - 3}" x2="{cx}" y2="{cy + 3}" '
            f'stroke="black" stroke-width="0.5"/>'
        )

    # label
    label = (
        f'<text x="{width_mm / 2}" y="{height_mm - 4}" '
        f'text-anchor="middle" font-family="sans-serif" font-size="3" '
        f'fill="gray">Tracefinity marker sheet — {paper_size.upper()} — '
        f'print at 100% scale (Actual size)</text>'
    )

    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width_mm}mm" height="{height_mm}mm" '
        f'viewBox="0 0 {width_mm} {height_mm}">\n'
        f'<rect width="{width_mm}" height="{height_mm}" fill="white"/>\n'
        f'{"".join(corner_marks)}\n'
        f'{"".join(marker_groups)}\n'
        f'{label}\n'
        f'</svg>'
    )
    return svg
