# Copyright 2026 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""The four watcher tools, defined as plain Python functions.

No MCP, no service, no port: two CSVs and one deployment call used by one agent.
Every number the agent reports comes from one of these tools; nothing is
computed in prose.
"""

import statistics
from typing import Any

from langchain_core.tools import BaseTool, tool

from agent.config import Config
from agent.drilling import scoring, telemetry
from agent.drilling.ops_log import get_ops_log as _get_ops_log
from agent.drilling.state import TelemetryRow, well_state
from agent.drilling.wells import WELL_IDS, WELL_POSITIONS

# maxExplanations requested from the deployment for the single-well tool.
_MAX_EXPLANATIONS: int = 6


def _median_channel(window: list[TelemetryRow], column: str) -> float:
    return statistics.median(float(row[column]) for row in window)


def _incident(well_event: bool, delta_flow: float) -> str | None:
    """Name the incident from the sign of delta flow when a well event is true.

    Positive delta flow = kick (fluid entering); negative = lost circulation
    (fluid leaving). The model does not provide this; null when no well event.
    """
    if not well_event:
        return None
    return "kick" if delta_flow > 0 else "lost_circulation"


def _score_one(
    well: str, as_of: str | None, config: Config, *, max_explanations: int = 0
) -> tuple[float, list[dict[str, object]], list[TelemetryRow], str]:
    """Resolve the window, score it, and return (probability, explanations, window, as_of)."""
    window = telemetry.resolve_window(well, as_of)
    resolved_as_of = window[-1]["timestamp"]
    llm_config = config  # naming kept explicit; config is the sole authority
    response = scoring.score_window(
        window,
        endpoint=llm_config.datarobot_endpoint,
        api_token=llm_config.datarobot_api_token or "",
        deployment_id=llm_config.deployment_drilling_classifier,
        max_explanations=max_explanations,
    )
    probability = scoring.extract_probability(response)
    explanations = (
        scoring.extract_explanations(response) if max_explanations > 0 else []
    )
    return probability, explanations, window, resolved_as_of


@tool
def get_fleet_status(as_of: str | None = None) -> dict[str, Any]:
    """Score all four wells at `as_of` (default: latest) and return one row per well.

    Call this first for any "how's the fleet" or "status" question. Makes four
    prediction calls. Each row carries the model probability, the physics-named
    state word, the primary channels, and the static latitude/longitude used only
    to plot the map (never scored, never reasoned over). `incident` is derived
    from the sign of delta flow when a well event is true, otherwise null; `as_of`
    echoes the exact timestamp scored.
    """
    config = Config()
    fleet: list[dict[str, Any]] = []
    for well in WELL_IDS:
        probability, _explanations, window, resolved_as_of = _score_one(
            well, as_of, config
        )
        state = well_state(window, probability)
        current = window[-1]
        delta_flow = float(current["delta_flow_gpm"])
        well_event = probability >= 0.5
        position = WELL_POSITIONS[well]
        fleet.append(
            {
                "well": well,
                "as_of": resolved_as_of,
                "probability": round(probability, 3),
                "well_event": well_event,
                "incident": _incident(well_event, delta_flow),
                "state": state,
                "delta_flow_gpm": round(delta_flow, 3),
                "pit_rate_bbl_per_min": round(
                    float(current["pit_rate_bbl_per_min"]), 3
                ),
                "spp_psi": round(float(current["spp_psi"]), 3),
                "gas_units": round(float(current["gas_units"]), 3),
                "latitude": position.latitude,
                "longitude": position.longitude,
            }
        )
    return {"fleet": fleet}


@tool
def score_well(well: str, as_of: str | None = None) -> dict[str, Any]:
    """Score one well at `as_of` (default: latest) with prediction explanations.

    `well` is GUY-001 through GUY-004. Call repeatedly with different `as_of`
    values to narrate how a probability ramped through onset. Explanations are
    signed - a negative strength argues AGAINST a well event. `matched_rows` is
    always 25 for a scorable as_of.
    """
    config = Config()
    probability, explanations, _window, resolved_as_of = _score_one(
        well, as_of, config, max_explanations=_MAX_EXPLANATIONS
    )
    return {
        "well": well,
        "as_of": resolved_as_of,
        "probability": round(probability, 3),
        "explanations": explanations,
        "matched_rows": telemetry.WINDOW_ROWS,
    }


@tool
def get_well_telemetry(
    well: str, as_of: str | None = None, channels: list[str] | None = None
) -> dict[str, Any]:
    """Raw telemetry window for one well ending at `as_of`, all six channels.

    Includes the three channels the model does not see (flow_out_gpm, gas_units,
    pit_volume_bbl). No scoring, no deployment call. `channels` is an optional
    subset; empty or omitted means all channels. `cumulative_pit_change_bbl` is
    the volume gained or lost across the window - a severity read, not detection.
    """
    telemetry.validate_well(well)
    window = telemetry.resolve_window(well, as_of)
    resolved_as_of = window[-1]["timestamp"]

    requested = tuple(channels) if channels else telemetry.ALL_CHANNELS
    unknown = [c for c in requested if c not in telemetry.ALL_CHANNELS]
    if unknown:
        raise telemetry.TelemetryError(
            f"unknown channel(s) {unknown}; valid channels are "
            f"{', '.join(telemetry.ALL_CHANNELS)}"
        )

    rows: list[dict[str, float | str]] = []
    for row in window:
        record: dict[str, float | str] = {"timestamp": row["timestamp"]}
        for channel in requested:
            record[channel] = round(float(row[channel]), 3)
        rows.append(record)

    current = rows[-1]
    first_pit = float(window[0]["pit_volume_bbl"])
    last_pit = float(window[-1]["pit_volume_bbl"])
    cumulative_pit_change = round(last_pit - first_pit, 3)

    return {
        "well": well,
        "as_of": resolved_as_of,
        "rows": rows,
        "current": current,
        "cumulative_pit_change_bbl": cumulative_pit_change,
    }


@tool
def get_ops_log(
    well: str, as_of: str | None = None, lookback_minutes: int = 15
) -> dict[str, Any]:
    """Operations log entries for a well as of a moment. THE MODEL CANNOT SEE THIS.

    Use it to tell a commanded operation from a formation event, and only after
    physics has named the state. An entry is active when
    `timestamp <= as_of <= timestamp + duration_min`; instant entries carry 0 and
    are never active. `explanatory` holds still-active pump_rate_change or
    mud_transfer entries that could account for a flow or pit change - the other
    seven event types explain nothing. `stale_explanatory` holds those same types
    once finished: history, never a cause.
    """
    result = _get_ops_log(well, as_of, lookback_minutes)
    return {
        "well": well,
        "as_of": as_of if as_of is not None else telemetry.latest_timestamp(well),
        "entries": [dict(entry) for entry in result.entries],
        "explanatory": [dict(entry) for entry in result.explanatory],
        "stale_explanatory": [dict(entry) for entry in result.stale_explanatory],
    }


def build_tools() -> list[BaseTool]:
    """All four watcher tools, for the graph factory."""
    return [get_fleet_status, score_well, get_well_telemetry, get_ops_log]
