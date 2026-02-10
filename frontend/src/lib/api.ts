import type {
  CampaignRequest,
  CampaignStartResponse,
  CampaignStatus,
  ConfirmRequest,
  ConfirmResponse,
  ProviderSearchRequest,
  ProviderSearchResponse,
} from "@/types/campaign";

const API_BASE = "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "ngrok-skip-browser-warning": "true",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }

  return res.json();
}

export const api = {
  healthCheck: () => request<{ ok: boolean }>("/health"),

  searchProviders: (data: ProviderSearchRequest) =>
    request<ProviderSearchResponse>("/providers/search", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  startCampaign: (data: CampaignRequest) =>
    request<CampaignStartResponse>("/campaigns", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getCampaignStatus: (campaignId: string) =>
    request<CampaignStatus>(`/campaigns/${campaignId}`),

  confirmSlot: (campaignId: string, data: ConfirmRequest) =>
    request<ConfirmResponse>(`/campaigns/${campaignId}/confirm`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  googleAuthorize: (userId: string) =>
    request<{ authorize_url: string }>(
      `/auth/google/authorize?user_id=${encodeURIComponent(userId)}`
    ),
};
