"""printable marker sheet generation for fiducial paper detection.

generates an SVG with four ArUco DICT_4X4_50 markers positioned at the
corners of a paper sheet. the SVG is dimensioned in real-world mm so that
printing at "Actual size / 100% scale" produces physically correct markers.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.constants import PAPER_SIZES, PaperSize

_MARKER_MM = 15.0
_MARKER_INSET_MM = 15.0


def _marker_center_offset() -> float:
    """distance from paper corner to marker centre along each axis (mm)."""
    return _MARKER_INSET_MM + _MARKER_MM / 2.0  # 22.5 mm


def _marker_svg_group(marker_id: int, dictionary: cv2.aruco.Dictionary) -> str:
    """return an SVG <g> element for a single 15×15 mm ArUco marker.

    the marker is a 4×4 grid with a 1‑cell white border, rendered as white
    background plus black <rect> elements for each dark data cell.
    """
    side_px = 60  # must be divisible by 6 (border + 4 data + border)
    img = cv2.aruco.generateImageMarker(dictionary, marker_id, side_px)
    cell_px = side_px // 6  # pixels per logical cell
    cell_mm = _MARKER_MM / 6  # mm per logical cell (2.5 mm)

    rects: list[str] = []
    for data_row in range(4):
        for data_col in range(4):
            # logical grid position (skip the 1‑cell white border)
            grid_row = 1 + data_row
            grid_col = 1 + data_col
            px_y = grid_row * cell_px + cell_px // 2
            px_x = grid_col * cell_px + cell_px // 2
            if img[px_y, px_x] == 0:  # black pixel
                x = (1 + data_col) * cell_mm
                y = (1 + data_row) * cell_mm
                rects.append(
                    f'<rect x="{x:.2f}" y="{y:.2f}" '
                    f'width="{cell_mm:.2f}" height="{cell_mm:.2f}" fill="black"/>'
                )

    parts = [
        f'<rect x="0" y="0" width="{_MARKER_MM}" height="{_MARKER_MM}" '
        f'fill="white"/>',
        *rects,
    ]
    return "\n".join(parts)


def generate_marker_sheet_svg(paper_size: PaperSize) -> str:
    """generate a printable marker‑sheet SVG for *paper_size*.

    four ArUco markers (IDs 0‑3 for TL, TR, BR, BL) are placed inset
    from the paper corners.  the SVG uses mm units so that a print dialog
    set to "Actual size" produces correct physical markers.
    """
    width_mm, height_mm = PAPER_SIZES[paper_size]
    offset = _marker_center_offset()

    # marker centre positions on the paper (mm from top‑left)
    positions: dict[int, tuple[float, float]] = {
        0: (offset, offset),                     # TL
        1: (width_mm - offset, offset),           # TR
        2: (width_mm - offset, height_mm - offset),  # BR
        3: (offset, height_mm - offset),          # BL
    }

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

    marker_groups: list[str] = []
    for marker_id in [0, 1, 2, 3]:
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
