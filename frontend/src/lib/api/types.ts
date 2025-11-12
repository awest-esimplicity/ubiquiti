export interface DashboardSummary {
  total_devices: number;
  locked_devices: number;
  unlocked_devices: number;
  owner_count: number;
  unknown_vendors: number;
  generated_at: string;
}

export interface OwnersResponse {
  owners: ApiOwnerSummary[];
}

export interface ApiOwnerSummary {
  key: string;
  display_name: string;
  total_devices: number;
  locked_devices: number;
  unlocked_devices: number;
}

export interface DeviceStatus {
  name: string;
  owner: string;
  type: string;
  mac: string;
  locked: boolean;
  vendor?: string | null;
}

export interface DeviceListResponse {
  devices: DeviceStatus[];
}

export interface UnregisteredClient {
  name: string;
  mac: string;
  ip?: string | null;
  vendor?: string | null;
  last_seen?: string | null;
  locked: boolean;
}

export interface UnregisteredClientsResponse {
  clients: UnregisteredClient[];
}

export interface DeviceTarget {
  mac: string;
  name?: string | null;
  owner?: string | null;
  type?: string | null;
}

export interface DeviceActionRequest {
  targets: DeviceTarget[];
  unlock?: boolean;
}

export interface OwnerLockRequest {
  unlock?: boolean;
}

export interface SingleClientLockRequest extends DeviceTarget {
  unlock?: boolean;
}

export interface VerifyPinResponse {
  valid: boolean;
}

export interface ApiScheduleWindow {
  start: string;
  end: string;
}

export interface ApiScheduleRecurrence {
  type: "one_shot" | "daily" | "weekly" | "monthly";
  interval?: number;
  daysOfWeek?: string[] | null;
  dayOfMonth?: number | null;
  until?: string | null;
}

export interface ApiScheduleException {
  date: string;
  reason?: string | null;
  skip?: boolean | null;
  overrideWindow?: ApiScheduleWindow | null;
}

export interface ApiScheduleTarget {
  devices?: string[];
  tags?: string[];
}

export interface ApiDeviceSchedule {
  id: string;
  scope: "owner" | "global";
  ownerKey?: string | null;
  label: string;
  description?: string | null;
  targets: ApiScheduleTarget;
  action: "lock" | "unlock";
  endAction?: "lock" | "unlock" | null;
  window: ApiScheduleWindow;
  recurrence: ApiScheduleRecurrence;
  exceptions?: ApiScheduleException[];
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface ApiScheduleMetadata {
  timezone: string;
  generatedAt: string;
}

export interface ApiScheduleListResponse {
  metadata: ApiScheduleMetadata;
  schedules: ApiDeviceSchedule[];
}

export interface ApiOwnerScheduleResponse {
  metadata: ApiScheduleMetadata;
  ownerSchedules: ApiDeviceSchedule[];
  globalSchedules: ApiDeviceSchedule[];
}

export interface ApiScheduleCreateRequest {
  scope: "owner" | "global";
  ownerKey?: string | null;
  label: string;
  description?: string | null;
  targets: ApiScheduleTarget;
  action: "lock" | "unlock";
  endAction?: "lock" | "unlock" | null;
  window: ApiScheduleWindow;
  recurrence: ApiScheduleRecurrence;
  exceptions?: ApiScheduleException[];
  enabled?: boolean;
}
