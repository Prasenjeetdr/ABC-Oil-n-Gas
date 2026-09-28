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
"""Serverless scoring against the deployed drilling classifier.

The classifier answers one physics question: is the wellbore exchanging fluid
with the formation? It is scored on the MANAGEMENT endpoint with a bearer token
and nothing else - there is no prediction-server host, no /predApi/v1.0 path and
no DataRobot-Key header on this tenant. The verdict is never computed locally;
if the deployment id is unset, scoring fails loudly.
"""

import csv
import io
import time
from typing import Sequence

import requests

from agent.drilling.state import TelemetryRow
from agent.drilling.telemetry import WINDOW_ROWS

# Model inputs only. gas_units, flow_out_gpm and pit_volume_bbl are in the data
# and used by the agent and UI, but are NOT model inputs. well_event and condition
# are labels; well_event is still written into the payload (see below) but is never
# evidence for the agent.
MODEL_FEATURES: tuple[str, ...] = (
    "flow_in_gpm",
    "delta_flow_gpm",
    "spp_psi",
    "pit_rate_bbl_per_min",
)
SERIES_ID_COLUMN: str = "series_id"
TIMESTAMP_COLUMN: str = "timestamp"
TARGET_COLUMN: str = "well_event"

POSITIVE_CLASS_LABEL: float = 1.0

_COLD_START_RETRIES: int = 40
_COLD_START_BACKOFF_SECONDS: float = 5.0
_REQUEST_TIMEOUT_SECONDS: float = 60.0


class ScoringError(RuntimeError):
    """Raised when the deployment cannot be scored or the response is malformed."""


def extract_probability(response_json: object) -> float:
    """P(well_event = 1) for the scored row. Passes mypy --strict, no cast."""
    if not isinstance(response_json, dict):
        raise ScoringError(f"unexpected response: {response_json!r}")
    rows = response_json.get("data")
    if not isinstance(rows, list) or not rows:
        raise ScoringError(f"no predictions returned: {response_json!r}")
    row = rows[-1]
    if not isinstance(row, dict):
        raise ScoringError(f"unexpected prediction row: {row!r}")
    values = row.get("predictionValues")
    if not isinstance(values, list):
        raise ScoringError(f"no predictionValues in row: {row!r}")
    for value in values:
        if not isinstance(value, dict):
            continue
        if float(value["label"]) == POSITIVE_CLASS_LABEL:
            return float(value["value"])
    raise ScoringError(f"no positive-class probability in {values!r}")


def extract_explanations(response_json: object) -> list[dict[str, object]]:
    """Prediction explanations for the scored (last) row, signed.

    Each entry is {feature, feature_value, strength, qualitative_strength};
    a negative strength argues AGAINST a well event. Returns an empty list when
    the deployment does not attach explanations to the response.
    """
    if not isinstance(response_json, dict):
        raise ScoringError(f"unexpected response: {response_json!r}")
    rows = response_json.get("data")
    if not isinstance(rows, list) or not rows:
        raise ScoringError(f"no predictions returned: {response_json!r}")
    row = rows[-1]
    if not isinstance(row, dict):
        raise ScoringError(f"unexpected prediction row: {row!r}")
    raw = row.get("predictionExplanations")
    if not isinstance(raw, list):
        return []
    explanations: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        explanations.append(
            {
                "feature": item.get("feature"),
                "feature_value": item.get("featureValue"),
                "strength": item.get("strength"),
                "qualitative_strength": item.get("qualitativeStrength"),
            }
        )
    return explanations


def _build_payload(window: Sequence[TelemetryRow]) -> str:
    """A CSV payload of exactly the window rows.

    The target column must be present. Time-series scoring picks the row to
    predict from where the target is BLANK, so history rows carry their known
    well_event value and the newest row - the one being scored - is left blank.
    """
    if len(window) != WINDOW_ROWS:
        raise ScoringError(
            f"scoring requires exactly {WINDOW_ROWS} rows, got {len(window)}; a "
            "shorter window is an unscorable request"
        )
    columns = [
        TIMESTAMP_COLUMN,
        SERIES_ID_COLUMN,
        *MODEL_FEATURES,
        TARGET_COLUMN,
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    last_index = len(window) - 1
    for index, row in enumerate(window):
        record = {
            TIMESTAMP_COLUMN: row[TIMESTAMP_COLUMN],
            SERIES_ID_COLUMN: row[SERIES_ID_COLUMN],
            **{feature: row[feature] for feature in MODEL_FEATURES},
            TARGET_COLUMN: "" if index == last_index else row[TARGET_COLUMN],
        }
        writer.writerow(record)
    return buffer.getvalue()


def _predictions_url(endpoint: str, deployment_id: str) -> str:
    base = endpoint.rstrip("/")
    return f"{base}/deployments/{deployment_id}/predictions"


def score_window(
    window: Sequence[TelemetryRow],
    *,
    endpoint: str,
    api_token: str,
    deployment_id: str | None,
    max_explanations: int = 0,
) -> object:
    """POST the 25-row window to the serverless deployment and return the JSON.

    Retries a handful of times on HTTP 503 "Inference server is starting", which
    is a normal cold start rather than a failure. Fails loudly when the deployment
    id is unset - a missing verdict is never fabricated locally.
    """
    if not deployment_id:
        raise ScoringError(
            "DEPLOYMENT_DRILLING_CLASSIFIER is not set; refusing to compute a "
            "verdict locally. This is a broken session, not an unscorable request."
        )
    if not api_token:
        raise ScoringError("DATAROBOT_API_TOKEN is not set; cannot score.")

    url = _predictions_url(endpoint, deployment_id)
    headers = {
        "Content-Type": "text/csv; charset=UTF-8",
        "Authorization": f"Bearer {api_token}",
    }
    params: dict[str, str] = {}
    if max_explanations > 0:
        params["maxExplanations"] = str(max_explanations)

    payload = _build_payload(window).encode("utf-8")

    last_error: str = ""
    for attempt in range(_COLD_START_RETRIES):
        response = requests.post(
            url,
            headers=headers,
            params=params,
            data=payload,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 503:
            last_error = response.text
            time.sleep(_COLD_START_BACKOFF_SECONDS)
            continue
        if response.status_code >= 400:
            raise ScoringError(
                f"scoring failed with HTTP {response.status_code}: {response.text}"
            )
        return response.json()

    raise ScoringError(
        f"deployment did not become ready after {_COLD_START_RETRIES} attempts; "
        f"last response: {last_error}"
    )
