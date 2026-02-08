import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CheckCircle2, Copy, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import type { ConfirmResponse } from "@/types/campaign";

interface ConfirmationSuccessProps {
  confirmation: ConfirmResponse;
  onReset: () => void;
}

export function ConfirmationSuccess({ confirmation, onReset }: ConfirmationSuccessProps) {
  const copyRef = () => {
    navigator.clipboard.writeText(confirmation.confirmation_ref);
    toast.success("Reference copied to clipboard");
  };

  return (
    <div className="animate-slide-up text-center">
      <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-success/10">
        <CheckCircle2 className="h-10 w-10 text-success" />
      </div>

      <h2 className="mb-2 text-3xl font-bold tracking-tight font-display">
        You're all set!
      </h2>
      <p className="mb-8 text-muted-foreground">
        Your appointment has been confirmed.
      </p>

      <Card className="glass shadow-xl mx-auto max-w-sm">
        <CardContent className="p-6">
          <p className="mb-1 text-sm text-muted-foreground">Confirmation reference</p>
          <button
            onClick={copyRef}
            className="group flex w-full items-center justify-center gap-2 rounded-lg bg-secondary/60 px-4 py-3 font-mono text-lg font-bold tracking-widest transition-colors hover:bg-secondary"
          >
            {confirmation.confirmation_ref}
            <Copy className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
          </button>
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
