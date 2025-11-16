import scheduleConfig from "@/data/mock-schedules.json";
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

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function generateId(prefix: string): string {
  return `${prefix}-${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 8)}`;
}

export class MockScheduleAdapter implements SchedulePort {
  private config: ScheduleConfig;
  private groups: ScheduleGroup[];

  constructor() {
    this.config = clone(scheduleConfig as ScheduleConfig);
    this.groups = [];
  }

  loadConfig(): Promise<ScheduleConfig> {
    return Promise.resolve(clone(this.config));
  }

  loadOwnerSchedules(ownerKey: string): Promise<OwnerScheduleSnapshot> {
    const ownerSchedules = this.config.schedules.filter(
      (schedule) => schedule.scope === "owner" && schedule.ownerKey === ownerKey,
    );
    const globalSchedules = this.config.schedules.filter((schedule) => schedule.scope === "global");
    return Promise.resolve({
      metadata: clone(this.config.metadata),
      ownerSchedules: clone(ownerSchedules),
      globalSchedules: clone(globalSchedules),
    });
  }

  loadGroups(ownerKey: string): Promise<ScheduleGroupList> {
    const ownerGroups = this.groups.filter((group) => group.ownerKey === ownerKey);
    const globalGroups = this.groups.filter((group) => !group.ownerKey);
    const mapGroup = (group: ScheduleGroup): ScheduleGroup => ({
      ...clone(group),
      schedules: clone(
        this.config.schedules.filter((schedule) => schedule.groupId === group.id),
      ),
    });
    return Promise.resolve({
      ownerGroups: ownerGroups.map(mapGroup),
      globalGroups: globalGroups.map(mapGroup),
    });
  }

  async createSchedule(input: CreateScheduleInput): Promise<DeviceSchedule> {
    const now = new Date().toISOString();
    const idPrefix =
      input.scope === "owner" && input.ownerKey ? `owner-${input.ownerKey}` : "global";

    const schedule: DeviceSchedule = {
      id: `${idPrefix}-${Date.now()}`,
      scope: input.scope,
      ownerKey: input.ownerKey,
      groupId: input.groupId ?? undefined,
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
      updatedAt: now,
    };

    this.config.schedules.push(schedule);
    if (schedule.groupId) {
      const group = this.groups.find((item) => item.id === schedule.groupId);
      if (group) {
        if (!group.activeScheduleId) {
          group.activeScheduleId = schedule.id;
          this.setGroupActive(group.id, schedule.id);
        } else {
          schedule.enabled = group.activeScheduleId === schedule.id;
        }
        group.updatedAt = now;
      }
    }
    return Promise.resolve(clone(schedule));
  }

  deleteSchedule(scheduleId: string): Promise<void> {
    const schedule = this.config.schedules.find((item) => item.id === scheduleId);
    this.config.schedules = this.config.schedules.filter((item) => item.id !== scheduleId);
    if (schedule?.groupId) {
      const group = this.groups.find((item) => item.id === schedule.groupId);
      if (group) {
        if (group.activeScheduleId === scheduleId) {
          const remaining = this.config.schedules.find((item) => item.groupId === group.id);
          group.activeScheduleId = remaining?.id;
          this.setGroupActive(group.id, group.activeScheduleId ?? undefined);
        }
        group.updatedAt = new Date().toISOString();
      }
    }
    return Promise.resolve();
  }

  async cloneSchedule(scheduleId: string, targetOwner: string): Promise<DeviceSchedule> {
    const source = this.config.schedules.find((schedule) => schedule.id === scheduleId);
    if (!source) {
      return Promise.reject(new Error("Schedule not found"));
    }
    const now = new Date().toISOString();
    const clonedSchedule: DeviceSchedule = {
      ...clone(source),
      id: generateId(`owner-${targetOwner}`),
      scope: "owner",
      ownerKey: targetOwner,
      groupId: undefined,
      enabled: true,
      createdAt: now,
      updatedAt: now,
    };
    this.config.schedules.push(clonedSchedule);
    return Promise.resolve(clone(clonedSchedule));
  }

