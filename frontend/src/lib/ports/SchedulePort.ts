import type {
  CreateScheduleGroupInput,
  CreateScheduleInput,
  DeviceSchedule,
  OwnerScheduleSnapshot,
  ScheduleConfig,
  ScheduleGroup,
  ScheduleGroupList,
  UpdateScheduleGroupInput,
} from "@/lib/domain/schedules";

export interface SchedulePort {
  loadConfig(): Promise<ScheduleConfig>;
  loadOwnerSchedules(ownerKey: string): Promise<OwnerScheduleSnapshot>;
  loadGroups(ownerKey: string): Promise<ScheduleGroupList>;
  createSchedule(input: CreateScheduleInput): Promise<DeviceSchedule>;
  deleteSchedule(scheduleId: string): Promise<void>;
  cloneSchedule(scheduleId: string, targetOwner: string): Promise<DeviceSchedule>;
  copyOwnerSchedules(
    sourceOwner: string,
    targetOwner: string,
    mode: "merge" | "replace"
  ): Promise<{ created: DeviceSchedule[]; replacedCount: number }>;
  createGroup(input: CreateScheduleGroupInput): Promise<ScheduleGroup>;
  updateGroup(input: UpdateScheduleGroupInput): Promise<ScheduleGroup>;
  deleteGroup(groupId: string): Promise<void>;
  activateGroup(groupId: string, scheduleId: string): Promise<ScheduleGroup>;
}
