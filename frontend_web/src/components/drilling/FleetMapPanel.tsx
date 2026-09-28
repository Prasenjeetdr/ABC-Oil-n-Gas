import { useContext, useMemo } from 'react';
import { ChatContext } from '@/components/block/chat/context';
import { isToolInvocationPart } from '@/components/block/chat/types';
import { extractLatestFleet } from '@/drilling/fleet';
import { FleetMap } from '@/components/drilling/FleetMap';

const FLEET_TOOL_NAME = 'get_fleet_status';

export function FleetMapPanel() {
  const { combinedEvents } = useContext(ChatContext);

  const { fleet, stale } = useMemo(() => {
    const snapshot = extractLatestFleet(combinedEvents);

    // Determine staleness: find the last user message, then check whether any
    // get_fleet_status result arrived after it. If the newest answer did not call
    // the tool, the circles are held from an earlier turn and dimmed.
    let lastUserIndex = -1;
    for (let i = combinedEvents.length - 1; i >= 0; i -= 1) {
      const event = combinedEvents[i];
      if (event.type === 'message' && event.value.role === 'user') {
        lastUserIndex = i;
        break;
      }
    }

    let fleetInLatestTurn = false;
    if (lastUserIndex >= 0) {
      for (let i = lastUserIndex; i < combinedEvents.length; i += 1) {
        const event = combinedEvents[i];
        if (event.type !== 'message') {
          continue;
        }
        const parts = event.value.content?.parts ?? [];
        if (
          parts.some(
            part =>
              isToolInvocationPart(part) &&
              part.toolInvocation.toolName === FLEET_TOOL_NAME &&
              part.toolInvocation.state === 'result'
          )
        ) {
          fleetInLatestTurn = true;
          break;
        }
      }
    }

    return { fleet: snapshot, stale: snapshot !== null && !fleetInLatestTurn };
  }, [combinedEvents]);

  return <FleetMap fleet={fleet} stale={stale} />;
}
