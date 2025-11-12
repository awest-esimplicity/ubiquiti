import type {
  CreateScheduleInput,
  DeviceSchedule,
  ScheduleConfig
} from "@/lib/domain/schedules";

export interface SchedulePort {
  loadConfig(): Promise<ScheduleConfig>;
  createSchedule(input: CreateScheduleInput): Promise<DeviceSchedule>;
}
