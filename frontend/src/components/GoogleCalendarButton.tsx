import { Button } from "@/components/ui/button";
import { Calendar, Check, Loader2, LogOut } from "lucide-react";
import { toast } from "sonner";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

interface GoogleCalendarButtonProps {
  isConnected: boolean;
  isLoading: boolean;
  onConnect: () => Promise<void>;
  onDisconnect: () => void;
  variant?: "default" | "compact";
}

export function GoogleCalendarButton({
  isConnected,
  isLoading,
  onConnect,
  onDisconnect,
  variant = "default",
}: GoogleCalendarButtonProps) {
  const handleConnect = async () => {
    try {
      await onConnect();
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to start Google sign-in"
      );
    }
  };

  const handleDisconnect = () => {
    onDisconnect();
    toast.success("Google Calendar disconnected");
  };

  if (isConnected) {
    return (
      <Popover>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            size={variant === "compact" ? "sm" : "default"}
            className="gap-2 border-success/30 text-success cursor-pointer"
          >
            <Check className="h-4 w-4" />
            {variant === "compact" ? "Calendar" : "Google Calendar connected"}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-48 p-2 z-50 bg-popover" align="end">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start gap-2 text-destructive hover:text-destructive"
            onClick={handleDisconnect}
          >
            <LogOut className="h-4 w-4" />
            Disconnect
          </Button>
        </PopoverContent>
      </Popover>
    );
  }

  return (
    <Button
      variant="outline"
      size={variant === "compact" ? "sm" : "default"}
      className="gap-2"
      onClick={handleConnect}
      disabled={isLoading}
    >
      {isLoading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <Calendar className="h-4 w-4" />
      )}
      {variant === "compact"
        ? "Connect"
        : "Connect Google Calendar"}
    </Button>
  );
}
