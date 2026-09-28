// Static UI metadata for the four wells.
//
// These coordinates are ILLUSTRATIVE - four wells on one offshore block for a
// demo, not a real operator's positions. They are never scored and never reasoned
// over; they exist only so the map has something to plot.

export interface WellPosition {
  id: string;
  latitude: number;
  longitude: number;
}

export const WELL_POSITIONS: WellPosition[] = [
  { id: 'GUY-001', latitude: 7.42, longitude: -57.12 },
  { id: 'GUY-002', latitude: 7.35, longitude: -57.04 },
  { id: 'GUY-003', latitude: 7.48, longitude: -56.98 },
  { id: 'GUY-004', latitude: 7.29, longitude: -57.19 },
];

export const MAP_CENTRE: [number, number] = [7.385, -57.08];
export const MAP_ZOOM = 9;
export const MAP_LABEL = 'Offshore Guyana - illustrative block';

// Colour BY THE STATE WORD, never by pit rate or probability alone. Colouring by
// pit rate is the exact mistake this application argues against: a routine mud
// transfer would light up red beside a real kick sitting green.
//
// Each colour is chosen to read on both light and dark map tiles. `fill` and
// `stroke` are paired so a shade never stands alone.
export interface StateStyle {
  fill: string;
  stroke: string;
  label: string;
}

// The "not yet scored" neutral grey shown before any get_fleet_status result.
export const NEUTRAL_STYLE: StateStyle = {
  fill: '#9ca3af',
  stroke: '#4b5563',
  label: 'not yet scored',
};

const STATE_STYLES: Record<string, StateStyle> = {
  // Formation events - danger.
  kick: { fill: '#dc2626', stroke: '#7f1d1d', label: 'kick' },
  'lost circulation': { fill: '#dc2626', stroke: '#7f1d1d', label: 'lost circulation' },
  // Unclear - warning.
  watch: { fill: '#d97706', stroke: '#78350f', label: 'watch' },
  // Routine - calm.
  quiet: { fill: '#16a34a', stroke: '#14532d', label: 'quiet' },
  'rate change': { fill: '#2563eb', stroke: '#1e3a8a', label: 'rate change' },
  'mud transfer': { fill: '#0891b2', stroke: '#164e63', label: 'mud transfer' },
};

export function styleForState(state: string | null | undefined): StateStyle {
  if (!state) {
    return NEUTRAL_STYLE;
  }
  return STATE_STYLES[state] ?? NEUTRAL_STYLE;
}
