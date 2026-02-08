import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Phone, CheckCircle2, XCircle, Loader2, PhoneCall } from "lucide-react";
import type { CampaignStatus } from "@/types/campaign";

interface CampaignProgressProps {
  status: CampaignStatus | null;
  onCancel?: () => void;
}

export function CampaignProgress({ status, onCancel }: CampaignProgressProps) {
  const progress = status?.progress;
  const total = progress?.total_providers ?? 0;
  const completed = progress?.completed_calls ?? 0;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  const isInitializing = !status;
  const callsInProgress = progress?.calls_in_progress ?? 0;

  return (
    <div className="animate-slide-up">
      <div className="mb-10 text-center">
        <div className="relative mx-auto mb-6 flex h-16 w-16 items-center justify-center">
          <div className="absolute inset-0 rounded-2xl bg-primary/20 animate-pulse-ring" />
          <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-primary">
            {isInitializing ? (
              <Loader2 className="h-7 w-7 text-primary-foreground animate-spin" />
            ) : (
              <Phone className="h-7 w-7 text-primary-foreground" />
            )}
          </div>
        </div>
        <h2 className="mb-2 text-3xl font-bold tracking-tight font-display">
          {isInitializing ? "Starting search…" : "Calling providers…"}
        </h2>
        <p className="text-muted-foreground">
          {isInitializing 
            ? "Setting up your appointment search. This may take a moment."
            : `CallPilot is reaching out to ${total} providers in your area.`
          }
        </p>
      </div>

      <Card className="glass shadow-xl">
        <CardContent className="space-y-6 p-6 sm:p-8">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Progress</span>
              <span className="font-semibold font-display">{pct}%</span>
            </div>
            <Progress value={isInitializing ? undefined : pct} className="h-3" />
          </div>

          {!isInitializing && (
            <div className="grid grid-cols-4 gap-3">
              <Stat
                icon={<Phone className="h-4 w-4" />}
                label="Calls made"
                value={completed}
                color="text-foreground"
              />
              <Stat
                icon={<PhoneCall className="h-4 w-4" />}
                label="Calling…"
                value={callsInProgress}
                color="text-warning"
                pulse={callsInProgress > 0}
              />
              <Stat
                icon={<CheckCircle2 className="h-4 w-4" />}
                label="Available"
                value={progress?.successful_calls ?? 0}
                color="text-success"
              />
              <Stat
                icon={<XCircle className="h-4 w-4" />}
                label="Unavailable"
                value={progress?.failed_calls ?? 0}
                color="text-destructive"
              />
            </div>
          )}

          {status?.best && (
            <div className="rounded-lg border border-success/30 bg-success/5 p-4">
              <p className="text-sm font-medium text-success">
                ✨ Best match so far: {status.best.provider_id} — Score{" "}
                {Math.round(status.best.score * 100)}%
              </p>
            </div>
          )}

          {onCancel && (
            <Button
              variant="outline"
              onClick={onCancel}
              className="w-full"
            >
              Cancel search
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
  color,
  pulse,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  color: string;
  pulse?: boolean;
}) {
  return (
    <div className="rounded-lg bg-secondary/50 p-4 text-center">
      <div className={`mb-1 flex justify-center ${color} ${pulse ? "animate-pulse" : ""}`}>{icon}</div>
      <p className="text-2xl font-bold font-display">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
