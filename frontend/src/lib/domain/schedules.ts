export type ScheduleAction = "lock" | "unlock";
export type ScheduleScope = "owner" | "global";
export type ScheduleRecurrenceType = "one_shot" | "daily" | "weekly" | "monthly";

export interface ScheduleWindow {
  start: string; // ISO 8601 timestamp
  end: string;   // ISO 8601 timestamp
}

export interface ScheduleRecurrence {
  type: ScheduleRecurrenceType;
  interval?: number;            // every N units (default 1)
  daysOfWeek?: string[];        // ["Mon", "Tue", ...] for weekly
  dayOfMonth?: number;          // 1-31 for monthly
  until?: string | null;        // ISO timestamp limiting recurrence
}

export interface ScheduleException {
  date: string;                 // ISO date (YYYY-MM-DD)
  reason?: string;
  skip?: boolean;               // true to skip entirely
  overrideWindow?: ScheduleWindow; // optional window override
}

export interface ScheduleTarget {
  devices: string[];            // MAC addresses
  tags: string[];               // label/group identifiers
}

export interface DeviceSchedule {
  id: string;
  scope: ScheduleScope;
  ownerKey?: string;            // required when scope === "owner"
  label: string;
  description?: string;
  targets: ScheduleTarget;
  action: ScheduleAction;
  endAction?: ScheduleAction;
  window: ScheduleWindow;
  recurrence: ScheduleRecurrence;
  exceptions: ScheduleException[];
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface ScheduleMetadata {
  timezone: string;
  generatedAt: string;
}

export interface ScheduleConfig {
  metadata: ScheduleMetadata;
  schedules: DeviceSchedule[];
}

export interface CreateScheduleInput {
  scope: ScheduleScope;
  ownerKey?: string;
  label: string;
  description?: string;
  targets: ScheduleTarget;
  action: ScheduleAction;
  endAction?: ScheduleAction;
  window: ScheduleWindow;
  recurrence: ScheduleRecurrence;
  exceptions?: ScheduleException[];
  enabled?: boolean;
}

export interface OwnerScheduleSnapshot {
  metadata: ScheduleMetadata;
  ownerSchedules: DeviceSchedule[];
  globalSchedules: DeviceSchedule[];
}
