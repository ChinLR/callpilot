import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { ArrowLeft, MapPin, Star, Building2, Users, Clock, Sparkles } from "lucide-react";
import type { Provider } from "@/types/campaign";
import { ProviderMap } from "@/components/ProviderMap";

interface ProviderSelectionProps {
  providers: Provider[];
  onContinue: (selectedIds: string[]) => void;
  onBack: () => void;
  isLoading: boolean;
  autoBook: boolean;
  onAutoBookChange: (value: boolean) => void;
  mapCenter?: { lat: number; lng: number };
}

export function ProviderSelection({
  providers,
  onContinue,
  onBack,
  isLoading,
  autoBook,
  onAutoBookChange,
  mapCenter,
}: ProviderSelectionProps) {
  const [selected, setSelected] = useState<Set<string>>(
    new Set(providers.map((p) => p.id))
  );

  const toggleProvider = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === providers.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(providers.map((p) => p.id)));
    }
  };

  return (
    <div className="animate-slide-up">
      <div className="mb-8">
        <Button
          variant="ghost"
          size="sm"
          onClick={onBack}
          className="mb-4 -ml-2 text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back
        </Button>

        <div className="flex items-center gap-3 mb-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary">
            <Building2 className="h-6 w-6 text-primary-foreground" />
          </div>
          <div>
            <h2 className="text-2xl font-bold tracking-tight font-display">
              Select providers
            </h2>
            <p className="text-muted-foreground text-sm">
              {providers.length} provider{providers.length !== 1 ? "s" : ""} found • Deselect any you'd like to skip
            </p>
          </div>
        </div>
      </div>

      {/* Provider map */}
      <div className="mb-6">
        <ProviderMap
          providers={providers}
          center={mapCenter}
          selectedIds={selected}
        />
      </div>

      <Card className="glass shadow-xl mb-6">
        <CardContent className="p-4">
          <div className="flex items-center justify-between pb-3 border-b border-border/50">
            <button
              onClick={toggleAll}
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <Checkbox
                checked={selected.size === providers.length}
                onCheckedChange={toggleAll}
              />
              <span>
                {selected.size === providers.length ? "Deselect all" : "Select all"}
              </span>
            </button>
            <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Users className="h-4 w-4" />
              {selected.size} selected
            </div>
          </div>

          <div className="divide-y divide-border/50">
            {providers?.map((provider) => (
              <div
                key={provider.id}
                className={`flex items-start gap-3 py-4 transition-opacity ${
                  !selected.has(provider.id) ? "opacity-50" : ""
                }`}
              >
                <Checkbox
                  checked={selected.has(provider.id)}
                  onCheckedChange={() => toggleProvider(provider.id)}
                  className="mt-0.5"
                />
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{provider.name}</div>
                  <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
                    {provider.travel_minutes != null && (
                      <span className="flex items-center gap-1">
                        <Clock className="h-3.5 w-3.5" />
                        {provider.travel_minutes} min away
                      </span>
                    )}
                    {provider.rating != null && (
                      <span className="flex items-center gap-1">
                        <Star className="h-3.5 w-3.5 fill-primary/80 text-primary/80" />
                        {provider.rating.toFixed(1)}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground/70 mt-0.5 truncate">
                    <span className="inline-flex items-center gap-1">
                      <MapPin className="h-3 w-3" />
                      {provider.address}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Auto-book toggle */}
      <Card className="glass shadow-md mb-4">
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Sparkles className="h-4 w-4 text-primary" />
              <div>
                <Label htmlFor="auto-book" className="font-medium cursor-pointer">
                  Auto-book best match
                </Label>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {autoBook
                    ? "The agent will automatically confirm the best slot"
                    : "You'll pick from available slots manually"}
                </p>
              </div>
            </div>
            <Switch
              id="auto-book"
              checked={autoBook}
              onCheckedChange={onAutoBookChange}
            />
          </div>
        </CardContent>
      </Card>

      <Button
        size="lg"
        className="w-full text-base font-semibold"
        disabled={selected.size === 0 || isLoading}
        onClick={() => onContinue(Array.from(selected))}
      >
        {isLoading
          ? "Starting calls…"
          : `Call ${selected.size} provider${selected.size !== 1 ? "s" : ""}`}
      </Button>
    </div>
  );
}
