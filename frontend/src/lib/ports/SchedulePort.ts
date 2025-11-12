import type {
  CreateScheduleInput,
  DeviceSchedule,
  ScheduleConfig,
  OwnerScheduleSnapshot
} from "@/lib/domain/schedules";

export interface SchedulePort {
  loadConfig(): Promise<ScheduleConfig>;
  loadOwnerSchedules(ownerKey: string): Promise<OwnerScheduleSnapshot>;
  createSchedule(input: CreateScheduleInput): Promise<DeviceSchedule>;
  deleteSchedule(scheduleId: string): Promise<void>;
}
