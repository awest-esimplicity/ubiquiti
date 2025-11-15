import scheduleConfig from "@/data/mock-schedules.json";
import type {
  CreateScheduleInput,
  DeviceSchedule,
  ScheduleConfig,
  OwnerScheduleSnapshot
} from "@/lib/domain/schedules";
import type { SchedulePort } from "@/lib/ports/SchedulePort";

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export class MockScheduleAdapter implements SchedulePort {
  private config: ScheduleConfig;

  constructor() {
    this.config = clone(scheduleConfig as ScheduleConfig);
  }

  loadConfig(): Promise<ScheduleConfig> {
    return Promise.resolve(clone(this.config));
  }

  loadOwnerSchedules(ownerKey: string): Promise<OwnerScheduleSnapshot> {
    const ownerSchedules = this.config.schedules.filter(
      (schedule) => schedule.scope === "owner" && schedule.ownerKey === ownerKey
    );
    const globalSchedules = this.config.schedules.filter(
      (schedule) => schedule.scope === "global"
    );
    return Promise.resolve({
      metadata: clone(this.config.metadata),
      ownerSchedules: clone(ownerSchedules),
      globalSchedules: clone(globalSchedules)
    });
  }

  createSchedule(input: CreateScheduleInput): Promise<DeviceSchedule> {
    const now = new Date().toISOString();
    const idPrefix =
      input.scope === "owner" && input.ownerKey
        ? `owner-${input.ownerKey}`
        : "global";

    const schedule: DeviceSchedule = {
      id: `${idPrefix}-${Date.now()}`,
      scope: input.scope,
      ownerKey: input.ownerKey,
      label: input.label,
      description: input.description,
      targets: clone(input.targets),
      action: input.action,
      endAction: input.endAction,
      window: clone(input.window),
      recurrence: clone(input.recurrence),
      exceptions: clone(input.exceptions ?? []),
      enabled: input.enabled ?? true,
      createdAt: now,
      updatedAt: now
    };

    this.config.schedules.push(schedule);
    return Promise.resolve(clone(schedule));
  }

  deleteSchedule(scheduleId: string): Promise<void> {
    this.config.schedules = this.config.schedules.filter((schedule) => schedule.id !== scheduleId);
    return Promise.resolve();
  }

  cloneSchedule(scheduleId: string, targetOwner: string): Promise<DeviceSchedule> {
    const source = this.config.schedules.find((schedule) => schedule.id === scheduleId);
    if (!source) {
      return Promise.reject(new Error("Schedule not found"));
    }
    const now = new Date().toISOString();
    const clonedSchedule: DeviceSchedule = {
      ...clone(source),
      id: `owner-${targetOwner}-${Date.now()}`,
      scope: "owner",
      ownerKey: targetOwner,
      enabled: true,
      createdAt: now,
      updatedAt: now
    };
    this.config.schedules.push(clonedSchedule);
    return Promise.resolve(clone(clonedSchedule));
  }

  copyOwnerSchedules(
    sourceOwner: string,
    targetOwner: string,
    mode: "merge" | "replace"
  ): Promise<{ created: DeviceSchedule[]; replacedCount: number }> {
    const sourceSchedules = this.config.schedules.filter(
      (schedule) => schedule.scope === "owner" && schedule.ownerKey === sourceOwner
    );
    if (sourceSchedules.length === 0) {
      return Promise.resolve({ created: [], replacedCount: 0 });
    }

    let replacedCount = 0;
    if (mode === "replace") {
      const remaining = this.config.schedules.filter((schedule) => {
        const replaceCandidate = schedule.scope === "owner" && schedule.ownerKey === targetOwner;
        if (replaceCandidate) {
          replacedCount += 1;
          return false;
        }
        return true;
      });
      this.config.schedules = remaining;
    }

    const created: DeviceSchedule[] = [];
    for (const schedule of sourceSchedules) {
      const now = new Date().toISOString();
      const copy: DeviceSchedule = {
        ...clone(schedule),
        id: `owner-${targetOwner}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
        scope: "owner",
        ownerKey: targetOwner,
        enabled: true,
        createdAt: now,
        updatedAt: now
      };
      this.config.schedules.push(copy);
      created.push(clone(copy));
    }

    return Promise.resolve({ created, replacedCount });
  }
}
