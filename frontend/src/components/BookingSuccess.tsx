import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CheckCircle2, Copy, RotateCcw, CalendarDays, Clock, User } from "lucide-react";
import { format } from "date-fns";
import { toast } from "sonner";
import type { BookingDetails } from "@/types/campaign";

interface BookingSuccessProps {
  booking: BookingDetails;
  onReset: () => void;
}

export function BookingSuccess({ booking, onReset }: BookingSuccessProps) {
  const copyRef = () => {
    navigator.clipboard.writeText(booking.confirmation_ref);
    toast.success("Reference copied to clipboard");
  };

  const startDate = new Date(booking.start);
  const endDate = new Date(booking.end);

  return (
    <div className="animate-slide-up text-center">
      <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-success/10">
        <CheckCircle2 className="h-10 w-10 text-success" />
      </div>

      <h2 className="mb-2 text-3xl font-bold tracking-tight font-display">
        You're all set{booking.client_name ? `, ${booking.client_name}` : ""}!
      </h2>
      <p className="mb-8 text-muted-foreground">
        Your appointment has been automatically booked.
      </p>

      <Card className="glass shadow-xl mx-auto max-w-sm">
        <CardContent className="p-6 space-y-4">
          {/* Appointment details */}
          <div className="space-y-2.5 text-left">
            <div className="flex items-center gap-3">
              <User className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium font-display">{booking.provider_id}</span>
            </div>
            <div className="flex items-center gap-3">
              <CalendarDays className="h-4 w-4 text-muted-foreground" />
              <span>{format(startDate, "EEEE, MMMM d, yyyy")}</span>
            </div>
            <div className="flex items-center gap-3">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <span>
                {format(startDate, "h:mm a")} – {format(endDate, "h:mm a")}
              </span>
            </div>
          </div>

          {/* Divider */}
          <div className="border-t border-border/50" />

          {/* Confirmation ref */}
          <div>
            <p className="mb-1 text-sm text-muted-foreground">Confirmation reference</p>
            <button
              onClick={copyRef}
              className="group flex w-full items-center justify-center gap-2 rounded-lg bg-secondary/60 px-4 py-3 font-mono text-lg font-bold tracking-widest transition-colors hover:bg-secondary"
            >
              {booking.confirmation_ref}
              <Copy className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
            </button>
          </div>

          {booking.notes && (
            <p className="text-xs text-muted-foreground/70 italic">{booking.notes}</p>
          )}
        </CardContent>
      </Card>

      <Button
        variant="ghost"
        size="lg"
        onClick={onReset}
        className="mt-8 text-muted-foreground"
      >
        <RotateCcw className="mr-2 h-4 w-4" />
        Schedule another
      </Button>
    </div>
  );
}
