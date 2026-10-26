import { useEffect } from 'react';
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet';
import type { LatLngBoundsExpression, LatLngExpression } from 'leaflet';
import { usePalette } from '../theme/chart';

export interface Track { id: string | number; points: [number, number][]; color: string; weight?: number; label?: string;
  opacity?: number }
export interface Dot { lat: number; lon: number; color: string; r?: number; label?: string }

function Fit({ bounds }: { bounds: LatLngBoundsExpression | null }) {
  const map = useMap();
  useEffect(() => { if (bounds) map.fitBounds(bounds, { padding: [16, 16] }); }, [map, bounds]);
  return null;
}

export default function MapView({ tracks = [], dots = [], height = 360, fitTo }: {
  tracks?: Track[]; dots?: Dot[]; height?: number; fitTo?: [number, number][];
}) {
  const p = usePalette();
  const all = fitTo ?? [...tracks.flatMap((t) => t.points), ...dots.map((d) => [d.lat, d.lon] as [number, number])];
  const bounds: LatLngBoundsExpression | null = all.length
    ? [[Math.min(...all.map((x) => x[0])), Math.min(...all.map((x) => x[1]))],
      [Math.max(...all.map((x) => x[0])), Math.max(...all.map((x) => x[1]))]]
    : null;
  return (
    <div className={p.dark ? 'map-dark' : 'map-light'}>
    <MapContainer style={{ height, width: '100%' }} center={[19.07, 72.86]} zoom={11} scrollWheelZoom={false}>
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19}
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
      {tracks.map((t) => (
        <Polyline key={t.id} positions={t.points as LatLngExpression[]}
          pathOptions={{ color: t.color, weight: t.weight ?? 3, opacity: t.opacity ?? 0.9 }}>
          {t.label && <Tooltip sticky>{t.label}</Tooltip>}
        </Polyline>
      ))}
      {dots.map((d, i) => (
        <CircleMarker key={i} center={[d.lat, d.lon]} radius={d.r ?? 3}
          pathOptions={{ color: d.color, fillColor: d.color, fillOpacity: 0.7, weight: 0 }}>
          {d.label && <Tooltip>{d.label}</Tooltip>}
        </CircleMarker>
      ))}
      <Fit bounds={bounds} />
    </MapContainer>
    </div>
  );
}
