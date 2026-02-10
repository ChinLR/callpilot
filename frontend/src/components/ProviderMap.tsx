import { useMemo } from "react";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Star, Clock, MapPin } from "lucide-react";
import type { Provider } from "@/types/campaign";

// Fix Leaflet's default marker icon path issue with bundlers
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

// Custom icon for the user's location
const userIcon = new L.Icon({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
  className: "hue-rotate-[200deg] saturate-150 brightness-75",
});

interface ProviderMapProps {
  providers: Provider[];
  center?: { lat: number; lng: number };
  selectedIds?: Set<string>;
}

export function ProviderMap({ providers, center, selectedIds }: ProviderMapProps) {
  // Determine map center: user coords > first provider > fallback
  const mapCenter = useMemo<[number, number]>(() => {
    if (center) return [center.lat, center.lng];
    const firstWithCoords = providers.find((p) => p.lat && p.lng);
    if (firstWithCoords) return [firstWithCoords.lat!, firstWithCoords.lng!];
    return [37.7749, -122.4194]; // San Francisco fallback
  }, [center, providers]);

  // Filter providers that have coordinates
  const mappableProviders = useMemo(
    () => providers.filter((p) => p.lat != null && p.lng != null),
    [providers]
  );

  if (mappableProviders.length === 0 && !center) {
    return null; // Nothing to show on the map
  }

  // Compute bounds to fit all markers
  const bounds = useMemo(() => {
    const points: [number, number][] = mappableProviders.map((p) => [p.lat!, p.lng!]);
    if (center) points.push([center.lat, center.lng]);
    if (points.length === 0) return undefined;
    if (points.length === 1) return undefined; // single point — use center + zoom
    return L.latLngBounds(points.map(([lat, lng]) => L.latLng(lat, lng))).pad(0.15);
  }, [mappableProviders, center]);

  return (
    <div className="overflow-hidden rounded-xl border border-border/50" style={{ height: 300 }}>
      <MapContainer
        center={mapCenter}
        zoom={13}
        bounds={bounds}
        scrollWheelZoom={true}
        style={{ height: "100%", width: "100%" }}
        className="z-0"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* User location marker */}
        {center && (
          <Marker position={[center.lat, center.lng]} icon={userIcon}>
            <Popup>
              <span className="font-medium">Your location</span>
            </Popup>
          </Marker>
        )}

        {/* Provider markers */}
        {mappableProviders.map((provider) => {
          const isSelected = !selectedIds || selectedIds.has(provider.id);
          const opacity = isSelected ? 1 : 0.4;

          return (
            <Marker
              key={provider.id}
              position={[provider.lat!, provider.lng!]}
              opacity={opacity}
            >
              <Popup>
                <div className="min-w-[180px] space-y-1">
                  <div className="font-semibold text-sm">{provider.name}</div>
                  <div className="flex items-center gap-2 text-xs text-gray-600">
                    {provider.travel_minutes != null && (
                      <span className="flex items-center gap-0.5">
                        <Clock className="h-3 w-3" />
                        {provider.travel_minutes} min
                      </span>
                    )}
                    {provider.rating != null && (
                      <span className="flex items-center gap-0.5">
                        <Star className="h-3 w-3" />
                        {provider.rating.toFixed(1)}
                      </span>
                    )}
                  </div>
                  <div className="flex items-start gap-1 text-xs text-gray-500">
                    <MapPin className="h-3 w-3 mt-0.5 shrink-0" />
                    <span>{provider.address}</span>
                  </div>
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>
    </div>
  );
}
