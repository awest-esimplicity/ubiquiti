import type {
  ApiDeviceSchedule,
  ApiOwnerSummary,
  ApiScheduleMetadata,
  ApiScheduleTarget,
  DashboardSummary,
  DeviceDetailResponse,
  DeviceStatus,
  DeviceTrafficSampleResponse,
  DeviceTrafficSummaryResponse,
  UnregisteredClient,
} from "@/lib/api/types";
import type {
  DashboardMetadata,
  Device,
  DeviceDetail,
  OwnerSummary,
  UnregisteredDevice,
  DeviceTrafficSample,
  DeviceTrafficSummary,
} from "@/lib/domain/models";
import type { DeviceSchedule, ScheduleMetadata, ScheduleTarget } from "@/lib/domain/schedules";

function normaliseDeviceType(value: string | null | undefined): Device["type"] {
  const trimmed = value?.trim();
  if (!trimmed) {
    return "unknown";
  }
  return trimmed;
}

export function mapDevice(apiDevice: DeviceStatus): Device {
  return {
    name: apiDevice.name,
    type: normaliseDeviceType(apiDevice.type),
    mac: apiDevice.mac,
    vendor: apiDevice.vendor ?? undefined,
    locked: apiDevice.locked,
  };
}

export function mapOwner(
  summary: ApiOwnerSummary,
  devices: DeviceStatus[],
  pin?: string | null,
): OwnerSummary {
  return {
    key: summary.key,
    displayName: summary.display_name,
    pin: pin ?? undefined,
    devices: devices.map(mapDevice),
  };
}

function mapTrafficSample(sample: DeviceTrafficSampleResponse): DeviceTrafficSample {
  return {
    timestamp: sample.timestamp,
    rxBytes: sample.rx_bytes,
    txBytes: sample.tx_bytes,
    totalBytes: sample.total_bytes,
  };
}

function mapTrafficSummary(summary: DeviceTrafficSummaryResponse | null | undefined): DeviceTrafficSummary | null {
  if (!summary) {
    return null;
  }

  return {
    intervalMinutes: summary.interval_minutes,
    start: summary.start ?? undefined,
    end: summary.end ?? undefined,
    totalRxBytes: summary.total_rx_bytes,
    totalTxBytes: summary.total_tx_bytes,
    samples: (summary.samples ?? []).map(mapTrafficSample),
  };
}

export function mapDeviceDetail(detail: DeviceDetailResponse): DeviceDetail {
  return {
    name: detail.name,
    type: normaliseDeviceType(detail.type),
    mac: detail.mac,
    vendor: detail.vendor ?? undefined,
    locked: detail.locked,
    owner: detail.owner,
    ip: detail.ip ?? undefined,
    lastSeen: detail.last_seen ?? undefined,
    connection: detail.connection,
    accessPoint: detail.access_point ?? undefined,
    signal: detail.signal ?? undefined,
    online: detail.online,
    networkName: detail.network_name ?? undefined,
    traffic: mapTrafficSummary(detail.traffic),
  };
}

export function mapMetadata(summary: DashboardSummary): DashboardMetadata {
  return {
    totalDevices: summary.total_devices,
    lockedDevices: summary.locked_devices,
    unknownVendors: summary.unknown_vendors,
    lastSync: summary.generated_at,
  };
}

export function mapUnregistered(client: UnregisteredClient): UnregisteredDevice {
  return {
    name: client.name,
    mac: client.mac,
    ip: client.ip ?? undefined,
    vendor: client.vendor ?? undefined,
    lastSeen: client.last_seen ?? undefined,
    locked: client.locked,
  };
}

export function mapScheduleMetadata(metadata: ApiScheduleMetadata): ScheduleMetadata {
  return {
    timezone: metadata.timezone,
    generatedAt: metadata.generatedAt,
  };
}

export function mapScheduleTarget(target: ScheduleTarget): ApiScheduleTarget {
  return {
    devices: target.devices ?? [],
    tags: target.tags ?? [],
  };
}

export function mapSchedule(schedule: ApiDeviceSchedule): DeviceSchedule {
  return {
    id: schedule.id,
    scope: schedule.scope,
    ownerKey: schedule.ownerKey ?? undefined,
    label: schedule.label,
    description: schedule.description ?? undefined,
    targets: {
      devices: schedule.targets?.devices ?? [],
      tags: schedule.targets?.tags ?? [],
    },
    action: schedule.action,
    endAction: schedule.endAction ?? undefined,
    window: {
      start: schedule.window.start,
      end: schedule.window.end,
    },
    recurrence: {
      type: schedule.recurrence.type,
      interval: schedule.recurrence.interval ?? 1,
      daysOfWeek: schedule.recurrence.daysOfWeek ?? undefined,
      dayOfMonth: schedule.recurrence.dayOfMonth ?? undefined,
      until: schedule.recurrence.until ?? undefined,
    },
    exceptions: (schedule.exceptions ?? []).map((exception) => ({
      date: exception.date,
      reason: exception.reason ?? undefined,
      skip: exception.skip ?? undefined,
      overrideWindow: exception.overrideWindow
        ? {
            start: exception.overrideWindow.start,
            end: exception.overrideWindow.end,
          }
        : undefined,
    })),
    enabled: schedule.enabled,
    createdAt: schedule.createdAt,
    updatedAt: schedule.updatedAt,
  };
}
