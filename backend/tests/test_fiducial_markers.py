"""Fiducial marker detection: marker-centres-to-corner mapping.

Tests verify the homography-based mapping from detected ArUco marker centres
to estimated paper corners.  No fixture images needed — we simulate marker
corner detections via a synthetic pinhole camera projection.
"""

import math

import numpy as np
import pytest

from app.services.image_processor import (
    ImageProcessor,
    _MARKER_CENTER_OFFSET,
    _MARKER_MM,
)


# ---------------------------------------------------------------------------
# synthetic camera helpers (same pattern as test_paper_orientation.py)
# ---------------------------------------------------------------------------

def _rot_x(deg: float) -> np.ndarray:
    t = math.radians(deg)
    return np.array([
        [1, 0, 0],
        [0, math.cos(t), -math.sin(t)],
        [0, math.sin(t), math.cos(t)],
    ])


def _rot_y(deg: float) -> np.ndarray:
    t = math.radians(deg)
    return np.array([
        [math.cos(t), 0, math.sin(t)],
        [0, 1, 0],
        [-math.sin(t), 0, math.cos(t)],
    ])


def _rot_z(deg: float) -> np.ndarray:
    t = math.radians(deg)
    return np.array([
        [math.cos(t), -math.sin(t), 0],
        [math.sin(t), math.cos(t), 0],
        [0, 0, 1],
    ])


def _project(
    points_3d: np.ndarray,
    tilt_deg: float = 30.0,
    distance: float = 420.0,
    focal: float = 800.0,
    yaw_deg: float = 8.0,
    roll_deg: float = 6.0,
    offset_x: float = 320.0,
    offset_y: float = 240.0,
) -> list[tuple[float, float]]:
    """project 3-D points into a 640×480 synthetic image."""
    rot = _rot_z(roll_deg) @ _rot_y(yaw_deg) @ _rot_x(tilt_deg)
    projected: list[tuple[float, float]] = []
    for p in points_3d:
        q = rot @ p + np.array([0.0, 0.0, distance])
        projected.append((float(focal * q[0] / q[2] + offset_x),
                          float(focal * q[1] / q[2] + offset_y)))
    return projected


def _build_marker_detections(
    width_mm: float,
    height_mm: float,
    tilt_deg: float = 30.0,
    **kwargs,
) -> tuple[list[np.ndarray], np.ndarray]:
    """return synthetic (corners_list, ids) for four markers on the paper.

    markers are 15×15 mm squares inset 15 mm from the paper corners.
    ID 0 = TL, 1 = TR, 2 = BR, 3 = BL.
    """
    offset = _MARKER_CENTER_OFFSET  # 22.5 mm
    half_marker = _MARKER_MM / 2.0   # 7.5 mm

    # marker centres in 3-D (paper on XY plane, centred at origin)
    centres: dict[int, tuple[float, float]] = {
        0: (-width_mm / 2 + offset, -height_mm / 2 + offset),   # TL
        1: ( width_mm / 2 - offset, -height_mm / 2 + offset),   # TR
        2: ( width_mm / 2 - offset,  height_mm / 2 - offset),   # BR
        3: (-width_mm / 2 + offset,  height_mm / 2 - offset),   # BL
    }

    corners_list: list[np.ndarray] = []
    ids_list: list[int] = []

    for marker_id in [0, 1, 2, 3]:
        cx, cy = centres[marker_id]
        corners_3d = np.array([
            [cx - half_marker, cy - half_marker, 0.0],
            [cx + half_marker, cy - half_marker, 0.0],
            [cx + half_marker, cy + half_marker, 0.0],
            [cx - half_marker, cy + half_marker, 0.0],
        ], dtype=np.float64)
        projected = _project(corners_3d, tilt_deg=tilt_deg, **kwargs)
        corners_list.append(
            np.array([[(p[0], p[1]) for p in projected]], dtype=np.float32)
        )
        ids_list.append(marker_id)

    ids = np.array([[i] for i in ids_list], dtype=np.int32)
    return corners_list, ids


def _project_paper_corners(
    width_mm: float,
    height_mm: float,
    tilt_deg: float = 30.0,
    **kwargs,
) -> list[tuple[float, float]]:
    """project the four paper corners (ground truth)."""
    hw, hh = width_mm / 2.0, height_mm / 2.0
    corners_3d = np.array([
        [-hw, -hh, 0.0],  # TL
        [ hw, -hh, 0.0],  # TR
        [ hw,  hh, 0.0],  # BR
        [-hw,  hh, 0.0],  # BL
    ], dtype=np.float64)
    return _project(corners_3d, tilt_deg=tilt_deg, **kwargs)


