// Read the newest get_fleet_status tool result out of the chat event stream.
//
// The build is stateless and there is no REST fallback: panels read tool results
// out of the chat event stream. We walk events newest-first for a tool-invocation
// part whose toolName is get_fleet_status and whose state is "result". The
// LangGraph adapter emits only TextMessage/ToolCall/Reasoning - there is no
// CustomEvent or StateSnapshot to listen for.

import { isToolInvocationPart, type ChatStateEvent } from '@/components/block/chat/types';

export interface FleetWell {
  well: string;
  as_of: string;
  probability: number;
  well_event: boolean;
  incident: string | null;
  state: string;
  delta_flow_gpm: number;
  pit_rate_bbl_per_min: number;
  spp_psi: number;
  gas_units: number;
  latitude: number;
  longitude: number;
}

export interface FleetSnapshot {
  as_of: string;
  wells: FleetWell[];
}

const FLEET_TOOL_NAME = 'get_fleet_status';

function parseFleetResult(raw: unknown): FleetSnapshot | null {
  let parsed: unknown = raw;
  if (typeof raw === 'string') {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (!parsed || typeof parsed !== 'object') {
    return null;
  }
  const fleet = (parsed as { fleet?: unknown }).fleet;
  if (!Array.isArray(fleet) || fleet.length === 0) {
    return null;
  }
  const wells = fleet.filter(
    (w): w is FleetWell => !!w && typeof w === 'object' && 'well' in w && 'state' in w
  );
  if (wells.length === 0) {
    return null;
  }
  return { as_of: wells[0].as_of, wells };
}

/**
 * Return the most recent fleet snapshot found in the event stream, or null.
 * Walks messages newest-first and, within a message, parts newest-first, so the
 * latest get_fleet_status result wins.
 */
export function extractLatestFleet(events: ChatStateEvent[]): FleetSnapshot | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i];
    if (event.type !== 'message') {
      continue;
    }
    const parts = event.value.content?.parts ?? [];
    for (let j = parts.length - 1; j >= 0; j -= 1) {
      const part = parts[j];
      if (!isToolInvocationPart(part)) {
        continue;
      }
      const invocation = part.toolInvocation;
      if (invocation.toolName !== FLEET_TOOL_NAME || invocation.state !== 'result') {
        continue;
      }
      const snapshot = parseFleetResult(invocation.result);
      if (snapshot) {
        return snapshot;
      }
    }
  }
  return null;
}
