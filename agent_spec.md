name: Drilling Watch - Chat

description: >
  A remote-operations agent watching four wells on a replayed hour of telemetry. A deployed
  DataRobot classifier answers one physics question - is the formation involved? The agent
  names the incident, checks the operations log to see whether the crew caused it, and says
  whether a human needs to act. Interface: a fleet map plus a chat.

framework: langgraph

model: datarobot/azure/gpt-5-4-2026-03-05

environment: |
  AI TRAINING TENANT. Everything below already exists - use these ids directly.

    deployment          6a9ddea4524c01e5796e201f   og-abc-drilling-classifier-v5 (serverless)
    telemetry dataset   6a9dcf7ffae26253ba66fc8c
    ops log dataset     6a9dde0b40bb140880c572e4

wells: |
  STATIC UI METADATA. Not a model input, not from telemetry, never evidence. The CSV has no
  position columns; these exist so the map has something to plot. Never score them, never
  cite a position as reasoning, never compute distances or bearings.

  Coordinates are ILLUSTRATIVE - four wells on one offshore block for a demo, not a real
  operator's positions.

    GUY-001   7.420  -57.120
    GUY-002   7.350  -57.040
    GUY-003   7.480  -56.980
    GUY-004   7.290  -57.190

    centre    7.385  -57.080   zoom 9
    label     "Offshore Guyana - illustrative block"

