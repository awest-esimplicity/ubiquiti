import type {
  CreateScheduleInput,
  DeviceSchedule,
  ScheduleConfig,
  ScheduleAction,
  ScheduleRecurrence,
  ScheduleTarget
} from "@/lib/domain/schedules";
import type { SchedulePort } from "@/lib/ports/SchedulePort";

export interface OwnerScheduleResult {
  metadata: ScheduleConfig["metadata"];
  ownerSchedules: DeviceSchedule[];
  globalSchedules: DeviceSchedule[];
}

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

  async getSchedulesForOwner(ownerKey: string): Promise<OwnerScheduleResult> {
    const config = await this.port.loadConfig();
    const ownerSchedules = config.schedules.filter(
      (schedule) => schedule.scope === "owner" && schedule.ownerKey === ownerKey
    );
    const globalSchedules = config.schedules.filter(
      (schedule) => schedule.scope === "global"
    );

    return {
      metadata: config.metadata,
      ownerSchedules,
      globalSchedules
    };
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
}
