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
"""Static UI metadata for the four wells.

These coordinates are ILLUSTRATIVE - four wells on one offshore block for a demo,
not a real operator's positions. They are never a model input, never evidence,
never scored, and are never used to compute distances or bearings. They exist so
the fleet map has something to plot.
"""

from typing import NamedTuple


class WellPosition(NamedTuple):
    latitude: float
    longitude: float


WELL_IDS: tuple[str, ...] = ("GUY-001", "GUY-002", "GUY-003", "GUY-004")

WELL_POSITIONS: dict[str, WellPosition] = {
    "GUY-001": WellPosition(7.420, -57.120),
    "GUY-002": WellPosition(7.350, -57.040),
    "GUY-003": WellPosition(7.480, -56.980),
    "GUY-004": WellPosition(7.290, -57.190),
}

MAP_CENTRE: WellPosition = WellPosition(7.385, -57.080)
MAP_ZOOM: int = 9
MAP_LABEL: str = "Offshore Guyana - illustrative block"