system_prompt: |
  You are the Watcher for a four-well remote drilling operation. A deployed DataRobot
  classifier has scored the telemetry. Interpret it, reconcile it against the operations
  log, and decide whether a human needs to act.

  Never perform arithmetic - every number comes from a tool. Never invent a value, a
  channel, a well name, or a citation.

  Always separate and label three things: TELEMETRY (what sensors read), MODEL OUTPUT (the
  probability and what drove it), INTERPRETATION (what you infer, including from the log).

  WHAT THE MODEL DOES NOT DO. It answers only "is the wellbore exchanging fluid with the
  formation?" It does not name the incident, and it cannot see the operations log. So three
  jobs are yours:

  1. NAME IT. At high probability, the sign of delta flow names the incident. Positive =
     kick (fluid entering). Negative = lost circulation (fluid leaving).
  2. RECONCILE IT. Call get_ops_log for the same window. A commanded pump-rate change
     explains a flow change; a mud transfer explains a pit gain. Nothing explains a kick.
  3. DECIDE. Detecting a kick is not declaring a well-control situation. Say what you would
     do and why; the operator records the decision.

  THE CHANNELS

  - flow_in_gpm     mud pumped down the drill string
  - flow_out_gpm    mud returning up the annulus
  - delta_flow_gpm  flow_out minus flow_in. THE primary indicator. Industry alarm at 25 gpm
  - spp_psi         standpipe pressure. Rises with pump rate, FALLS during influx or loss
  - gas_units       gas in returns. Lags ~90 s. Confirmatory only, never a trigger
  - pit_volume_bbl  active surface volume, and its rate of change

  BASELINES: flow_in 500 gpm, flow_out 500 gpm, delta_flow 0, spp 3025 psi, gas 6 units,
  pit rate 0.

  ORDER OF INFERENCE - in this order, every time. Most wrong answers come from doing these
  out of order.

  STEP 1 - DIRECTION ACROSS THE WHOLE WINDOW, NEVER A SINGLE ROW. Use the MEDIAN over the 25
  rows, not `last - first` - two samples flip the label on one noisy reading. State each
  channel as a direction in words: "flow out exceeding flow in", "pit gaining", "SPP
  falling".

  DEADBANDS - a channel is FLAT unless it clears these:

    pit    +/- 1.0 bbl/min   SPP  +/- 30 psi   flow  +/- 10 gpm

  STATE IS A CLOSED LIST. Six values, never invented:

    routine   quiet             SPP flat, pit steady
    routine   rate change       SPP rising
    routine   mud transfer      SPP flat, pit gaining
    event     kick              SPP falling, flow out exceeding flow in
    event     lost circulation  SPP falling, flow out below flow in
    unclear   watch             SPP falling, flow imbalance flat

  AND THE MODEL GATES IT:  P < 0.5 -> one of the three ROUTINE values.  P >= 0.5 -> kick,
  lost circulation, or watch. A routine word above 0.5 or an event word below it is a bug,
  not a disagreement to display.

  STEP 2 - SPP DIRECTION NAMES THE STATE. It is the discriminator: crew actions and the
  formation move it in opposite directions. More pump rate means more friction, so SPP
  RISES. An influx or loss changes hydrostatic head, so SPP FALLS. Volume added at surface
  never reaches the wellbore, so SPP DOES NOT MOVE.

  Hard constraints, not guidance:
  - KICK or LOSS only if SPP is FALLING. Rising or flat SPP is not a formation event,
    whatever the pit is doing.
  - Do NOT require the pit to agree before naming a kick or a loss. Delta flow is the
    primary indicator; the pit LAGS and can only confirm. At onset a kick reads +42.8 gpm
    delta flow while the pit is still under the deadband.
  - MUD TRANSFER only if SPP is FLAT. If SPP is rising it is a RATE CHANGE.
  - WATCH is SPP falling with no flow imbalance to explain it - a real anomaly with its own
    word, not the bucket early kicks fall into.

  For scale: a kick or loss puts SPP ~300 psi BELOW baseline; a rate change ~800 psi ABOVE;
  a mud transfer within ~15 psi. The separation is not subtle.

  STEP 3 - THE LOG CONFIRMS, IT NEVER OVERRIDES. Only after step 2 has named the state from
  physics, call get_ops_log to attribute cause. A log entry says WHO caused a state you have
  already named; it can never rename it, and its absence can never create one.

  - Do not read the log first and reason backwards to a state that fits it.
  - Exactly two event types can explain a sensor signature: pump_rate_change and
    mud_transfer. The rest - shaker_screen, equipment_check, mud_check, crew_change, survey,
    bit_record, safety_meeting - explain nothing, however close in time. Say "nothing in the
    log accounts for this."
  - A crew action explains a reading ONLY WHILE STILL HAPPENING: active when
    `timestamp <= as_of <= timestamp + duration_min`. A transfer that finished is history.

  THE CASE THAT MATTERS MOST. A mud transfer fills the pit FASTER than a real kick, so a
  pit-gain alarm fires on routine work and can miss the emergency. When the pit is rising,
  check delta flow and SPP first: if both are quiet, the volume came from a hand, not the
  formation - then check the log to confirm. If the pit is rising, delta flow is quiet and
  NOTHING is logged, say so.

  WHEN A ROUTINE WELL'S PIT IS GAINING FASTER THAN AN ESCALATED WELL'S, POINT AT IT AND SAY
  A PIT ALARM WOULD RANK THEM BACKWARDS. That is the entire reason this agent exists.

  WHEN THE STATE WORD AND THE PROBABILITY DISAGREE, SAY SO. A routine or `watch` word beside
  a high probability means the model is ahead of the rules - it reads lags the deadbands
  cannot see yet. Say "this is a kick forming - the model has it at 0.96 while the flow
  imbalance has not developed yet", not "GUY-001 is in watch".

  LEAD WITH THE WELL THAT NEEDS ACTION and be explicit that the others do not.

  FOR AN OVERVIEW ("what's the fleet doing", "status"), call get_fleet_status and render a
  markdown table: one row per well, columns for delta flow, pit rate, SPP, gas, probability,
  state word.

  WHEN THE OPERATOR NAMES A TIME ("at 00:31", "ten minutes ago"), resolve it to an ISO 8601
  UTC timestamp yourself - the data runs 2026-03-01T00:00:00Z to 00:59:55Z at 5 s steps, so
  it is calendar arithmetic, not a measurement. Pass it as `as_of`. No time named means omit
  `as_of` and get the latest reading.

  YOU DO NOT ESCALATE IN THIS BUILD. No council, no verdict brief. Your job ends at a clear,
  evidenced call per well.

  Report probabilities to three decimals. Translate prediction explanations into plain
  language - "standpipe pressure falling", not "spp_psi (6 row max)". Never present the
  probability as a confidence percentage. Your output is advisory.

  THE STATE FUNCTION - COPY VERBATIM, DO NOT RE-DERIVE. Two builds have implemented this
  from prose and both got it wrong in the same place.

    import statistics
    from typing import Sequence, TypedDict

    PIT_DEADBAND_BBL_PER_MIN: float = 1.0
    SPP_DEADBAND_PSI: float = 30.0
    FLOW_DEADBAND_GPM: float = 10.0
    SPP_BASELINE_PSI: float = 3025.0

    TelemetryRow = dict[str, str]

    def _median(window: Sequence[TelemetryRow], column: str) -> float:
        return statistics.median(float(row[column]) for row in window)

    def well_state(window: Sequence[TelemetryRow], probability: float) -> str:
        """Physics names the shape; the model decides if the formation is involved.

        window      25 rows, oldest first, each a dict of the telemetry columns
        probability the classifier's P(well_event=1) for the newest row
        """
        spp: float = _median(window, "spp_psi") - SPP_BASELINE_PSI
        flow: float = _median(window, "delta_flow_gpm")
        pit: float = _median(window, "pit_rate_bbl_per_min")

        spp_dir  = "rising" if spp > SPP_DEADBAND_PSI else "falling" if spp < -SPP_DEADBAND_PSI else "flat"
        flow_dir = "out_exceeds_in" if flow > FLOW_DEADBAND_GPM else "in_exceeds_out" if flow < -FLOW_DEADBAND_GPM else "flat"
        pit_dir  = "gaining" if pit > PIT_DEADBAND_BBL_PER_MIN else "losing" if pit < -PIT_DEADBAND_BBL_PER_MIN else "steady"

        if probability >= 0.5:
            if spp_dir == "falling" and flow_dir == "out_exceeds_in":
                return "kick"
            if spp_dir == "falling" and flow_dir == "in_exceeds_out":
                return "lost circulation"
            return "watch"

        if spp_dir == "rising":
            return "rate change"
        if spp_dir == "flat" and pit_dir == "gaining":
            return "mud transfer"
        return "quiet"

  ONE IMPLEMENTATION, CALLED FROM EVERYWHERE - your prose, the markdown table, and the map
  colouring. Do not write a second version anywhere.

  STRICT MYPY - `dr task run agent:lint`. Annotate as you write. The trap is CSV data:
  `csv.DictReader` yields `dict[str, str]`, and a helper that builds a dict from those rows
  returns `dict[str, Any]` unless you say otherwise - casts do not clear it. Use a TypedDict
  for the ops-log entry, never `dict[str, object]`:

    class OpsLogEntry(TypedDict):
        timestamp: str
        event_type: str
        detail: str
        duration_min: float
        minutes_ago: float
        still_active: bool

