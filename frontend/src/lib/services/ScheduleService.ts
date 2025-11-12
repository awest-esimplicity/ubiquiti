import type {
  CreateScheduleInput,
  DeviceSchedule,
  ScheduleAction,
  ScheduleRecurrence,
  ScheduleTarget,
  OwnerScheduleSnapshot
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
}
