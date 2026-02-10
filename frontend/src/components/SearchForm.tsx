import { useState } from "react";
import { format, setHours, setMinutes, startOfDay } from "date-fns";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Calendar } from "@/components/ui/calendar";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Search, MapPin, Clock, CalendarDays, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { LocationInput } from "@/components/LocationInput";

const SERVICES = [
  "dentist",
  "doctor",
  "therapist",
  "optometrist",
  "dermatologist",
  "veterinarian",
];

const TIME_OPTIONS = Array.from({ length: 28 }, (_, i) => {
  const totalMinutes = 7 * 60 + i * 30; // 7:00 AM to 20:30 (8:30 PM)
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const label = `${hours % 12 || 12}:${minutes.toString().padStart(2, "0")} ${hours >= 12 ? "PM" : "AM"}`;
  const value = `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}`;
  return { label, value };
});

interface SearchFormProps {
  onSubmit: (params: {
    service: string;
    location: string;
    lat?: number;
    lng?: number;
    dateRangeStart: string;
    dateRangeEnd: string;
    durationMin: number;
    maxTravelMinutes?: number;
    clientName: string;
  }) => void;
  isLoading: boolean;
}

export function SearchForm({ onSubmit, isLoading }: SearchFormProps) {
  const [clientName, setClientName] = useState("");
  const [service, setService] = useState("");
  const [location, setLocation] = useState("");
  const [coords, setCoords] = useState<{ lat: number; lng: number } | undefined>();
  const [dateStart, setDateStart] = useState<Date | undefined>();
  const [timeStart, setTimeStart] = useState("09:00");
  const [dateEnd, setDateEnd] = useState<Date | undefined>();
  const [timeEnd, setTimeEnd] = useState("17:00");
  const [duration, setDuration] = useState("30");

  const combineDateAndTime = (date: Date, time: string): string => {
    const [h, m] = time.split(":").map(Number);
    return setMinutes(setHours(date, h), m).toISOString();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!clientName || !service || !location || !dateStart || !dateEnd) return;

    onSubmit({
      clientName,
      service,
      location,
      lat: coords?.lat,
      lng: coords?.lng,
      dateRangeStart: combineDateAndTime(dateStart, timeStart),
      dateRangeEnd: combineDateAndTime(dateEnd, timeEnd),
      durationMin: parseInt(duration),
    });
  };

  return (
    <div className="animate-slide-up">
      <div className="mb-10 text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary">
          <Search className="h-7 w-7 text-primary-foreground" />
        </div>
        <h2 className="mb-2 text-3xl font-bold tracking-tight font-display">
          Find your appointment
        </h2>
        <p className="text-muted-foreground">
          CallPilot calls providers for you and finds the best available slot.
        </p>
      </div>

      <Card className="glass shadow-xl">
        <CardContent className="p-6 sm:p-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Your Details */}
            <div className="space-y-2">
              <Label className="flex items-center gap-2 text-sm font-medium">
                <User className="h-3.5 w-3.5 text-muted-foreground" />
                Your name
              </Label>
              <Input
                placeholder="e.g. Alice Müller"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                required
              />
            </div>

            <div className="space-y-2">
              <Label className="flex items-center gap-2 text-sm font-medium">
                <Search className="h-3.5 w-3.5 text-muted-foreground" />
                Service type
              </Label>
              <Select value={service} onValueChange={setService}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a service" />
                </SelectTrigger>
                <SelectContent>
                  {SERVICES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s.charAt(0).toUpperCase() + s.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label className="flex items-center gap-2 text-sm font-medium">
                <MapPin className="h-3.5 w-3.5 text-muted-foreground" />
                Location
              </Label>
              <LocationInput
                value={location}
                onChange={(loc, c) => {
                  setLocation(loc);
                  setCoords(c);
                }}
                placeholder="City, neighbourhood, or address"
              />
            </div>

            {/* Date & time range */}
            <div className="grid gap-6 sm:grid-cols-2">
              <div className="space-y-2">
                <Label className="flex items-center gap-2 text-sm font-medium">
                  <CalendarDays className="h-3.5 w-3.5 text-muted-foreground" />
                  Earliest date & time
                </Label>
                <div className="flex gap-2">
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        className={cn(
                          "flex-1 justify-start text-left font-normal",
                          !dateStart && "text-muted-foreground"
                        )}
                      >
                        <CalendarDays className="mr-2 h-4 w-4" />
                        {dateStart ? format(dateStart, "MMM d, yyyy") : "Pick date"}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0 bg-popover z-50" align="start">
                      <Calendar
                        mode="single"
                        selected={dateStart}
                        onSelect={setDateStart}
                        disabled={(date) => date < startOfDay(new Date())}
                        initialFocus
                        className={cn("p-3 pointer-events-auto")}
                      />
                    </PopoverContent>
                  </Popover>
                  <Select value={timeStart} onValueChange={setTimeStart}>
                    <SelectTrigger className="w-[120px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-popover z-50">
                      {TIME_OPTIONS.map((t) => (
                        <SelectItem key={t.value} value={t.value}>
                          {t.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label className="flex items-center gap-2 text-sm font-medium">
                  <CalendarDays className="h-3.5 w-3.5 text-muted-foreground" />
                  Latest date & time
                </Label>
                <div className="flex gap-2">
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        className={cn(
                          "flex-1 justify-start text-left font-normal",
                          !dateEnd && "text-muted-foreground"
                        )}
                      >
                        <CalendarDays className="mr-2 h-4 w-4" />
                        {dateEnd ? format(dateEnd, "MMM d, yyyy") : "Pick date"}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0 bg-popover z-50" align="start">
                      <Calendar
                        mode="single"
                        selected={dateEnd}
                        onSelect={setDateEnd}
                        disabled={(date) =>
                          date < (dateStart ?? startOfDay(new Date()))
                        }
                        initialFocus
                        className={cn("p-3 pointer-events-auto")}
                      />
                    </PopoverContent>
                  </Popover>
                  <Select value={timeEnd} onValueChange={setTimeEnd}>
                    <SelectTrigger className="w-[120px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-popover z-50">
                      {TIME_OPTIONS.map((t) => (
                        <SelectItem key={t.value} value={t.value}>
                          {t.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            {/* Duration */}
            <div className="space-y-2">
              <Label className="flex items-center gap-2 text-sm font-medium">
                <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                Duration
              </Label>
              <Select value={duration} onValueChange={setDuration}>
                <SelectTrigger className="sm:w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-popover z-50">
                  <SelectItem value="15">15 min</SelectItem>
                  <SelectItem value="30">30 min</SelectItem>
                  <SelectItem value="45">45 min</SelectItem>
                  <SelectItem value="60">60 min</SelectItem>
                  <SelectItem value="90">90 min</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button
              type="submit"
              size="lg"
              className="w-full text-base font-semibold"
              disabled={isLoading || !clientName || !service || !location || !dateStart || !dateEnd}
            >
              {isLoading ? "Searching…" : "Find providers"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