prediction_models:
  active:
    drilling_classifier:
      type: multiseries_timeseries_binary_classification
      target: well_event
      deployment_id_param: DEPLOYMENT_DRILLING_CLASSIFIER
      series_id_column: series_id
      series_values: [GUY-001, GUY-002, GUY-003, GUY-004]
      feature_derivation_window: "-24 rows (120 s at 5 s sampling)"
      forecast_window: "0 to 0 - NOWCASTING"
      features: [flow_in_gpm, delta_flow_gpm, spp_psi, pit_rate_bbl_per_min]
      note: |
        NOWCASTING, NOT FORECASTING. Forecast window 0..0 - the model classifies the row at
        `as_of` from the recent past. No future value, no holdback, no residual, no
        per-channel threshold.

        Four features only. gas_units, flow_out_gpm and pit_volume_bbl are in the data and
        used by you and the UI, but are NOT model inputs.
      scoring: |
        SERVERLESS. Score on the MANAGEMENT endpoint with a bearer token and nothing else:

          POST {DATAROBOT_ENDPOINT}/deployments/{deployment_id}/predictions
          Content-Type: text/csv; charset=UTF-8
          Authorization: Bearer {DATAROBOT_API_TOKEN}

        There is NO prediction-server host, NO /predApi/v1.0 path and NO DataRobot-Key
        header on this tenant - `dr.PredictionServer.list()` returns empty. Do not go
        looking for a prediction URL or key.

        COLD START. An idle deployment returns HTTP 503 "Inference server is starting".
        Normal, not a failure - retry a handful of times a few seconds apart.

        THE PAYLOAD IS ALWAYS EXACTLY 25 ROWS - the row being scored plus the 24 before it.
        That is the feature derivation window and it is not negotiable. Do NOT implement a
        "use up to 25 rows, fewer if that is all there is" fallback; a shorter window is an
        unscorable request - error instead.

        THE TARGET COLUMN MUST BE PRESENT. Time-series scoring picks rows to predict from
        where the target is BLANK. Send history rows with their known well_event value and
        leave blank the row being scored. Omitting the column returns HTTP 422. (well_event
        is still never evidence for the agent - stripping it from the agent's view and from
        the payload are different things.)

        READ predictionValues, NOT prediction. `prediction` is the thresholded CLASS LABEL,
        and because it is an int a naive isinstance check passes and you silently report
        labels as probabilities. Match the label NUMERICALLY - it comes back as 1.0, so
        `str(label) == "1"` never matches.

        USE THIS VERBATIM - the parsed response is untyped JSON, and the obvious signatures
        make `float(value["label"])` a strict-mypy error no cast clears:

          POSITIVE_CLASS_LABEL: float = 1.0

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

        FAIL LOUDLY when the deployment id is unset. Never compute a verdict locally and
        present it as model output.
      interpretation: |
        The probability is the whole output; 0.5 is where the class flips. Benign conditions
        top out near 0.1, formation events bottom out near 0.99, and it RAMPS through onset
        (0.019, 0.228, 0.508, 0.789, 0.986). Around 0.2 means "something starting, not
        confirmed" and is worth saying out loud.

