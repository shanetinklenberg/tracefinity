"""Abstract base class and capability enum for bin STL generators."""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from app.services.polygon_scaler import ScaledPolygon


class GeneratorCapability(str, Enum):
    """Feature flags a generator can advertise via capabilities()."""
    STEP_EXPORT        = "step_export"        # .step CAD file output
    THREEMF            = "threemf"            # multi-material .3mf output
    CHAMFER            = "chamfer"            # cutout edge chamfering
    BIN_SPLITTING      = "bin_splitting"      # split large bins into bed-sized pieces
    INSERT             = "insert"             # contrast insert STL
    SCOOPS             = "scoops"             # finger scoop back wall
    DIVIDERS           = "dividers"           # interior length/width dividers
    LITE_STYLE         = "lite_style"         # thin-wall shell without raised floor
    TEXT_LABELS        = "text_labels"        # embossed/recessed text on bin floor
    CUSTOM_MAGNET_SIZE = "custom_magnet_size" # non-standard magnet diameter/depth
    RIM_UNITS          = "rim_units"          # raised rim collar above floor


class BinGenerator(ABC):
    """Interface for gridfinity bin generators.

    Concrete implementations advertise supported features via capabilities().
    Call sites use supports() to degrade gracefully when a feature is absent
    (e.g. skip passing step_path to a generator that lacks STEP_EXPORT).

    Swapping generators requires one line in routes.py:
        stl_generator: BinGenerator = SomeOtherGenerator()
    """

    @classmethod
    @abstractmethod
    def capabilities(cls) -> frozenset[GeneratorCapability]:
        """Return the set of features this generator implements."""
        ...

    def supports(self, cap: GeneratorCapability) -> bool:
        """Return True if this generator supports the given capability."""
        return cap in self.capabilities()

    @abstractmethod
    def generate_bin(
        self,
        polygons: list[ScaledPolygon],
        config: Any,
        output_path: str,
        threemf_path: str | None = None,
        step_path: str | None = None,
    ) -> tuple[Any, Any]:
        """Generate the main bin STL.

        Returns (bin_body, text_body | None). Both values are opaque
        geometry handles — callers must not inspect them, only pass them
        back to split_bin.
        """
        ...

    @abstractmethod
    def generate_insert(
        self,
        polygons: list[ScaledPolygon],
        config: Any,
        output_path: str,
        offset_x: float,
        offset_y: float,
    ) -> bool:
        """Generate a contrast insert STL. Returns True if a file was produced."""
        ...

    @abstractmethod
    def split_bin(
        self,
        bin_body: Any,
        text_body: Any,
        config: Any,
        bed_size: float,
        output_dir: str,
        session_id: str,
    ) -> list[str]:
        """Split bin into bed-sized pieces. Returns output STL paths."""
        ...
