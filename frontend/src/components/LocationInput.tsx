import { useState, useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { MapPin, Navigation, Loader2 } from "lucide-react";

interface LocationInputProps {
  value: string;
  onChange: (
    location: string,
    coords?: { lat: number; lng: number }
  ) => void;
  placeholder?: string;
}

export function LocationInput({
  value,
  onChange,
  placeholder = "City, neighbourhood, or address",
}: LocationInputProps) {
  const [isLocating, setIsLocating] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);

  const reverseGeocode = useCallback(
    async (lat: number, lng: number): Promise<string> => {
      try {
        const res = await fetch(
          `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&addressdetails=1`,
          { headers: { "User-Agent": "CallPilot/1.0" } }
        );
        if (!res.ok) throw new Error("Geocode failed");
        const data = await res.json();

        // Build a concise display address from address parts
        const addr = data.address || {};
        const parts = [
          addr.suburb || addr.neighbourhood || addr.town || "",
          addr.city || addr.municipality || addr.county || "",
          addr.postcode || "",
        ].filter(Boolean);

        return parts.length > 0 ? parts.join(", ") : data.display_name || `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
      } catch {
        // Fall back to raw coordinates
        return `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
      }
    },
    []
  );

  const handleUseMyLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setGeoError("Geolocation is not supported by your browser.");
      return;
    }

    setIsLocating(true);
    setGeoError(null);

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        const address = await reverseGeocode(latitude, longitude);
        onChange(address, { lat: latitude, lng: longitude });
        setIsLocating(false);
      },
      (err) => {
        setIsLocating(false);
        switch (err.code) {
          case err.PERMISSION_DENIED:
            setGeoError("Location permission denied. Please enter your address manually.");
            break;
          case err.POSITION_UNAVAILABLE:
            setGeoError("Location unavailable. Please enter your address manually.");
            break;
          case err.TIMEOUT:
            setGeoError("Location request timed out. Please try again.");
            break;
          default:
            setGeoError("Could not detect location. Please enter your address manually.");
        }
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
    );
  }, [onChange, reverseGeocode]);

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <MapPin className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <Input
            placeholder={placeholder}
            value={value}
            onChange={(e) => {
              setGeoError(null);
              onChange(e.target.value);
            }}
            className="pl-9"
          />
        </div>
        <Button
          type="button"
          variant="outline"
          size="default"
          onClick={handleUseMyLocation}
          disabled={isLocating}
          className="shrink-0 gap-1.5"
          title="Use my current location"
        >
          {isLocating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Navigation className="h-4 w-4" />
          )}
          <span className="hidden sm:inline">
            {isLocating ? "Locating..." : "Use my location"}
          </span>
        </Button>
      </div>
      {geoError && (
        <p className="text-xs text-destructive">{geoError}</p>
      )}
    </div>
  );
}
