export type DeviceType = string;

export interface Device {
  name: string;
  type: DeviceType;
  mac: string;
  vendor?: string;
  locked: boolean;
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