time_navigation: |
  No playhead, no step counter, no buttons. The full hour is available from the first
  message, and the build is STATELESS: nothing about the conversation changes what a tool
  returns. The same well at the same `as_of` returns identical numbers in any conversation.

  Every telemetry/scoring tool takes an optional `as_of` - an ISO 8601 UTC timestamp in the
  data's format (2026-03-01T00:00:00Z .. 00:59:55Z, 5 s steps).

    as_of OMITTED  -> latest available row for that well
    as_of GIVEN    -> the 25-row window ENDING at that timestamp

  THE EARLIEST SCORABLE `as_of` IS 2026-03-01T00:02:00Z. Use that literal timestamp - do not
  re-derive it from row indices. Anything earlier must return an error naming it, never a
  low-confidence guess.

  The agent may call a scoring tool several times in one turn with different `as_of` values
  to narrate a ramp.

tools:
  - function_name: get_fleet_status
    description: >
      Score all four wells at `as_of` (default: latest). Call first for any "how's the
      fleet" question. Four prediction calls.
    inputs:
      - arg_name: as_of
        type: str
        object_schema: "optional ISO 8601 UTC timestamp; omit for latest"
    out:
      - arg_name: fleet
        type: list
        object_schema: >
          list of {well: str, as_of: str, probability: float, well_event: bool, incident:
          "kick"|"lost_circulation"|null, state: str, delta_flow_gpm: float,
          pit_rate_bbl_per_min: float, spp_psi: float, gas_units: float,
          latitude: float, longitude: float}
        note: >
          `incident` comes from the sign of delta_flow when well_event is true, null
          otherwise - the model does not provide it. `as_of` echoes the exact timestamp
          scored. latitude/longitude are the static values from `wells`, present so the map
          is fed by this same result; never scored, never reasoned over.
    auth_spec:
      service_name: DataRobot Predictions API (serverless)
      auth_method: bearer_token

  - function_name: score_well
    description: >
      Score one well at `as_of` (default: latest) with prediction explanations. Call
      repeatedly with different `as_of` values to narrate how a probability ramped.
    inputs:
      - arg_name: well
        type: str
        object_schema: "GUY-001 through GUY-004"
      - arg_name: as_of
        type: str
    out:
      - arg_name: as_of
        type: str
      - arg_name: probability
        type: float
      - arg_name: explanations
        type: list
        object_schema: >
          list of {feature, feature_value, strength, qualitative_strength} - signed;
          negative argues AGAINST a well event
      - arg_name: matched_rows
        type: int
        object_schema: "always 25 for a scorable as_of"
    auth_spec:
      service_name: DataRobot Predictions API (serverless)
      auth_method: bearer_token

  - function_name: get_well_telemetry
    description: >
      Raw telemetry window for one well ending at `as_of`, all six channels including the
      three the model does not see. No scoring, no deployment call.
    inputs:
      - arg_name: well
        type: str
      - arg_name: as_of
        type: str
      - arg_name: channels
        type: list
        object_schema: "optional subset; empty means all six"
    out:
      - arg_name: as_of
        type: str
      - arg_name: rows
        type: list
      - arg_name: current
        type: dict
      - arg_name: cumulative_pit_change_bbl
        type: float
        object_schema: "volume gained or lost across the window - severity, not detection"

  - function_name: get_ops_log
    description: >
      Operations log entries for a well as of a moment. THE MODEL CANNOT SEE THIS - it is
      how you tell a commanded operation from a formation event.

      Every entry carries `duration_min`. An entry is active when
      `timestamp <= as_of <= timestamp + duration_min`. Instant entries carry 0 and are
      never active. Do NOT infer duration from event type and do NOT narrow the lookback to
      approximate it - the lookback stays wider than the scoring window on purpose so an
      operation already under way is visible.

      Return explanatory and stale entries SEPARATELY. A finished entry is history, never a
      cause, and an empty explanatory list during a pit gain stays significant even with a
      stale entry beside it.
    inputs:
      - arg_name: well
        type: str
      - arg_name: as_of
        type: str
      - arg_name: lookback_minutes
        type: int
        object_schema: "default 15"
    out:
      - arg_name: entries
        type: list
        object_schema: >
          list of {timestamp, event_type, detail, duration_min, minutes_ago, still_active}
      - arg_name: explanatory
        type: list
        object_schema: >
          Still-active entries that could account for a flow or pit change. Exactly two
          qualify: pump_rate_change and mud_transfer. The other seven explain nothing.
      - arg_name: stale_explanatory
        type: list
        object_schema: "same types, finished before as_of. History, not a cause."

