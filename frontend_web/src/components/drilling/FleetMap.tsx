import { useMemo } from 'react';
import { MapContainer, TileLayer, Circle, Tooltip, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { MAP_CENTRE, MAP_LABEL, MAP_ZOOM, WELL_POSITIONS, styleForState } from '@/drilling/wells';
import type { FleetSnapshot, FleetWell } from '@/drilling/fleet';

interface FleetMapProps {
  fleet: FleetSnapshot | null;
  /** True when the latest agent answer did not call get_fleet_status; hold and dim. */
  stale: boolean;
}

const CIRCLE_RADIUS_METERS = 2200;

function toThreeDecimals(value: number): string {
  return value.toFixed(3);
}

export function FleetMap({ fleet, stale }: FleetMapProps) {
  const byWell = useMemo(() => {
    const map = new Map<string, FleetWell>();
    fleet?.wells.forEach(w => map.set(w.well, w));
    return map;
  }, [fleet]);

  return (
    <div className="relative h-full w-full">
      <MapContainer
        center={MAP_CENTRE}
        zoom={MAP_ZOOM}
        scrollWheelZoom
        className="h-full w-full"
        style={{ background: 'var(--muted)' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {WELL_POSITIONS.map(position => {
          const well = byWell.get(position.id);
          const style = styleForState(well?.state);
          return (
            <Circle
              key={position.id}
              center={[position.latitude, position.longitude]}
              radius={CIRCLE_RADIUS_METERS}
              pathOptions={{
                color: style.stroke,
                fillColor: style.fill,
                fillOpacity: stale ? 0.25 : 0.6,
                opacity: stale ? 0.4 : 0.9,
                weight: 2,
              }}
            >
              <Tooltip permanent direction="top" offset={[0, -6]}>
                <span className="font-semibold">{position.id}</span>
              </Tooltip>
              <Popup>
                <div className="space-y-0.5 text-xs">
                  <div className="text-sm font-semibold">{position.id}</div>
                  {well ? (
                    <>
                      <div>
                        State: <span className="font-medium">{well.state}</span>
                      </div>
                      <div>Probability: {toThreeDecimals(well.probability)}</div>
                      <div>Delta flow: {toThreeDecimals(well.delta_flow_gpm)} gpm</div>
                      <div>Pit rate: {toThreeDecimals(well.pit_rate_bbl_per_min)} bbl/min</div>
                      <div>SPP: {toThreeDecimals(well.spp_psi)} psi</div>
                      <div>as_of: {well.as_of}</div>
                    </>
                  ) : (
                    <div>{style.label}</div>
                  )}
                </div>
              </Popup>
            </Circle>
          );
        })}
      </MapContainer>

      <div className="pointer-events-none absolute left-2 top-2 z-[1000] rounded-md bg-card/90 px-2 py-1 text-xs text-card-foreground shadow">
        <div className="font-medium">{MAP_LABEL}</div>
        <div className="text-muted-foreground">
          {fleet ? (
            <>
              as_of {fleet.as_of}
              {stale ? ' (stale - last scored moment)' : ''}
            </>
          ) : (
            'not yet scored - ask a question to score the fleet'
          )}
        </div>
      </div>
    </div>
  );
}
