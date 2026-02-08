import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Star, Clock, CalendarDays } from "lucide-react";
import { format } from "date-fns";
import type { CampaignStatus, ProviderSlot } from "@/types/campaign";

interface ResultsListProps {
  status: CampaignStatus;
  onSelect: (slot: ProviderSlot) => void;
  onBack: () => void;
}

export function ResultsList({ status, onSelect, onBack }: ResultsListProps) {
  const ranked = status.ranked ?? [];

  return (
    <div className="animate-slide-up">
      <div className="mb-8">
        <Button
          variant="ghost"
          size="sm"
          onClick={onBack}
          className="mb-4 -ml-2 text-muted-foreground"
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          New search
        </Button>
        <h2 className="mb-2 text-3xl font-bold tracking-tight font-display">
          Available slots
        </h2>
        <p className="text-muted-foreground">
          We found {ranked.length} option{ranked.length !== 1 ? "s" : ""} for you.
          Pick the one that works best.
        </p>
      </div>

      {ranked.length === 0 ? (
        <Card className="glass shadow-lg">
          <CardContent className="p-8 text-center">
            <p className="text-muted-foreground">
              No slots were found. Try broadening your date range or location.
            </p>
            <Button onClick={onBack} className="mt-4">
              Try again
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {ranked.map((slot, i) => (
            <SlotCard
              key={`${slot.provider_id}-${slot.start}`}
              slot={slot}
              rank={i + 1}
              isBest={i === 0}
              onSelect={() => onSelect(slot)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SlotCard({
  slot,
  rank,
  isBest,
  onSelect,
}: {
  slot: ProviderSlot;
  rank: number;
  isBest: boolean;
  onSelect: () => void;
}) {
  const startDate = new Date(slot.start);
  const endDate = new Date(slot.end);
  const scorePercent = Math.round(slot.score * 100);

  return (
    <Card
      className={`glass shadow-md transition-all hover:shadow-lg cursor-pointer group ${
        isBest ? "ring-2 ring-primary/50" : ""
      }`}
      onClick={onSelect}
    >
      <CardContent className="flex items-center gap-4 p-4 sm:p-5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 font-display font-bold text-primary">
          {rank}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <p className="truncate font-semibold font-display">
              {slot.provider_name || slot.provider_id}
            </p>
            {isBest && (
              <Badge className="bg-primary/10 text-primary border-0 text-xs">
                <Star className="mr-1 h-3 w-3" /> Best match
              </Badge>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span className="flex items-center gap-1">
              <CalendarDays className="h-3.5 w-3.5" />
              {format(startDate, "MMM d, yyyy")}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {format(startDate, "h:mm a")} – {format(endDate, "h:mm a")}
            </span>
          </div>
        </div>

        <div className="hidden sm:flex flex-col items-end gap-1">
          <span className="text-lg font-bold font-display text-primary">
            {scorePercent}%
          </span>
          <span className="text-xs text-muted-foreground">match</span>
        </div>

        <Button
          size="sm"
          className="shrink-0 opacity-80 group-hover:opacity-100 transition-opacity"
        >
          Book
        </Button>
      </CardContent>
    </Card>
  );
}