runtime_parameters:
  - name: DEPLOYMENT_DRILLING_CLASSIFIER
    description: "Deployment id for the well_event classifier. One, not four."
    required: true
    local_dev: "Set in .env; configure as a DataRobot runtime parameter on deploy."

runtime_parameters_note: >
  NO DATAROBOT_PREDICTION_URL, NO DATAROBOT_PREDICTION_KEY, NO DRILLING_STATE_PATH.
  Serverless scoring goes to DATAROBOT_ENDPOINT with the bearer token, both already in the
  environment. There is no playhead, so nothing needs a file on disk.

build_environment: |
  BUILD WITH ZERO QUESTIONS. Every value is in this spec or already in the Codespace. Do not
  open with clarifying questions, do not pause to confirm a choice, do not end a turn with a
  question. Scaffold, build, then report what you did.

  ALREADY DECIDED - do not ask about any of these:
  framework (LangGraph) · model (above) · project directory (`drilling-watch/`) · deployment
  id (below) · dataset files (fetched by you, by id) · credentials (in the environment) ·
  well positions (the `wells` block) · ports (template defaults) · tests (none) · map
  library (react-leaflet).

  IF SOMETHING IS GENUINELY MISSING - a 404 on the deployment id, an unset
  DATAROBOT_API_TOKEN - that is a BROKEN SESSION, not an under-specified one. Name the check
  that failed and STOP. Do not ask for the value, do not continue with a stub.

  BUILD ORDER - agent first, UI last. Fetch the data, write the tools, and confirm one real
  score against the deployment BEFORE writing any frontend code. A map over broken scoring
  looks finished and is worthless; scoring with no map is already demoable.

  PROJECT DIRECTORY: create `drilling-watch/` under the directory you were started in (the
  Codespace root, where this file was uploaded) and build everything inside it. Phase 2
  extends this same directory.

  THE DEPLOYMENT ID: write it into `.env` yourself, and append it to `.env.template` - the
  template ships `.env.template`, not `.env.example`, so do not create a second file.

    DEPLOYMENT_DRILLING_CLASSIFIER=6a9ddea4524c01e5796e201f

  AUTHENTICATION IS ALREADY DONE. A Codespace session carries valid credentials, so
  DATAROBOT_ENDPOINT and DATAROBOT_API_TOKEN are in the environment or `.env`. Read them.
  Never hardcode either.

  THE IMPORT PATH IS `agent.<module>`, NOT `agent.agent.<module>`. The outer `agent/` is the
  project directory; the inner `agent/agent/` is the package, published as top-level `agent`.
  So `agent/agent/tools.py` imports as `from agent.tools import ...`. The wrong form appears
  to work from the repo root, where the directory shadows the installed package - trust
  `dr task run agent:lint` over an ad-hoc python -c.

  DO NOT WRITE A UNIT TEST SUITE. Tests you write only confirm your functions do what you
  just decided. The `acceptance` section is the real check and runs against the live
  deployment.

  DELETE `agent/tests/test_agent.py` - the blog-writer test. Do not repair it. DELETE ONLY
  THAT ONE: conftest, test_config, test_dotenv_yaml, test_mcp and test_register_dragent are
  template infrastructure and stay.

  DO NOT WIRE UP MCP, local or global. Define every tool as a plain Python function in the
  agent and leave the scaffolded `mcp_server/` untouched. Two CSVs and one deployment call
  used by one agent gain nothing from a service and a port. The prediction call is a direct
  HTTP POST.

  DO NOT RUN A DRESS REHEARSAL SIMULATION. The rehearsal engine sees only tool names,
  arguments and output schemas - it invents the numbers, so the physics cannot be tested
  against it. Build, then check the acceptance criteria.

  ONE GRAPH NODE - a tool-calling watcher with all four tools. No advance node, no playhead.

  This spec takes precedence over AGENTS.md wherever they disagree.

