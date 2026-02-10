// Provider search types
export interface ProviderSearchRequest {
  service: string;
  location: string;
  lat?: number;
  lng?: number;
  max_travel_minutes?: number;
}

export interface Provider {
  id: string;
  name: string;
  phone: string;
  address: string;
  rating: number;
  lat?: number;
  lng?: number;
  services?: string[];
  travel_minutes?: number;
}

export interface ProviderSearchResponse {
  providers: Provider[];
}

// Campaign types
export interface CampaignRequest {
  provider_ids: string[];
  service: string;
  location: string;
  date_range_start: string;
  date_range_end: string;
  duration_min: number;
  max_parallel?: number;
  auto_book?: boolean;
  client_name?: string;
  preferences?: Record<string, unknown>;
}

export interface CampaignStartResponse {
  campaign_id: string;
  status: string;
}

export interface CampaignProgress {
  total_providers: number;
  completed_calls: number;
  successful_calls: number;
  failed_calls: number;
  calls_in_progress: number;
}

export interface ProviderSlot {
  provider_id: string;
  provider_name?: string;
  start: string;
  end: string;
  score: number;
}

export interface BookingDetails {
  provider_id: string;
  start: string;
  end: string;
  confirmation_ref: string;
  confirmed_at: string;
  client_name?: string;
  notes?: string;
}

export interface ProviderDebugInfo {
  name: string;
  rating: number;
  address: string;
}

export interface ScoringBreakdown {
  earliest: number;
  rating: number;
  distance: number;
  preference: number;
  weights: {
    earliest: number;
    rating: number;
    distance: number;
    preference: number;
  };
  raw_score: number;
  relative_score: number;
}

export interface CampaignDebug {
  providers?: Record<string, ProviderDebugInfo>;
  scoring?: Record<string, ScoringBreakdown[]>;
  provider_outcomes?: Record<string, string>;
}

export interface CampaignStatus {
  campaign_id: string;
  status: "running" | "booking" | "booked" | "completed" | "failed";
  progress: CampaignProgress;
  best: ProviderSlot | null;
  ranked: ProviderSlot[];
  booking: BookingDetails | null;
  debug: CampaignDebug;
}

export interface ConfirmRequest {
  provider_id: string;
  start: string;
  end: string;
  user_contact: {
    name: string;
    phone: string;
  };
}

export interface ConfirmResponse {
  campaign_id: string;
  confirmed: boolean;
  confirmation_ref: string;
}

export type AppStep = "search" | "providers" | "polling" | "agent-results" | "results" | "confirm" | "success";
