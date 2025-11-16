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

export interface OwnerInfo {
  key: string;
  displayName: string;
}

export interface OwnerListResponse {
  owners: OwnerInfo[];
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

export interface DeviceTrafficSampleResponse {
  timestamp: string;
  rx_bytes: number;
  tx_bytes: number;
  total_bytes: number;
}

export interface DeviceTrafficSummaryResponse {
  interval_minutes: number;
  start?: string | null;
  end?: string | null;
  total_rx_bytes: number;
  total_tx_bytes: number;
  samples: DeviceTrafficSampleResponse[];
}

export type ApiDeviceConnection = "wired" | "wireless" | "unknown";

export interface DeviceDetailResponse {
  name: string;
  owner: string;
  type: string;
  mac: string;
  locked: boolean;
  vendor?: string | null;
  ip?: string | null;
  last_seen?: string | null;
  connection: ApiDeviceConnection;
  access_point?: string | null;
  signal?: number | null;
  online: boolean;
  network_name?: string | null;
  traffic?: DeviceTrafficSummaryResponse | null;
  destinations?: string[] | null;
  dpi_applications?: DeviceDPIEntryResponse[] | null;
}

export interface DeviceDPIEntryResponse {
  application: string;
  category?: string | null;
  rx_bytes: number;
  tx_bytes: number;
}

export interface AuditEventResponse {
  id?: number | null;
  timestamp: string;
  action: string;
  actor?: string | null;
  subject_type: string;
  subject_id?: string | null;
  reason?: string | null;
  metadata?: Record<string, unknown>;
}

export interface EventListResponse {
  events: AuditEventResponse[];
}

export interface DeviceRegistrationRequest {
  mac: string;
  name?: string | null;
  type?: string | null;
}

export interface OwnerCreateRequest {
  displayName: string;
  pin: string;
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

export interface WhoAmIResponse {
  ip?: string | null;
  forwardedFor: string[];
  probableClients: UnregisteredClient[];
}

export interface DeviceTypesResponse {
  types: string[];
}

export interface DeviceTypeCreateRequest {
  name: string;
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
  groupId?: string | null;
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
  groupId?: string | null;
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

export interface ApiScheduleGroup {
  id: string;
  ownerKey?: string | null;
  name: string;
  description?: string | null;
  activeScheduleId?: string | null;
  createdAt: string;
  updatedAt: string;
  schedules: ApiDeviceSchedule[];
}

export interface ApiScheduleGroupListResponse {
  ownerGroups: ApiScheduleGroup[];
  globalGroups: ApiScheduleGroup[];
}

export interface ApiScheduleGroupCreateRequest {
  name: string;
  ownerKey?: string | null;
  description?: string | null;
  scheduleIds: string[];
  activeScheduleId?: string | null;
}

export interface ApiScheduleGroupUpdateRequest {
  name?: string;
  description?: string | null;
  scheduleIds?: string[];
  activeScheduleId?: string | null;
}

export interface ApiScheduleGroupActivateRequest {
  scheduleId: string;
}

export interface ApiScheduleCloneRequest {
  targetOwner: string;
}

export interface ApiScheduleCloneResponse {
  schedule: ApiDeviceSchedule;
}

export interface ApiOwnerScheduleCopyRequest {
  targetOwner: string;
  mode?: "merge" | "replace";
}

export interface ApiOwnerScheduleCopyResponse {
  sourceOwner: string;
  targetOwner: string;
  mode: "merge" | "replace";
  created: ApiDeviceSchedule[];
  replacedCount: number;
}