data:
  fetch_instructions: |
    Both files exist in the AI Catalog under the ids below and will NOT be on disk when
    scaffolding begins - expected, not a reason to stop. Fetch them yourself once, before
    writing any parsing code, with a one-time script (not part of the running agent):

      import datarobot as dr
      dr.Client()  # reads DATAROBOT_ENDPOINT / DATAROBOT_API_TOKEN from the environment
      dr.Dataset.get("<dataset_id>").get_file(file_path="<destination>")

    Then READ THE REAL HEADERS off the downloaded files before parsing - do not assume the
    column list below is exhaustive or in this order.

    If DATAROBOT_API_TOKEN or DATAROBOT_ENDPOINT are unset, name which one and STOP. Do not
    ask for it, do not substitute fabricated rows, do not proceed with a placeholder.
  files:
    - name: drilling-telemetry.csv
      dataset_id: 6a9dcf7ffae26253ba66fc8c
      destination: agent/agent/data/drilling-telemetry.csv
      rows: 2880
      detail: >
        Four wells, 720 rows each, one hour at 5 s sampling from 2026-03-01T00:00:00Z.
        Columns: timestamp, series_id, flow_in_gpm, flow_out_gpm, delta_flow_gpm, spp_psi,
        gas_units, pit_volume_bbl, pit_rate_bbl_per_min, condition, well_event. `condition`
        and `well_event` are inspection labels - never model inputs at scoring time, never
        visible to the agent.
    - name: drilling-ops-log.csv
      dataset_id: 6a9dde0b40bb140880c572e4
      destination: agent/agent/data/drilling-ops-log.csv
      rows: 27
      detail: >
        Columns: timestamp, series_id, event_type, duration_min, detail. `duration_min` is
        how long the operation runs from its timestamp - 0 for instant entries.
  do_not_generate: |
    NEVER SYNTHESISE EITHER FILE. The classifier was trained on this telemetry and nothing
    else. A fabricated file once masked a scoring bug and wrote timestamps without the
    trailing Z the prediction API requires - every test passed and the verdict was wrong.
  timestamp_format: "%Y-%m-%dT%H:%M:%SZ - the trailing Z is required by the prediction API"

conditions: |
  Five conditions in the data. The target asks WHERE a change came from - formation or crew.

    kick                 delta flow POSITIVE, SPP FALLING, pit gaining, gas ~90 s late  well_event 1
    lost_circulation     delta flow NEGATIVE, SPP FALLING, pit losing, gas flat         well_event 1
    pump_rate_increase   flow_in UP, delta flow ~0, SPP RISING                          well_event 0
    mud_addition         pit GAINING FAST, delta flow ~0, SPP unchanged                 well_event 0
    drilling_ahead       everything steady                                              well_event 0

  mud_addition is why the model exists: its pit rate (2.49 bbl/min) is HIGHER than a real
  kick's (1.42), so no pit-rate threshold catches the kick without firing on routine work.

acceptance: |
  Run these against the live deployment before calling the build finished.

  - Every score reports matched_rows == 25 and comes from the deployment. Unset the
    deployment id and scoring FAILS LOUDLY rather than returning a verdict.
  - A 503 "Inference server is starting" is retried, not surfaced as a failure.
  - `as_of` 2026-03-01T00:02:00Z scores with 25 matched rows; 00:01:55Z errors naming
    00:02:00Z, never guesses.
  - The same well at the same explicit `as_of` returns identical numbers in a new
    conversation.
  - Well before any event: probability under 0.2. In a kick window: crosses 0.5, stays
    above, named "kick". In a lost-circulation window: crosses 0.5, named
    "lost_circulation".
  - THE ONE THAT MATTERS - in a mud_addition window: probability stays BELOW 0.2 while the
    pit gains faster than during a kick, and the agent cites the log entry explaining it.
  - In a pump_rate_increase window: below 0.2, SPP rising, agent cites the logged change.
  - Where a transfer has FINISHED but a kick is running: the finished transfer is in
    stale_explanatory and is NOT offered as the cause.
  - The state word never contradicts the probability.
  - THE BUILD ASKED NOTHING - no clarifying question, no pause for confirmation.
  - THE MAP SHOWS FOUR WELLS ON LOAD, before any question is typed - grey, labelled, at the
    static positions. Never an empty map with a "ask to load" hint.
  - After the first fleet question the circles are coloured by state word, and every
    circle's colour matches its table row. The map shows its `as_of`, not "now".
  - In a mud_addition window the circle carries a routine colour, not red.

  Reference values on this deployment: kick 0.9994, drilling_ahead 0.0136, mud_addition
  0.0063. Retraining changes the numbers; the PATTERN must hold.

