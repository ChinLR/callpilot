import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Phone,
  CheckCircle2,
  Star,
  Clock,
  CalendarDays,
  Loader2,
  PhoneOff,
  Trophy,
  MapPin,
  Heart,
  Zap,
} from "lucide-react";
import { format } from "date-fns";
import type { CampaignStatus, ScoringBreakdown } from "@/types/campaign";

interface AgentResultsProps {
  status: CampaignStatus;
  onBooked: () => void;
}

const SCORE_DIMENSIONS = [
  { key: "earliest" as const, label: "Availability", icon: Clock, color: "bg-primary" },
  { key: "rating" as const, label: "Rating", icon: Star, color: "bg-primary" },
  { key: "distance" as const, label: "Distance", icon: MapPin, color: "bg-primary" },
  { key: "preference" as const, label: "Preference", icon: Heart, color: "bg-primary" },
];

const FAILED_OUTCOMES = new Set(["no_answer", "failed", "busy", "error", "voicemail"]);

export function AgentResults({ status, onBooked }: AgentResultsProps) {
  const [animateIn, setAnimateIn] = useState(false);
  const [showConfirmed, setShowConfirmed] = useState(false);

  const ranked = status.ranked ?? [];
  const debug = status.debug ?? {};
  const providers = debug.providers ?? {};
  const scoring = debug.scoring ?? {};
  const outcomes = debug.provider_outcomes ?? {};
  const isBooking = status.status === "booking";
  const isBooked = status.status === "booked";
  const best = status.best;

  // Animate score bars in
  useEffect(() => {
    const timer = setTimeout(() => setAnimateIn(true), 100);
    return () => clearTimeout(timer);
  }, []);

  // When booked, show calling-back animation first, then confirmed state
  useEffect(() => {
    if (isBooked) {
      // Show the "calling back" animation for 3 seconds before revealing confirmed
      const confirmTimer = setTimeout(() => {
        setShowConfirmed(true);
      }, 3000);
      const navTimer = setTimeout(onBooked, 8000); // 3s animation + 5s confirmed
      return () => {
        clearTimeout(confirmTimer);
        clearTimeout(navTimer);
      };
    }
  }, [isBooked, onBooked]);

  // Split providers into successful and failed
  const successProviderIds = ranked.map((s) => s.provider_id);
  const failedProviderIds = Object.entries(outcomes)
    .filter(([id, outcome]) => FAILED_OUTCOMES.has(outcome) && !successProviderIds.includes(id))
    .map(([id]) => id);

  const getProviderName = (id: string) => providers[id]?.name ?? id;
  const getProviderRating = (id: string) => providers[id]?.rating;
  const getScoring = (id: string): ScoringBreakdown | null => scoring[id]?.[0] ?? null;

  const getOutcomeLabel = (outcome: string) => {
    switch (outcome) {
      case "no_answer": return "No Answer";
      case "failed": return "Call Failed";
      case "busy": return "Line Busy";
      case "voicemail": return "Voicemail";
      case "error": return "Error";
      default: return outcome;
    }
  };

  return (
    <div className="animate-slide-up space-y-8">
      {/* Section 1: Confirming Booking — at the top */}
      {best && (
        <div>
          <Card className={`glass shadow-xl overflow-hidden transition-colors duration-500 ${
            isBooked && showConfirmed ? "border-success/30" : "border-primary/20"
          }`}>
            <div className={`h-0.5 transition-colors duration-500 ${
              isBooked && showConfirmed
                ? "bg-success"
                : "bg-gradient-to-r from-primary/0 via-primary to-primary/0 animate-pulse"
            }`} />
            <CardContent className="p-6 sm:p-8">
              {/* Calling back state */}
              {!(isBooked && showConfirmed) && (
                <div className="animate-fade-in">
                  <div className="flex items-center gap-4 mb-5">
                    <div className="relative flex h-14 w-14 items-center justify-center">
                      <div className="absolute inset-0 rounded-2xl bg-primary/20 animate-pulse-ring" />
                      <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl bg-primary">
                        <Phone className="h-6 w-6 text-primary-foreground" />
                      </div>
                    </div>
                    <div>
                      <h3 className="text-lg font-bold font-display">
                        Confirming Booking
                      </h3>
                      <p className="text-sm text-muted-foreground">
                        Calling back{" "}
                        <span className="text-foreground font-medium">
                          {getProviderName(best.provider_id)}
                        </span>{" "}
                        to confirm your appointment…
                      </p>
                    </div>
                  </div>

                  <div className="rounded-lg bg-secondary/50 p-4 space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <CalendarDays className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">
                        {format(new Date(best.start), "EEEE, MMMM d")}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-sm">
                      <Clock className="h-4 w-4 text-muted-foreground" />
                      <span>
                        {format(new Date(best.start), "h:mm a")} –{" "}
                        {format(new Date(best.end), "h:mm a")}
                      </span>
                    </div>
                  </div>

                  <div className="mt-5 flex items-center justify-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Call in progress</span>
                    <span className="inline-flex gap-0.5">
                      <span className="animate-pulse" style={{ animationDelay: "0ms" }}>.</span>
                      <span className="animate-pulse" style={{ animationDelay: "200ms" }}>.</span>
                      <span className="animate-pulse" style={{ animationDelay: "400ms" }}>.</span>
                    </span>
                  </div>
                </div>
              )}

              {/* Confirmed state */}
              {isBooked && showConfirmed && (
                <div className="text-center animate-scale-in">
                  <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-success/10">
                    <CheckCircle2 className="h-8 w-8 text-success" />
                  </div>
                  <h3 className="text-xl font-bold font-display mb-1">
                    Booking Confirmed!
                  </h3>
                  <p className="text-sm text-muted-foreground mb-4">
                    {status.booking?.client_name
                      ? `Booked for ${status.booking.client_name}`
                      : "Your appointment has been secured."}
                  </p>
                  {status.booking && (
                    <div className="inline-flex items-center gap-2 rounded-full bg-secondary/60 px-4 py-2 text-sm font-mono font-semibold tracking-wider">
                      {status.booking.confirmation_ref}
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Section 2: Provider Scores */}
      <div>
        <div className="flex items-center gap-3 mb-6">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary">
            <Trophy className="h-6 w-6 text-primary-foreground" />
          </div>
          <div>
            <h2 className="text-2xl font-bold tracking-tight font-display">
              Provider Scores
            </h2>
            <p className="text-sm text-muted-foreground">
              {ranked.length} provider{ranked.length !== 1 ? "s" : ""} ranked by best fit
            </p>
          </div>
        </div>

        <div className="space-y-3">
          {ranked.map((slot, i) => {
            const isBest = i === 0;
            const providerScoring = getScoring(slot.provider_id);
            const rating = getProviderRating(slot.provider_id);
            const scorePercent = Math.round(slot.score * 100);

            return (
              <Card
                key={slot.provider_id}
                className={`glass shadow-md transition-all ${
                  isBest
                    ? "ring-2 ring-success/50 shadow-[0_0_20px_hsl(152,50%,48%,0.1)]"
                    : ""
                }`}
                style={{ animationDelay: `${i * 80}ms` }}
              >
                <CardContent className="p-5">
                  {/* Provider header */}
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div
                        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg font-display font-bold text-sm ${
                          isBest
                            ? "bg-success text-success-foreground"
                            : "bg-secondary text-secondary-foreground"
                        }`}
                      >
                        {i + 1}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-semibold font-display">
                            {getProviderName(slot.provider_id)}
                          </p>
                          {isBest && (
                            <Badge className="bg-success/15 text-success border-0 text-[10px] uppercase tracking-wider font-semibold">
                              <Zap className="mr-0.5 h-2.5 w-2.5" />
                              Best Match — Selected by Agent
                            </Badge>
                          )}
                        </div>
                        {rating != null && (
                          <div className="flex items-center gap-1 mt-0.5 text-sm text-muted-foreground">
                            <Star className="h-3 w-3 fill-primary text-primary" />
                            {rating.toFixed(1)}
                            {providers[slot.provider_id]?.address && (
                              <>
                                <span className="mx-1.5">•</span>
                                <span className="text-xs truncate max-w-[200px]">
                                  {providers[slot.provider_id].address}
                                </span>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-bold font-display text-primary">
                        {scorePercent}%
                      </p>
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        match
                      </p>
                    </div>
                  </div>

                  {/* Score breakdown */}
                  {providerScoring && (
                    <div className="grid grid-cols-2 gap-x-4 gap-y-2.5">
                      {SCORE_DIMENSIONS.map((dim) => {
                        const value = providerScoring[dim.key];
                        const weight = providerScoring.weights[dim.key];
                        const Icon = dim.icon;

                        return (
                          <div key={dim.key} className="space-y-1">
                            <div className="flex items-center justify-between text-xs">
                              <span className="flex items-center gap-1 text-muted-foreground">
                                <Icon className="h-3 w-3" />
                                {dim.label}
                              </span>
                              <span className="text-muted-foreground/60 tabular-nums">
                                {Math.round(weight * 100)}% wt
                              </span>
                            </div>
                            <div className="relative h-2 w-full overflow-hidden rounded-full bg-secondary">
                              <div
                                className={`h-full rounded-full ${dim.color} transition-all duration-700 ease-out`}
                                style={{
                                  width: animateIn
                                    ? `${Math.round(value * 100)}%`
                                    : "0%",
                                  transitionDelay: `${i * 80 + 200}ms`,
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}

          {/* Failed providers */}
          {failedProviderIds.length > 0 && (
            <div className="space-y-2 pt-2">
              <p className="text-xs uppercase tracking-wider text-muted-foreground/50 font-semibold px-1">
                Unavailable
              </p>
              {failedProviderIds.map((id) => (
                <Card key={id} className="glass opacity-40">
                  <CardContent className="flex items-center justify-between p-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-secondary">
                        <PhoneOff className="h-4 w-4 text-muted-foreground" />
                      </div>
                      <p className="font-medium font-display text-muted-foreground">
                        {getProviderName(id)}
                      </p>
                    </div>
                    <Badge
                      variant="outline"
                      className="text-muted-foreground border-border/50 text-xs"
                    >
                      {getOutcomeLabel(outcomes[id])}
                    </Badge>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
