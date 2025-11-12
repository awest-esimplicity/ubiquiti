import type {
  ApiDeviceSchedule,
  ApiOwnerScheduleResponse,
  ApiScheduleCreateRequest,
  ApiScheduleListResponse,
  DashboardSummary,
  DeviceActionRequest,
  DeviceListResponse,
  DeviceTarget,
  OwnerLockRequest,
  OwnersResponse,
  SingleClientLockRequest,
  UnregisteredClientsResponse,
  VerifyPinResponse
} from "@/lib/api/types";

type HttpMethod = "GET" | "POST" | "DELETE";

const env = import.meta.env as Record<string, string | undefined>;
const DEFAULT_BASE_URL = env.PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

interface RequestOptions<TBody> {
  method?: HttpMethod;
  body?: TBody;
  signal?: AbortSignal;
}

export class UnifiApiClient {
  constructor(private readonly baseUrl: string = DEFAULT_BASE_URL) {}

  private async request<TResponse, TBody = unknown>(
    path: string,
    { method = "GET", body, signal }: RequestOptions<TBody> = {}
  ): Promise<TResponse> {
    const url = path.startsWith("http") ? path : `${this.baseUrl}${path}`;
    const headers = new Headers({
      "Content-Type": "application/json"
    });

    const response = await fetch(url, {
      method,
      headers,
      signal,
      body: body ? JSON.stringify(body) : undefined
    });

    if (!response.ok) {
      let message = `Request to ${path} failed with status ${response.status}`;
      try {
        const errorPayload = (await response.json()) as unknown;
        if (
          typeof errorPayload === "object" &&
          errorPayload !== null &&
          "detail" in errorPayload &&
          typeof (errorPayload as { detail: unknown }).detail === "string"
        ) {
          message = (errorPayload as { detail: string }).detail;
        }
      } catch (error) {
        // ignore JSON parse issues, fallback to default message
      }
      throw new Error(message);
    }

    if (response.status === 204) {
      return undefined as TResponse;
    }

    const data = (await response.json()) as unknown;
    return data as TResponse;
  }

  async getDashboardSummary(signal?: AbortSignal): Promise<DashboardSummary> {
    return this.request<DashboardSummary>("/api/dashboard/summary", { signal });
  }

  async listOwnerSummaries(signal?: AbortSignal): Promise<OwnersResponse> {
    return this.request<OwnersResponse>("/api/owners", { signal });
  }

  async listOwnerDevices(ownerKey: string, signal?: AbortSignal): Promise<DeviceListResponse> {
    return this.request<DeviceListResponse>(`/api/owners/${ownerKey}/devices`, { signal });
  }

  async listUnregisteredClients(signal?: AbortSignal): Promise<UnregisteredClientsResponse> {
    return this.request<UnregisteredClientsResponse>("/api/clients/unregistered", { signal });
  }

  async lockDevices(targets: DeviceTarget[], unlock = false): Promise<void> {
    const payload: DeviceActionRequest = {
      targets,
      unlock
    };
    await this.request("/api/devices/lock", { method: "POST", body: payload });
  }

  async lockOwner(ownerKey: string, unlock = false): Promise<void> {
    const payload: OwnerLockRequest = { unlock };
    await this.request(`/api/owners/${ownerKey}/lock`, { method: "POST", body: payload });
  }

  async lockUnregisteredClient(target: DeviceTarget, unlock = false): Promise<void> {
    const payload: SingleClientLockRequest = {
      ...target,
      unlock
    };
    await this.request("/api/clients/unregistered/lock", { method: "POST", body: payload });
  }

  async verifyOwnerPin(ownerKey: string, pin: string): Promise<boolean> {
    const response = await this.request<VerifyPinResponse, { pin: string }>(
      `/api/owners/${ownerKey}/verify-pin`,
      {
        method: "POST",
        body: { pin }
      }
    );
    return response.valid;
  }

  async listSchedules(signal?: AbortSignal): Promise<ApiScheduleListResponse> {
    return this.request<ApiScheduleListResponse>("/api/schedules", { signal });
  }

  async getOwnerSchedules(ownerKey: string, signal?: AbortSignal): Promise<ApiOwnerScheduleResponse> {
    return this.request<ApiOwnerScheduleResponse>(`/api/owners/${ownerKey}/schedules`, { signal });
  }

  async createSchedule(payload: ApiScheduleCreateRequest): Promise<ApiDeviceSchedule> {
    return this.request<ApiDeviceSchedule, ApiScheduleCreateRequest>("/api/schedules", {
      method: "POST",
      body: payload
    });
  }

  async deleteSchedule(scheduleId: string): Promise<void> {
    await this.request(`/api/schedules/${scheduleId}`, {
      method: "DELETE"
    });
  }
}
