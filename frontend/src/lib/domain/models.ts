export type DeviceType = string;

export interface Device {
  name: string;
  type: DeviceType;
  mac: string;
  vendor?: string;
  locked: boolean;
}

export type DeviceConnectionType = "wired" | "wireless" | "unknown";

export interface DeviceTrafficSample {
  timestamp: string;
  rxBytes: number;
  txBytes: number;
  totalBytes: number;
}

export interface DeviceTrafficSummary {
  intervalMinutes: number;
  start?: string;
  end?: string;
  totalRxBytes: number;
  totalTxBytes: number;
  samples: DeviceTrafficSample[];
}

export interface DeviceDetail extends Device {
  owner: string;
  ip?: string;
  lastSeen?: string;
  connection: DeviceConnectionType;
  accessPoint?: string;
  signal?: number;
  online: boolean;
  networkName?: string;
  traffic?: DeviceTrafficSummary | null;
}

export interface DeviceRegistrationPayload {
  mac: string;
  name?: string;
  type?: string;
}

export interface OwnerSummary {
  key: string;
  displayName: string;
  pin?: string | null;
  devices: Device[];
}

export interface UnregisteredDevice {
  name: string;
  mac: string;
  ip?: string;
  vendor?: string;
  locked: boolean;
  lastSeen?: string;
}

export interface DashboardMetadata {
  totalDevices: number;
  lockedDevices: number;
  unknownVendors: number;
  lastSync: string;
}

export interface DashboardSnapshot {
  owners: OwnerSummary[];
  unregistered: UnregisteredDevice[];
  metadata: DashboardMetadata;
}

export interface SessionIdentity {
  ip?: string | null;
  forwardedFor: string[];
  probableClients: UnregisteredDevice[];
}
