"""
Technology shift detection (Step 15).
"""

from __future__ import annotations

from typing import Dict, List, Optional
from steel_model.optimization.model import BaselineInputs, BaselineMILPResult
from steel_model.explainability.schemas import TechnologyShift

DEFAULT_THRESHOLDS = {
    "presence_threshold": 0.05,
    "share_change_threshold": 0.10,
    "capacity_addition_threshold": 5.0,
    "retirement_threshold": 5.0,
}


def detect_technology_shifts(
    inputs: BaselineInputs,
    res: BaselineMILPResult,
    thresholds: Optional[Dict[str, float]] = None,
) -> List[TechnologyShift]:
    """Detect and record significant technology mix and capacity events over time."""
    if thresholds is None:
        th = DEFAULT_THRESHOLDS
    else:
        th = {**DEFAULT_THRESHOLDS, **thresholds}

    shifts: List[TechnologyShift] = []
    years = sorted(list(inputs.years))

    for r in inputs.all_routes:
        # Check active status first
        active = r in inputs.routes
        for idx, t in enumerate(years):
            ncap = res.ncap_mt.get(r, {}).get(t, 0.0) if active else 0.0
            ret = res.ret_mt.get(r, {}).get(t, 0.0) if active else 0.0
            share = res.production_share(r).get(t, 0.0) if active else 0.0

            # 1. Capacity Addition Spike
            if ncap >= th["capacity_addition_threshold"]:
                shifts.append(
                    TechnologyShift(
                        year=t,
                        technology=r,
                        event_type="SPIKE_ADDITION",
                        before_value=None,
                        after_value=float(ncap),
                        absolute_change=float(ncap),
                        threshold=th["capacity_addition_threshold"],
                        status="DETECTED",
                    )
                )

            # 2. Capacity Retirement Spike
            if ret >= th["retirement_threshold"]:
                shifts.append(
                    TechnologyShift(
                        year=t,
                        technology=r,
                        event_type="SPIKE_RETIREMENT",
                        before_value=None,
                        after_value=float(ret),
                        absolute_change=float(ret),
                        threshold=th["retirement_threshold"],
                        status="DETECTED",
                    )
                )

            # Check year-over-year share shifts
            if idx > 0:
                prev_t = years[idx - 1]
                prev_share = res.production_share(r).get(prev_t, 0.0) if active else 0.0
                change = share - prev_share

                # 3. Technology Appears
                if prev_share < th["presence_threshold"] and share >= th["presence_threshold"]:
                    shifts.append(
                        TechnologyShift(
                            year=t,
                            technology=r,
                            event_type="APPEARS",
                            before_value=float(prev_share),
                            after_value=float(share),
                            absolute_change=float(change),
                            threshold=th["presence_threshold"],
                            status="DETECTED",
                        )
                    )

                # 4. Technology Disappears
                elif prev_share >= th["presence_threshold"] and share < th["presence_threshold"]:
                    shifts.append(
                        TechnologyShift(
                            year=t,
                            technology=r,
                            event_type="DISAPPEARS",
                            before_value=float(prev_share),
                            after_value=float(share),
                            absolute_change=float(change),
                            threshold=th["presence_threshold"],
                            status="DETECTED",
                        )
                    )

                # 5. Share Rise / Fall
                if change >= th["share_change_threshold"]:
                    shifts.append(
                        TechnologyShift(
                            year=t,
                            technology=r,
                            event_type="RISE",
                            before_value=float(prev_share),
                            after_value=float(share),
                            absolute_change=float(change),
                            threshold=th["share_change_threshold"],
                            status="DETECTED",
                        )
                    )
                elif change <= -th["share_change_threshold"]:
                    shifts.append(
                        TechnologyShift(
                            year=t,
                            technology=r,
                            event_type="FALL",
                            before_value=float(prev_share),
                            after_value=float(share),
                            absolute_change=float(change),
                            threshold=th["share_change_threshold"],
                            status="DETECTED",
                        )
                    )

    return shifts