  copyOwnerSchedules(
    sourceOwner: string,
    targetOwner: string,
    mode: "merge" | "replace",
  ): Promise<{ created: DeviceSchedule[]; replacedCount: number }> {
    const sourceSchedules = this.config.schedules.filter(
      (schedule) => schedule.scope === "owner" && schedule.ownerKey === sourceOwner,
    );
    if (sourceSchedules.length === 0) {
      return Promise.resolve({ created: [], replacedCount: 0 });
    }

    let replacedCount = 0;
    if (mode === "replace") {
      const remaining = this.config.schedules.filter((schedule) => {
        const replaceCandidate =
          schedule.scope === "owner" && schedule.ownerKey === targetOwner;
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
        id: generateId(`owner-${targetOwner}`),
        scope: "owner",
        ownerKey: targetOwner,
        groupId: undefined,
        enabled: true,
        createdAt: now,
        updatedAt: now,
      };
      this.config.schedules.push(copy);
      created.push(clone(copy));
    }

    return Promise.resolve({ created, replacedCount });
  }

  createGroup(input: CreateScheduleGroupInput): Promise<ScheduleGroup> {
    const now = new Date().toISOString();
    const id = generateId("group");
    const group: ScheduleGroup = {
      id,
      ownerKey: input.ownerKey,
      name: input.name,
      description: input.description,
      activeScheduleId: input.activeScheduleId ?? input.scheduleIds[0] ?? undefined,
      createdAt: now,
      updatedAt: now,
      schedules: [],
    };
    this.groups.push(group);

    this.config.schedules = this.config.schedules.map((schedule) => {
      if (input.scheduleIds.includes(schedule.id)) {
        return {
          ...schedule,
          groupId: id,
          enabled: group.activeScheduleId
            ? schedule.id === group.activeScheduleId
            : schedule.enabled,
        };
      }
      return schedule;
    });

    if (group.activeScheduleId) {
      this.setGroupActive(id, group.activeScheduleId);
    }

    return Promise.resolve({
      ...group,
      schedules: clone(
        this.config.schedules.filter((schedule) => schedule.groupId === id),
      ),
    });
  }

  updateGroup(input: UpdateScheduleGroupInput): Promise<ScheduleGroup> {
    const group = this.groups.find((item) => item.id === input.groupId);
    if (!group) {
      return Promise.reject(new Error("Group not found"));
    }
    const now = new Date().toISOString();
    if (input.name !== undefined) {
      group.name = input.name;
    }
    if (input.description !== undefined) {
      group.description = input.description;
    }
    if (input.scheduleIds) {
      const desired = new Set(input.scheduleIds);
      this.config.schedules = this.config.schedules.map((schedule) => {
        if (schedule.groupId === group.id && !desired.has(schedule.id)) {
          return { ...schedule, groupId: undefined };
        }
        if (desired.has(schedule.id)) {
          return { ...schedule, groupId: group.id };
        }
        return schedule;
      });
      if (input.activeScheduleId && !desired.has(input.activeScheduleId)) {
        return Promise.reject(new Error("activeScheduleId must be part of scheduleIds"));
      }
    }
    if (input.activeScheduleId !== undefined) {
      group.activeScheduleId = input.activeScheduleId || undefined;
    }
    group.updatedAt = now;
    if (group.activeScheduleId) {
      this.setGroupActive(group.id, group.activeScheduleId);
    }
    return Promise.resolve({
      ...group,
      schedules: clone(
        this.config.schedules.filter((schedule) => schedule.groupId === group.id),
      ),
    });
  }

  deleteGroup(groupId: string): Promise<void> {
    this.groups = this.groups.filter((group) => group.id !== groupId);
    this.config.schedules = this.config.schedules.map((schedule) =>
      schedule.groupId === groupId ? { ...schedule, groupId: undefined } : schedule,
    );
    return Promise.resolve();
  }

  activateGroup(groupId: string, scheduleId: string): Promise<ScheduleGroup> {
    const group = this.groups.find((item) => item.id === groupId);
    if (!group) {
      return Promise.reject(new Error("Group not found"));
    }
    const scheduleExists = this.config.schedules.some(
      (schedule) => schedule.id === scheduleId && schedule.groupId === groupId,
    );
    if (!scheduleExists) {
      return Promise.reject(new Error("Schedule does not belong to group"));
    }
    group.activeScheduleId = scheduleId;
    group.updatedAt = new Date().toISOString();
    this.setGroupActive(group.id, scheduleId);
    return Promise.resolve({
      ...group,
      schedules: clone(
        this.config.schedules.filter((schedule) => schedule.groupId === group.id),
      ),
    });
  }

  private setGroupActive(groupId: string, scheduleId: string | undefined): void {
    this.config.schedules = this.config.schedules.map((schedule) => {
      if (schedule.groupId === groupId) {
        return { ...schedule, enabled: schedule.id === scheduleId };
      }
      return schedule;
    });
  }
}
