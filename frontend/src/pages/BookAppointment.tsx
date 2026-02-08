import { useEffect, useCallback } from "react";
import { useCampaign } from "@/hooks/useCampaign";
import { useGoogleAuth } from "@/hooks/useGoogleAuth";
import { SearchForm } from "@/components/SearchForm";
import { ProviderSelection } from "@/components/ProviderSelection";
import { CampaignProgress } from "@/components/CampaignProgress";
import { AgentResults } from "@/components/AgentResults";
import { BookingSuccess } from "@/components/BookingSuccess";
import { ResultsList } from "@/components/ResultsList";
import { ConfirmSlot } from "@/components/ConfirmSlot";
import { ConfirmationSuccess } from "@/components/ConfirmationSuccess";
import { GoogleCalendarButton } from "@/components/GoogleCalendarButton";
import { toast } from "sonner";
import callpilotLogo from "@/assets/callpilot-logo.png";

const BookAppointment = () => {
  const campaign = useCampaign();
  const google = useGoogleAuth();
  const handleBooked = useCallback(() => {
    campaign.navigateToSuccess();
  }, [campaign]);

  useEffect(() => {
    if (google.justConnected) {
      toast.success("Google Calendar linked successfully");
    }
  }, [google.justConnected]);

  useEffect(() => {
    if (google.oauthError) {
      toast.error(google.oauthError);
      google.clearOauthError();
    }
  }, [google.oauthError]);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border/50 bg-card/60 backdrop-blur-lg sticky top-0 z-40">
        <div className="mx-auto flex h-16 max-w-2xl items-center justify-between px-4">
          <div className="flex items-center gap-2.5">
            <img src={callpilotLogo} alt="CallPilot" className="h-8 w-8 rounded-lg" />
            <span className="text-lg font-bold tracking-tight font-display">
              CallPilot
            </span>
          </div>
          <div className="flex items-center gap-3">
            <GoogleCalendarButton
              isConnected={google.isConnected}
              isLoading={google.isLoading}
              onConnect={google.connect}
              onDisconnect={google.disconnect}
              variant="compact"
            />
            <StepIndicator step={campaign.step} />
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="mx-auto max-w-2xl px-4 py-10 sm:py-16">
        {/* Error banner */}
        {campaign.error && (
          <div className="mb-6 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            {campaign.error}
            <button
              onClick={() => campaign.setError(null)}
              className="ml-2 underline hover:no-underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {campaign.step === "search" && (
          <SearchForm
            onSubmit={campaign.searchProviders}
            isLoading={campaign.isLoading}
          />
        )}

        {campaign.step === "providers" && (
          <ProviderSelection
            providers={campaign.providers}
            onContinue={campaign.startCampaign}
            onBack={campaign.goBack}
            isLoading={campaign.isLoading}
            autoBook={campaign.autoBook}
            onAutoBookChange={campaign.setAutoBook}
          />
        )}

        {campaign.step === "polling" && (
          <CampaignProgress status={campaign.status} onCancel={campaign.reset} />
        )}

        {campaign.step === "agent-results" && campaign.status && (
          <AgentResults
            status={campaign.status}
            onBooked={handleBooked}
          />
        )}

        {campaign.step === "results" && campaign.status && (
          <ResultsList
            status={campaign.status}
            onSelect={campaign.selectSlot}
            onBack={campaign.goBack}
          />
        )}

        {campaign.step === "confirm" && campaign.selectedSlot && (
          <ConfirmSlot
            slot={campaign.selectedSlot}
            onConfirm={campaign.confirmSlot}
            onBack={campaign.goBack}
            isLoading={campaign.isLoading}
          />
        )}

        {campaign.step === "success" && campaign.booking && (
          <BookingSuccess
            booking={campaign.booking}
            onReset={campaign.reset}
          />
        )}

        {campaign.step === "success" && !campaign.booking && campaign.confirmation && (
          <ConfirmationSuccess
            confirmation={campaign.confirmation}
            onReset={campaign.reset}
          />
        )}
      </main>
    </div>
  );
};

function StepIndicator({ step }: { step: string }) {
  const steps = [
    { key: "search", label: "Search" },
    { key: "providers", label: "Providers" },
    { key: "polling", label: "Calling" },
    { key: "agent-results", label: "Results" },
    { key: "confirm", label: "Confirm" },
    { key: "success", label: "Done" },
  ];

  const currentIndex = steps.findIndex((s) => s.key === step);

  return (
    <div className="flex items-center gap-1.5">
      {steps.map((s, i) => (
        <div
          key={s.key}
          className={`h-1.5 rounded-full transition-all duration-300 ${
            i <= currentIndex
              ? "w-6 bg-primary"
              : "w-1.5 bg-border"
          }`}
          title={s.label}
        />
      ))}
    </div>
  );
}

export default BookAppointment;
