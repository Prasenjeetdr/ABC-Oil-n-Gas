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
"""Stateless access to the replayed hour of telemetry.

The full hour is available from the first message. Nothing about a conversation
changes what this module returns: the same well at the same ``as_of`` yields
identical rows every time. Timestamps are parsed and windows are sliced here so
the rest of the agent never does calendar arithmetic on raw CSV strings.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

from agent.drilling.state import TelemetryRow
from agent.drilling.wells import WELL_IDS

WINDOW_ROWS: int = 25
"""The feature derivation window: the row being scored plus the 24 before it."""

TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H:%M:%SZ"
"""The trailing Z is required by the prediction API."""

# Use this literal - do not re-derive it from row indices. Any as_of earlier than
# this cannot assemble a full 25-row window and is unscorable.
EARLIEST_SCORABLE_AS_OF: str = "2026-03-01T00:02:00Z"

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_TELEMETRY_PATH = _DATA_DIR / "drilling-telemetry.csv"

# Channels that live in the CSV and are shown to the operator and the UI.
ALL_CHANNELS: tuple[str, ...] = (
    "flow_in_gpm",
    "flow_out_gpm",
    "delta_flow_gpm",
    "spp_psi",
    "gas_units",
    "pit_volume_bbl",
    "pit_rate_bbl_per_min",
)

# Inspection labels present in the data. Never model inputs at scoring time and
# never visible to the agent. well_event is still sent in the scoring payload for
# history rows (a payload requirement), but it is stripped from anything the agent
# or UI reads.
_LABEL_COLUMNS: tuple[str, ...] = ("condition", "well_event")


class TelemetryError(ValueError):
    """Raised when a request cannot be satisfied from the telemetry data."""


def parse_timestamp(value: str) -> datetime:
    """Parse a data-format ISO 8601 UTC timestamp (with the required trailing Z)."""
    try:
        return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise TelemetryError(
            f"invalid timestamp {value!r}; expected format "
            f"{TIMESTAMP_FORMAT} (e.g. {EARLIEST_SCORABLE_AS_OF})"
        ) from exc


def _load() -> dict[str, list[TelemetryRow]]:
    if not _TELEMETRY_PATH.exists():
        raise TelemetryError(
            f"telemetry file not found at {_TELEMETRY_PATH}; the dataset must be "
            "fetched from the AI Catalog before the agent can run"
        )
    by_well: dict[str, list[TelemetryRow]] = {well: [] for well in WELL_IDS}
    with _TELEMETRY_PATH.open(newline="") as handle:
        for row in csv.DictReader(handle):
            series = row["series_id"]
            if series in by_well:
                by_well[series].append(row)
    for well, rows in by_well.items():
        rows.sort(key=lambda r: r["timestamp"])
    return by_well


_BY_WELL: dict[str, list[TelemetryRow]] = _load()

_EARLIEST_SCORABLE_DT = parse_timestamp(EARLIEST_SCORABLE_AS_OF)


def validate_well(well: str) -> str:
    if well not in _BY_WELL:
        raise TelemetryError(
            f"unknown well {well!r}; valid wells are {', '.join(WELL_IDS)}"
        )
    return well


def latest_timestamp(well: str) -> str:
    validate_well(well)
    return _BY_WELL[well][-1]["timestamp"]


def public_row(row: TelemetryRow) -> dict[str, float | str]:
    """A telemetry row with the inspection labels stripped, numerics coerced."""
    out: dict[str, float | str] = {"timestamp": row["timestamp"]}
    for channel in ALL_CHANNELS:
        out[channel] = float(row[channel])
    return out


def resolve_window(well: str, as_of: str | None) -> list[TelemetryRow]:
    """Return the 25-row window ending at ``as_of`` (or the latest 25 rows).

    Raises TelemetryError when ``as_of`` is earlier than the earliest scorable
    timestamp or otherwise cannot assemble a full window. A shorter window is an
    unscorable request - it errors rather than falling back to fewer rows.
    """
    validate_well(well)
    rows = _BY_WELL[well]

    if as_of is None:
        end_index = len(rows) - 1
    else:
        as_of_dt = parse_timestamp(as_of)
        if as_of_dt < _EARLIEST_SCORABLE_DT:
            raise TelemetryError(
                f"as_of {as_of} is before the earliest scorable timestamp "
                f"{EARLIEST_SCORABLE_AS_OF}; a full {WINDOW_ROWS}-row window cannot "
                "be assembled, so this request is unscorable"
            )
        end_index = _index_of_timestamp(rows, as_of)

    start_index = end_index - (WINDOW_ROWS - 1)
    if start_index < 0:
        raise TelemetryError(
            f"as_of {as_of} cannot assemble a full {WINDOW_ROWS}-row window"
        )
    return rows[start_index : end_index + 1]


def _index_of_timestamp(rows: list[TelemetryRow], as_of: str) -> int:
    for index, row in enumerate(rows):
        if row["timestamp"] == as_of:
            return index
    raise TelemetryError(
        f"as_of {as_of} is not a sampled timestamp; the data runs at 5 s steps "
        f"from 2026-03-01T00:00:00Z to 00:59:55Z"
    )
