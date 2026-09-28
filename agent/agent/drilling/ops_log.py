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
"""The operations log - how a commanded operation is told from a formation event.

The model cannot see this. Exactly two event types can explain a sensor
signature: pump_rate_change and mud_transfer. The rest explain nothing, however
close in time. An entry is active only while it is still happening:
``timestamp <= as_of <= timestamp + duration_min``. A finished entry is history,
never a cause; its absence can never create a state.
"""

import csv
from datetime import timedelta
from pathlib import Path

from agent.drilling.state import OpsLogEntry
from agent.drilling.telemetry import (
    TelemetryError,
    latest_timestamp,
    parse_timestamp,
    validate_well,
)

DEFAULT_LOOKBACK_MINUTES: int = 15

# The only two event types that can account for a flow or pit change. The other
# seven - shaker_screen, equipment_check, mud_check, crew_change, survey,
# bit_record, safety_meeting - explain nothing.
EXPLANATORY_EVENT_TYPES: frozenset[str] = frozenset(
    {"pump_rate_change", "mud_transfer"}
)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_OPS_LOG_PATH = _DATA_DIR / "drilling-ops-log.csv"


def _load() -> dict[str, list[dict[str, str]]]:
    if not _OPS_LOG_PATH.exists():
        raise TelemetryError(
            f"ops-log file not found at {_OPS_LOG_PATH}; the dataset must be "
            "fetched from the AI Catalog before the agent can run"
        )
    by_well: dict[str, list[dict[str, str]]] = {}
    with _OPS_LOG_PATH.open(newline="") as handle:
        for row in csv.DictReader(handle):
            by_well.setdefault(row["series_id"], []).append(row)
    for rows in by_well.values():
        rows.sort(key=lambda r: r["timestamp"])
    return by_well


_BY_WELL: dict[str, list[dict[str, str]]] = _load()


def _to_entry(
    raw: dict[str, str], *, still_active: bool, minutes_ago: float
) -> OpsLogEntry:
    return OpsLogEntry(
        timestamp=raw["timestamp"],
        event_type=raw["event_type"],
        detail=raw["detail"],
        duration_min=float(raw["duration_min"]),
        minutes_ago=round(minutes_ago, 2),
        still_active=still_active,
    )


class OpsLogResult:
    """The three lists an ops-log query returns, kept separate on purpose."""

    def __init__(
        self,
        entries: list[OpsLogEntry],
        explanatory: list[OpsLogEntry],
        stale_explanatory: list[OpsLogEntry],
    ) -> None:
        self.entries = entries
        self.explanatory = explanatory
        self.stale_explanatory = stale_explanatory


def get_ops_log(
    well: str,
    as_of: str | None = None,
    lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
) -> OpsLogResult:
    """Log entries for a well as of a moment.

    Returns explanatory (still-active pump_rate_change/mud_transfer) and stale
    explanatory (same types, finished before as_of) separately from the raw
    entries. The lookback stays wider than the scoring window on purpose so an
    operation already under way is visible; duration is never inferred from the
    event type.
    """
    validate_well(well)
    resolved_as_of = as_of if as_of is not None else latest_timestamp(well)
    as_of_dt = parse_timestamp(resolved_as_of)
    window_start = as_of_dt - timedelta(minutes=lookback_minutes)

    entries: list[OpsLogEntry] = []
    explanatory: list[OpsLogEntry] = []
    stale_explanatory: list[OpsLogEntry] = []

    for raw in _BY_WELL.get(well, []):
        entry_start = parse_timestamp(raw["timestamp"])
        if entry_start > as_of_dt or entry_start < window_start:
            continue

        duration_min = float(raw["duration_min"])
        entry_end = entry_start + timedelta(minutes=duration_min)
        # Instant entries carry duration 0 and are never active.
        still_active = duration_min > 0 and entry_start <= as_of_dt <= entry_end
        minutes_ago = (as_of_dt - entry_start).total_seconds() / 60.0

        entry = _to_entry(raw, still_active=still_active, minutes_ago=minutes_ago)
        entries.append(entry)

        if raw["event_type"] in EXPLANATORY_EVENT_TYPES:
            if still_active:
                explanatory.append(entry)
            else:
                stale_explanatory.append(entry)

    return OpsLogResult(entries, explanatory, stale_explanatory)