# ---------------------------------------------------------------------------
# test instance (no U2-Net load)
# ---------------------------------------------------------------------------

@pytest.fixture
def proc() -> ImageProcessor:
    """ImageProcessor without the expensive model load."""
    return object.__new__(ImageProcessor)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

class TestMarkerCornersFromDetections:
    """unit tests for _marker_corners_from_detections homography mapping."""

    def test_all_four_markers_found_returns_corners(self, proc):
        """A4 portrait: computed corners match ground-truth within 1 px."""
        corners_list, ids = _build_marker_detections(210, 297, tilt_deg=30)
        result = proc._marker_corners_from_detections(corners_list, ids)
        assert result is not None
        assert len(result) == 4

        ground_truth = _project_paper_corners(210, 297, tilt_deg=30)
        for i, ((cx, cy), (gx, gy)) in enumerate(zip(result, ground_truth)):
            assert abs(cx - gx) < 1.0, f"corner {i} x off by {abs(cx - gx):.3f}"
            assert abs(cy - gy) < 1.0, f"corner {i} y off by {abs(cy - gy):.3f}"

    def test_missing_marker_returns_none(self, proc):
        """only 3 markers → None."""
        corners_list, ids = _build_marker_detections(210, 297)
        corners_list_3 = corners_list[:2] + corners_list[3:]
        ids_3 = np.array([[0], [1], [3]], dtype=np.int32)
        assert proc._marker_corners_from_detections(corners_list_3, ids_3) is None

    def test_wrong_marker_ids_returns_none(self, proc):
        """markers 10-13 instead of 0-3 → None."""
        corners_list, _ = _build_marker_detections(210, 297)
        ids_wrong = np.array([[10], [11], [12], [13]], dtype=np.int32)
        assert proc._marker_corners_from_detections(corners_list, ids_wrong) is None

    def test_degenerate_small_marker_rejected(self, proc):
        """marker edge shorter than 1 px → None."""
        corners_list, ids = _build_marker_detections(210, 297)
        for i in range(4):
            centre = corners_list[i][0].mean(axis=0)
            corners_list[i] = np.array(
                [[(centre[0], centre[1]) for _ in range(4)]], dtype=np.float32
            )
        assert proc._marker_corners_from_detections(corners_list, ids) is None

    def test_landscape_orientation_auto_detected(self, proc):
        """landscape-oriented A4 (297×210): method infers landscape and
        computes correct corners."""
        corners_list, ids = _build_marker_detections(297, 210, tilt_deg=25)
        result = proc._marker_corners_from_detections(corners_list, ids)
        assert result is not None
        assert len(result) == 4

        ground_truth = _project_paper_corners(297, 210, tilt_deg=25)
        for i, ((cx, cy), (gx, gy)) in enumerate(zip(result, ground_truth)):
            assert abs(cx - gx) < 1.0, f"corner {i} x off by {abs(cx - gx):.3f}"
            assert abs(cy - gy) < 1.0, f"corner {i} y off by {abs(cy - gy):.3f}"

    def test_steep_tilt_corners_accurate(self, proc):
        """45° tilt with perspective foreshortening: homography handles
        both axes independently so corners stay accurate."""
        corners_list, ids = _build_marker_detections(210, 297, tilt_deg=45)
        result = proc._marker_corners_from_detections(corners_list, ids)
        assert result is not None

        ground_truth = _project_paper_corners(210, 297, tilt_deg=45)
        for i, ((cx, cy), (gx, gy)) in enumerate(zip(result, ground_truth)):
            assert abs(cx - gx) < 1.0, f"corner {i} x off by {abs(cx - gx):.3f}"
            assert abs(cy - gy) < 1.0, f"corner {i} y off by {abs(cy - gy):.3f}"

    def test_letter_paper_approximate(self, proc):
        """US Letter sheet detected with A4 assumption: corners are close
        enough to serve as a starting point for user refinement."""
        corners_list, ids = _build_marker_detections(215.9, 279.4, tilt_deg=30)
        result = proc._marker_corners_from_detections(corners_list, ids)
        assert result is not None
        assert len(result) == 4

        ground_truth = _project_paper_corners(215.9, 279.4, tilt_deg=30)
        # Letter vs A4 discrepancy means corners will be off by a few px,
        # but still well within the range the user can refine.
        for i, ((cx, cy), (gx, gy)) in enumerate(zip(result, ground_truth)):
            assert abs(cx - gx) < 5.0, f"corner {i} x off by {abs(cx - gx):.3f}"
            assert abs(cy - gy) < 5.0, f"corner {i} y off by {abs(cy - gy):.3f}"
