import type {
  ApiOwnerSummary,
  DashboardSummary,
  DeviceStatus,
  UnregisteredClient
} from "@/lib/api/types";
import type { DashboardMetadata, Device, OwnerSummary, UnregisteredDevice } from "@/lib/domain/models";

function toDeviceType(value: string): Device["type"] {
  const normalized = value.toLowerCase();
  const allowed: Device["type"][] = [
    "computer",
    "tv",
    "switch",
    "streaming",
    "console",
    "phone",
    "tablet",
    "unknown"
  ];
  if (allowed.includes(normalized as Device["type"])) {
    return normalized as Device["type"];
  }
  return "unknown";
}

export function mapDevice(apiDevice: DeviceStatus): Device {
  return {
    name: apiDevice.name,
    type: toDeviceType(apiDevice.type),
    mac: apiDevice.mac,
    vendor: apiDevice.vendor ?? undefined,
    locked: apiDevice.locked
  };
}

export function mapOwner(
  summary: ApiOwnerSummary,
  devices: DeviceStatus[],
  pin?: string | null
): OwnerSummary {
  return {
    key: summary.key,
    displayName: summary.display_name,
    pin: pin ?? undefined,
    devices: devices.map(mapDevice)
  };
}

export function mapMetadata(summary: DashboardSummary): DashboardMetadata {
  return {
    totalDevices: summary.total_devices,
    lockedDevices: summary.locked_devices,
    unknownVendors: summary.unknown_vendors,
    lastSync: summary.generated_at
  };
}

export function mapUnregistered(client: UnregisteredClient): UnregisteredDevice {
  return {
    name: client.name,
    mac: client.mac,
    ip: client.ip ?? undefined,
    vendor: client.vendor ?? undefined,
    lastSeen: client.last_seen ?? undefined,
    locked: client.locked
  };
}
