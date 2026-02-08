import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CalendarCheck, Loader2, Star, Clock, CalendarDays } from "lucide-react";
import { format } from "date-fns";
import type { CampaignStatus } from "@/types/campaign";

interface BookingProgressProps {
  status: CampaignStatus;
}

export function BookingProgress({ status }: BookingProgressProps) {
  const best = status.best;

  return (
    <div className="animate-slide-up text-center">
      <div className="relative mx-auto mb-6 flex h-16 w-16 items-center justify-center">
        <div className="absolute inset-0 rounded-2xl bg-primary/20 animate-pulse-ring" />
        <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-primary">
          <CalendarCheck className="h-7 w-7 text-primary-foreground animate-pulse" />
        </div>
      </div>

      <h2 className="mb-2 text-3xl font-bold tracking-tight font-display">
        Booking best match…
      </h2>
      <p className="mb-8 text-muted-foreground">
        Found available slots! The agent is now confirming the best option for you.
      </p>

      {best && (
        <Card className="glass shadow-xl mx-auto max-w-sm">
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-3">
              <Badge className="bg-primary/10 text-primary border-0 text-xs">
                <Star className="mr-1 h-3 w-3" /> Best match
              </Badge>
              <span className="text-sm text-muted-foreground">
                {Math.round(best.score * 100)}% match
              </span>
            </div>

            <p className="font-semibold font-display mb-2">
              {best.provider_name || best.provider_id}
            </p>

            <div className="space-y-1.5 text-sm text-muted-foreground">
              <div className="flex items-center gap-2">
                <CalendarDays className="h-3.5 w-3.5" />
                {format(new Date(best.start), "EEEE, MMMM d, yyyy")}
              </div>
              <div className="flex items-center gap-2">
                <Clock className="h-3.5 w-3.5" />
                {format(new Date(best.start), "h:mm a")} – {format(new Date(best.end), "h:mm a")}
              </div>
            </div>

            <div className="mt-4 flex items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Confirming with provider…
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