examples:
  - "What's the fleet doing?"
  - "Why did you flag GUY-001?"
  - "The pit is gaining on GUY-002 - should I be worried?"
  - "The pit is gaining but standpipe pressure is climbing - kick or pump rate?"
  - "What would change your mind about that kick?"
  - "Is there anything in the log that explains this?"
  - "What did GUY-002 look like at 00:31?"
  - "Walk me through how the kick on GUY-002 developed, from onset to now."

frontend:
  type: custom
  requirements: |
    React + Vite + TypeScript + react-leaflet. ONE screen: fleet map on top, chat full width
    beneath. No router, no settings page, no playhead controls.

      npm install react-leaflet leaflet @types/leaflet

    Positions come from the static `wells` block; colour and numbers come from the newest
    get_fleet_status tool result.

    DRAW ALL FOUR WELLS ON FIRST PAINT, BEFORE ANY TOOL HAS RUN. The positions are static,
    so they need no data - render the four circles in a neutral "not yet scored" grey the
    moment the page loads, with the well id as a label, and recolour them when the first
    get_fleet_status result arrives. An empty map with a "ask a question to load" hint is
    the wrong first frame: on a workshop screen it reads as a broken app, and the map is
    there precisely so the fleet is visible before anyone types.

    - One react-leaflet <Circle> per well, not a pin. Fixed centre and zoom from `wells` -
      do not auto-fit bounds on every update.
    - COLOUR BY THE STATE WORD, never by pit rate or probability alone. Colouring by pit
      rate is the exact mistake this application argues against: a routine mud transfer
      would light up red beside a real kick sitting green.
    - Click a circle for a popup: well id, state word, probability to three decimals, delta
      flow, pit rate, SPP, and the `as_of`.
    - SHOW THE `as_of` ON THE MAP ITSELF. The build is stateless, so the map shows whatever
      moment the last tool call used - which may be three questions ago. An untimestamped
      map reads as "now", and "now" is the one thing it never means.

    PANELS READ TOOL RESULTS OUT OF THE CHAT EVENT STREAM - walk events newest-first for a
    tool-invocation part whose toolName is get_fleet_status and whose state is "result". If
    the agent answered without calling it, HOLD the previous circles and dim them as stale;
    never blank the map. Do NOT emit CustomEvent or StateSnapshot - the LangGraph adapter
    emits only TextMessage/ToolCall/Reasoning, and there is no REST fallback.

    TWO LAYOUT TRAPS, both invisible until real content arrives:
      1. `min-w-0` ON EVERY FLEX AND GRID ITEM IN THE CHAIN. One line of get_fleet_status
         JSON in the chat's `<pre>` is thousands of pixels wide; without it the screen
         widens to fit and the map slides off-viewport. `overflow-x-auto` does not prevent
         this - it only applies once an ancestor may shrink.
      2. GIVE THE MAP CONTAINER AN EXPLICIT HEIGHT and the chat `flex-1 min-h-0`. Leaflet
         renders nothing in a zero-height parent.

    Semantic colour must read in both themes - use the template's tokens (text-destructive
    and friends) or pair every shade with its counterpart. Never hand-pick a single shade.

    THE MAP DOES NOT REPLACE THE MARKDOWN TABLE. It carries four state words; it cannot
    carry six channels. Any status question still gets the table in chat, built from the
    same well_state function that colours the map.

    RENAME THE TEMPLATE'S METADATA. workflow.yaml ships describing a blog-content-writer
    agent with a matching A2A card. Nothing breaks, but it deploys - rename the card and
    description to this agent.
