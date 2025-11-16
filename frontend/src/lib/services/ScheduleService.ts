import type {
  CreateScheduleGroupInput,
  CreateScheduleInput,
  DeviceSchedule,
  OwnerScheduleSnapshot,
  ScheduleAction,
  ScheduleGroup,
  ScheduleGroupList,
  ScheduleRecurrence,
  ScheduleTarget,
  UpdateScheduleGroupInput,
} from "@/lib/domain/schedules";
import type { SchedulePort } from "@/lib/ports/SchedulePort";

export interface CreateOwnerEventInput {
  label: string;
  description?: string;
  start: string;
  end: string;
  startAction: ScheduleAction;
  endAction: ScheduleAction;
  recurrence: ScheduleRecurrence;
  targets?: ScheduleTarget;
}

export class ScheduleService {
  constructor(private readonly port: SchedulePort) {}

  async getSchedulesForOwner(ownerKey: string): Promise<OwnerScheduleSnapshot> {
    return this.port.loadOwnerSchedules(ownerKey);
  }

  async getScheduleGroups(ownerKey: string): Promise<ScheduleGroupList> {
    return this.port.loadGroups(ownerKey);
  }

  async createEventForOwner(
    ownerKey: string,
    input: CreateOwnerEventInput
  ): Promise<DeviceSchedule> {
    const startISO = new Date(input.start).toISOString();
    const endISO = new Date(input.end).toISOString();

    const payload: CreateScheduleInput = {
      scope: "owner",
      ownerKey,
      label: input.label,
      description: input.description,
      targets:
        input.targets ??
        ({
          devices: [],
          tags: [ownerKey]
        } satisfies ScheduleTarget),
      action: input.startAction,
      endAction: input.endAction,
      window: {
        start: startISO,
        end: endISO
      },
      recurrence: input.recurrence,
      exceptions: [],
      enabled: true
    };

    return this.port.createSchedule(payload);
  }

  async deleteSchedule(scheduleId: string): Promise<void> {
    await this.port.deleteSchedule(scheduleId);
  }

  async cloneSchedule(scheduleId: string, targetOwner: string): Promise<DeviceSchedule> {
    return this.port.cloneSchedule(scheduleId, targetOwner);
  }

  async copyOwnerSchedules(
    sourceOwner: string,
    targetOwner: string,
    mode: "merge" | "replace"
  ): Promise<{ created: DeviceSchedule[]; replacedCount: number }> {
    return this.port.copyOwnerSchedules(sourceOwner, targetOwner, mode);
  }

  async createGroup(input: CreateScheduleGroupInput): Promise<ScheduleGroup> {
    return this.port.createGroup(input);
  }

  async updateGroup(input: UpdateScheduleGroupInput): Promise<ScheduleGroup> {
    return this.port.updateGroup(input);
  }

  async deleteGroup(groupId: string): Promise<void> {
    await this.port.deleteGroup(groupId);
  }

  async activateGroup(groupId: string, scheduleId: string): Promise<ScheduleGroup> {
    return this.port.activateGroup(groupId, scheduleId);
  }
}
