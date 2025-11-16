import { UnifiApiClient } from "@/lib/api/client";
import {
  mapSchedule,
  mapScheduleGroupEntry,
  mapScheduleGroups,
  mapScheduleMetadata,
  mapScheduleTarget,
} from "@/lib/api/transformers";
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
import type { SchedulePort } from "@/lib/ports/SchedulePort";

export class ApiScheduleAdapter implements SchedulePort {
  private readonly client: UnifiApiClient;

  constructor(baseUrl?: string) {
    this.client = new UnifiApiClient(baseUrl);
  }

  async loadConfig(): Promise<ScheduleConfig> {
    const response = await this.client.listSchedules();
    return {
      metadata: mapScheduleMetadata(response.metadata),
      schedules: response.schedules.map(mapSchedule)
    };
  }

  async loadOwnerSchedules(ownerKey: string): Promise<OwnerScheduleSnapshot> {
    const response = await this.client.getOwnerSchedules(ownerKey);
    return {
      metadata: mapScheduleMetadata(response.metadata),
      ownerSchedules: response.ownerSchedules.map(mapSchedule),
      globalSchedules: response.globalSchedules.map(mapSchedule)
    };
  }

  async loadGroups(ownerKey: string): Promise<ScheduleGroupList> {
    const response = await this.client.getScheduleGroups(ownerKey);
    return mapScheduleGroups(response);
  }

  async createSchedule(input: CreateScheduleInput): Promise<DeviceSchedule> {
    const payload = {
      scope: input.scope,
      ownerKey: input.ownerKey,
      groupId: input.groupId,
      label: input.label,
      description: input.description,
      targets: mapScheduleTarget(input.targets),
      action: input.action,
      endAction: input.endAction,
      window: {
        start: input.window.start,
        end: input.window.end
      },
      recurrence: input.recurrence,
      exceptions: input.exceptions ?? [],
      enabled: input.enabled ?? true
    };

    const schedule = await this.client.createSchedule(payload);
    return mapSchedule(schedule);
  }

  async deleteSchedule(scheduleId: string): Promise<void> {
    await this.client.deleteSchedule(scheduleId);
  }

  async cloneSchedule(scheduleId: string, targetOwner: string): Promise<DeviceSchedule> {
    const schedule = await this.client.cloneSchedule(scheduleId, { targetOwner });
    return mapSchedule(schedule);
  }

  async copyOwnerSchedules(
    sourceOwner: string,
    targetOwner: string,
    mode: "merge" | "replace"
  ): Promise<{ created: DeviceSchedule[]; replacedCount: number }> {
    const response = await this.client.copyOwnerSchedules(sourceOwner, {
      targetOwner,
      mode
    });
    return {
      created: response.created.map(mapSchedule),
      replacedCount: response.replacedCount
    };
  }

  async createGroup(input: CreateScheduleGroupInput): Promise<ScheduleGroup> {
    const apiGroup = await this.client.createScheduleGroup({
      name: input.name,
      ownerKey: input.ownerKey,
      description: input.description,
      scheduleIds: input.scheduleIds,
      activeScheduleId: input.activeScheduleId
    });
    return mapScheduleGroupEntry(apiGroup);
  }

  async updateGroup(input: UpdateScheduleGroupInput): Promise<ScheduleGroup> {
    const { groupId, ...rest } = input;
    const apiGroup = await this.client.updateScheduleGroup(groupId, {
      name: rest.name,
      description: rest.description,
      scheduleIds: rest.scheduleIds,
      activeScheduleId: rest.activeScheduleId
    });
    return mapScheduleGroupEntry(apiGroup);
  }

  async deleteGroup(groupId: string): Promise<void> {
    await this.client.deleteScheduleGroup(groupId);
  }

  async activateGroup(groupId: string, scheduleId: string): Promise<ScheduleGroup> {
    const apiGroup = await this.client.activateScheduleGroup(groupId, { scheduleId });
    return mapScheduleGroupEntry(apiGroup);
  }
}
