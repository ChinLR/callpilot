import { useState, useRef, useCallback } from "react";
import { api } from "@/lib/api";
import type {
  CampaignRequest,
  CampaignStatus,
  BookingDetails,
  ConfirmRequest,
  ConfirmResponse,
  Provider,
  ProviderSearchRequest,
  ProviderSlot,
  AppStep,
} from "@/types/campaign";

interface SearchParams {
  service: string;
  location: string;
  dateRangeStart: string;
  dateRangeEnd: string;
  durationMin: number;
  maxTravelMinutes?: number;
  clientName: string;
}

export function useCampaign() {
  const [step, setStep] = useState<AppStep>("search");
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [status, setStatus] = useState<CampaignStatus | null>(null);
  const [confirmation, setConfirmation] = useState<ConfirmResponse | null>(null);
  const [booking, setBooking] = useState<BookingDetails | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<ProviderSlot | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [searchParams, setSearchParams] = useState<SearchParams | null>(null);
  const [autoBook, setAutoBook] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  // Step 1: Search for providers
  const searchProviders = useCallback(
    async (params: SearchParams) => {
      setError(null);
      setIsLoading(true);
      setSearchParams(params);

      try {
        const req: ProviderSearchRequest = {
          service: params.service,
          location: params.location,
          max_travel_minutes: params.maxTravelMinutes,
        };

        const res = await api.searchProviders(req);
        const providerList = Array.isArray(res?.providers) ? res.providers : [];
        if (providerList.length === 0) {
          setError("No providers found. Try expanding your search.");
          return;
        }
        setProviders(providerList);
        setStep("providers");
      } catch (err) {
        console.error("Provider search failed:", err);
        setError(err instanceof Error ? err.message : "Failed to search providers");
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  // Step 2: Start campaign with selected providers
  const startCampaign = useCallback(
    async (providerIds: string[]) => {
      if (!searchParams) return;

      setError(null);
      setIsLoading(true);
      setStep("polling");

      try {
        const req: CampaignRequest = {
          provider_ids: providerIds,
          service: searchParams.service,
          location: searchParams.location,
          date_range_start: searchParams.dateRangeStart,
          date_range_end: searchParams.dateRangeEnd,
          duration_min: searchParams.durationMin,
          max_parallel: 5,
          auto_book: autoBook,
          client_name: searchParams.clientName,
          preferences: {},
        };

        const res = await api.startCampaign(req);
        setCampaignId(res.campaign_id);

        // Start polling
        let pollCount = 0;
        const maxPolls = 60; // 2.5 minutes max

        pollingRef.current = setInterval(async () => {
          pollCount++;

          if (pollCount > maxPolls) {
            stopPolling();
            setError("Search timed out. Please try again.");
            setStep("search");
            return;
          }

          try {
            const poll = await api.getCampaignStatus(res.campaign_id);
            setStatus(poll);

            if (poll.status === "booking") {
              // Discovery done, agent is booking — show agent results
              setStep("agent-results");
            } else if (poll.status === "booked") {
              // Auto-booked successfully — show in agent results, it will auto-navigate
              stopPolling();
              setBooking(poll.booking);
              setStep("agent-results");
            } else if (poll.status === "completed") {
              // auto_book=false or booking failed → manual slot picker
              stopPolling();
              setTimeout(() => setStep("results"), 1800);
            } else if (poll.status === "failed") {
              stopPolling();
              setError("Campaign failed. Please try again.");
              setStep("search");
            }
          } catch (err) {
            stopPolling();
            setError(err instanceof Error ? err.message : "Polling failed");
            setStep("search");
          }
        }, 1000);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to start campaign");
        setStep("providers");
      } finally {
        setIsLoading(false);
      }
    },
    [searchParams, autoBook, stopPolling]
  );

  const selectSlot = useCallback((slot: ProviderSlot) => {
    setSelectedSlot(slot);
    setStep("confirm");
  }, []);

  const confirmSlot = useCallback(
    async (contact: ConfirmRequest["user_contact"]) => {
      if (!campaignId || !selectedSlot) return;
      setError(null);
      setIsLoading(true);
      try {
        const res = await api.confirmSlot(campaignId, {
          provider_id: selectedSlot.provider_id,
          start: selectedSlot.start,
          end: selectedSlot.end,
          user_contact: contact,
        });
        setConfirmation(res);
        setStep("success");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Confirmation failed");
      } finally {
        setIsLoading(false);
      }
    },
    [campaignId, selectedSlot]
  );

  const reset = useCallback(() => {
    stopPolling();
    setStep("search");
    setCampaignId(null);
    setStatus(null);
    setConfirmation(null);
    setBooking(null);
    setSelectedSlot(null);
    setProviders([]);
    setSearchParams(null);
    setAutoBook(true);
    setError(null);
    setIsLoading(false);
  }, [stopPolling]);

  const goBack = useCallback(() => {
    if (step === "confirm") {
      setSelectedSlot(null);
      setStep("results");
    } else if (step === "results") {
      setStep("providers");
    } else if (step === "providers") {
      reset();
    }
  }, [step, reset]);

  const navigateToSuccess = useCallback(() => {
    setStep("success");
  }, []);

  return {
    step,
    campaignId,
    status,
    confirmation,
    booking,
    selectedSlot,
    providers,
    autoBook,
    error,
    isLoading,
    searchProviders,
    startCampaign,
    selectSlot,
    confirmSlot,
    reset,
    goBack,
    navigateToSuccess,
    setError,
    setAutoBook,
  };
}
