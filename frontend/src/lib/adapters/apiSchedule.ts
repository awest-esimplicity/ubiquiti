import { UnifiApiClient } from "@/lib/api/client";
import {
  mapSchedule,
  mapScheduleMetadata,
  mapScheduleTarget
} from "@/lib/api/transformers";
import type {
  CreateScheduleInput,
  DeviceSchedule,
  OwnerScheduleSnapshot,
  ScheduleConfig
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

  async createSchedule(input: CreateScheduleInput): Promise<DeviceSchedule> {
    const payload = {
      scope: input.scope,
      ownerKey: input.ownerKey,
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
}
