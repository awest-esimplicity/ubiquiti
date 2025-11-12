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
