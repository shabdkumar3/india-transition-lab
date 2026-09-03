"""
Technology Shift Detection (Step 15 §3).

Detects significant technology changes:
- new technology appears
- technology disappears
- share changes materially
- capacity build accelerates
- capacity retires

Uses documented, configurable thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from steel_model.diagnostics.pathway_record import PathwayRecord


@dataclass
class ShiftThresholds:
    """
    Documented thresholds for shift detection.

    All thresholds are explicit and configurable, never hard-coded
    without explanation.
    """
    # Absolute share change threshold (fraction of total production)
    share_change_abs: float = 0.05  # 5 percentage points

    # Relative share change threshold
    share_change_rel: float = 0.50  # 50% relative change

    # Capacity addition acceleration (year-over-year growth)
    ncap_growth_threshold: float = 0.50  # 50% YoY growth

    # New technology appearance threshold
    min_share_for_appearance: float = 0.01  # 1% share

    # Technology disappearance
    disappearance_threshold: float = 0.005  # 0.5% share

    def __post_init__(self):
        if not (0 < self.share_change_abs <= 1):
            raise ValueError("share_change_abs must be in (0, 1]")
        if not (0 < self.share_change_rel <= 10):
            raise ValueError("share_change_rel must be in (0, 10]")


@dataclass
class TechnologyShift:
    """Detected technology shift."""
    technology: str
    year: int
    shift_type: str  # "APPEARANCE", "DISAPPEARANCE", "SHARE_INCREASE", "SHARE_DECREASE", "NCAP_ACCELERATION", "RETIREMENT"
    magnitude: float
    previous_value: float
    current_value: float
    threshold_used: float
    confidence: str  # "HIGH", "MEDIUM", "LOW"


def detect_shifts(
    records: List[PathwayRecord],
    thresholds: Optional[ShiftThresholds] = None,
) -> List[TechnologyShift]:
    """
    Detect technology shifts from pathway records.

    Compares each year to the previous year for enabled technologies.
    """
    if thresholds is None:
        thresholds = ShiftThresholds()

    shifts = []

    # Group by technology
    by_tech: Dict[str, List[PathwayRecord]] = {}
    for r in records:
        by_tech.setdefault(r.technology, []).append(r)

    for tech, tech_records in by_tech.items():
        tech_records.sort(key=lambda r: r.year)

        for i in range(1, len(tech_records)):
            prev = tech_records[i - 1]
            curr = tech_records[i]

            # Skip if either year has no production data
            if prev.share is None or curr.share is None:
                continue

            # Share change detection
            share_diff = curr.share - prev.share
            abs_change = abs(share_diff)
            rel_change = abs(share_diff) / max(prev.share, 1e-6)

            # Appearance
            if prev.share < thresholds.min_share_for_appearance and curr.share >= thresholds.min_share_for_appearance:
                shifts.append(TechnologyShift(
                    technology=tech,
                    year=curr.year,
                    shift_type="APPEARANCE",
                    magnitude=curr.share,
                    previous_value=prev.share,
                    current_value=curr.share,
                    threshold_used=thresholds.min_share_for_appearance,
                    confidence="HIGH",
                ))

            # Disappearance
            if prev.share >= thresholds.disappearance_threshold and curr.share < thresholds.disappearance_threshold:
                shifts.append(TechnologyShift(
                    technology=tech,
                    year=curr.year,
                    shift_type="DISAPPEARANCE",
                    magnitude=prev.share,
                    previous_value=prev.share,
                    current_value=curr.share,
                    threshold_used=thresholds.disappearance_threshold,
                    confidence="HIGH",
                ))

            # Material share increase
            if share_diff >= thresholds.share_change_abs and rel_change >= thresholds.share_change_rel:
                shifts.append(TechnologyShift(
                    technology=tech,
                    year=curr.year,
                    shift_type="SHARE_INCREASE",
                    magnitude=share_diff,
                    previous_value=prev.share,
                    current_value=curr.share,
                    threshold_used=thresholds.share_change_abs,
                    confidence="HIGH" if rel_change >= 1.0 else "MEDIUM",
                ))

            # Material share decrease
            if share_diff <= -thresholds.share_change_abs and rel_change >= thresholds.share_change_rel:
                shifts.append(TechnologyShift(
                    technology=tech,
                    year=curr.year,
                    shift_type="SHARE_DECREASE",
                    magnitude=abs(share_diff),
                    previous_value=prev.share,
                    current_value=curr.share,
                    threshold_used=thresholds.share_change_abs,
                    confidence="HIGH" if rel_change >= 1.0 else "MEDIUM",
                ))

            # NCAP acceleration
            if prev.new_capacity_mt is not None and curr.new_capacity_mt is not None:
                if prev.new_capacity_mt > 0:
                    ncap_growth = (curr.new_capacity_mt - prev.new_capacity_mt) / prev.new_capacity_mt
                    if ncap_growth >= thresholds.ncap_growth_threshold:
                        shifts.append(TechnologyShift(
                            technology=tech,
                            year=curr.year,
                            shift_type="NCAP_ACCELERATION",
                            magnitude=ncap_growth,
                            previous_value=prev.new_capacity_mt,
                            current_value=curr.new_capacity_mt,
                            threshold_used=thresholds.ncap_growth_threshold,
                            confidence="MEDIUM",
                        ))

            # Retirement spike
            if prev.retired_capacity_mt is not None and curr.retired_capacity_mt is not None:
                if prev.retired_capacity_mt == 0 and curr.retired_capacity_mt > 0:
                    shifts.append(TechnologyShift(
                        technology=tech,
                        year=curr.year,
                        shift_type="RETIREMENT",
                        magnitude=curr.retired_capacity_mt,
                        previous_value=0.0,
                        current_value=curr.retired_capacity_mt,
                        threshold_used=0.0,
                        confidence="MEDIUM",
                    ))

    return shifts