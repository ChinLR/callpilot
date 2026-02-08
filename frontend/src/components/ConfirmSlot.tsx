import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { ArrowLeft, CalendarDays, Clock, User } from "lucide-react";
import { format } from "date-fns";
import type { ProviderSlot, ConfirmRequest } from "@/types/campaign";

interface ConfirmSlotProps {
  slot: ProviderSlot;
  onConfirm: (contact: ConfirmRequest["user_contact"]) => void;
  onBack: () => void;
  isLoading: boolean;
}

export function ConfirmSlot({ slot, onConfirm, onBack, isLoading }: ConfirmSlotProps) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");

  const startDate = new Date(slot.start);
  const endDate = new Date(slot.end);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !phone) return;
    onConfirm({ name, phone });
  };

  return (
    <div className="animate-slide-up">
      <Button
        variant="ghost"
        size="sm"
        onClick={onBack}
        className="mb-4 -ml-2 text-muted-foreground"
      >
        <ArrowLeft className="mr-1 h-4 w-4" />
        Back to results
      </Button>

      <div className="mb-8">
        <h2 className="mb-2 text-3xl font-bold tracking-tight font-display">
          Confirm your appointment
        </h2>
        <p className="text-muted-foreground">
          Review the details and enter your contact information.
        </p>
      </div>

      <div className="space-y-4">
        {/* Appointment summary */}
        <Card className="glass shadow-md">
          <CardContent className="p-5">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Appointment details
            </h3>
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <User className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium font-display">
                  {slot.provider_name || slot.provider_id}
                </span>
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
          </CardContent>
        </Card>

        {/* Contact form */}
        <Card className="glass shadow-xl">
          <CardContent className="p-6 sm:p-8">
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="space-y-2">
                <Label>Full name</Label>
                <Input
                  placeholder="Jane Doe"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label>Phone number</Label>
                <Input
                  type="tel"
                  placeholder="+1 (555) 999-9999"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  required
                />
              </div>
              <Button
                type="submit"
                size="lg"
                className="w-full text-base font-semibold"
                disabled={isLoading || !name || !phone}
              >
                {isLoading ? "Confirming…" : "Confirm appointment"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
