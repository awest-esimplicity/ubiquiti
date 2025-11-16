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

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function generateId(prefix: string): string {
  return `${prefix}-${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 8)}`;
}

interface InternalGroup {
  id: string;
  name: string;
  ownerKey?: string;
  description?: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
  scheduleIds: Set<string>;
}

export class MockScheduleAdapter implements SchedulePort {
  private config: ScheduleConfig;
  private groups: Map<string, InternalGroup>;
  private scheduleMemberships: Map<string, Set<string>>;

  constructor() {
    this.config = deepClone(scheduleConfig as ScheduleConfig);
    this.config.schedules = this.config.schedules.map((schedule) => {
      const legacyGroupId = (schedule as DeviceSchedule & { groupId?: string }).groupId;
      const legacyGroupIds = (schedule as DeviceSchedule & { groupIds?: string[] }).groupIds;
      return {
        ...schedule,
        groupIds: Array.isArray(legacyGroupIds)
          ? [...legacyGroupIds]
          : legacyGroupId
          ? [legacyGroupId]
          : [],
      };
    });
    this.groups = new Map();
    this.scheduleMemberships = new Map();
  }

  private cloneSchedule(schedule: DeviceSchedule): DeviceSchedule {
    return deepClone(schedule);
  }

  private findSchedule(scheduleId: string): DeviceSchedule | undefined {
    return this.config.schedules.find((schedule) => schedule.id === scheduleId);
  }

  private ensureSchedule(scheduleId: string): DeviceSchedule {
    const schedule = this.findSchedule(scheduleId);
    if (!schedule) {
      throw new Error(`Schedule ${scheduleId} not found`);
    }
    return schedule;
  }

  private ensureGroup(groupId: string): InternalGroup {
    const group = this.groups.get(groupId);
    if (!group) {
      throw new Error(`Schedule group ${groupId} not found`);
    }
    return group;
  }

  private addMembership(group: InternalGroup, scheduleId: string): void {
    const schedule = this.ensureSchedule(scheduleId);
    if (!schedule.groupIds.includes(group.id)) {
      schedule.groupIds.push(group.id);
      schedule.updatedAt = new Date().toISOString();
    }
    group.scheduleIds.add(scheduleId);
    const memberships = this.scheduleMemberships.get(scheduleId) ?? new Set<string>();
    memberships.add(group.id);
    this.scheduleMemberships.set(scheduleId, memberships);
  }

  private removeMembership(group: InternalGroup, scheduleId: string): void {
    const schedule = this.ensureSchedule(scheduleId);
    if (schedule.groupIds.includes(group.id)) {
      schedule.groupIds = schedule.groupIds.filter((id) => id !== group.id);
      schedule.updatedAt = new Date().toISOString();
    }
    group.scheduleIds.delete(scheduleId);
    const memberships = this.scheduleMemberships.get(scheduleId);
    if (memberships) {
      memberships.delete(group.id);
      if (memberships.size === 0) {
        this.scheduleMemberships.delete(scheduleId);
      }
    }
  }

  private enforceActivation(): void {
    const activeGroups = new Set(
      [...this.groups.values()].filter((group) => group.isActive).map((group) => group.id),
    );
    if (activeGroups.size === 0) {
      // When no groups are active we disable only the schedules that belong to any group.
      for (const schedule of this.config.schedules) {
        if (this.scheduleMemberships.has(schedule.id)) {
          if (schedule.enabled !== false) {
            schedule.enabled = false;
            schedule.updatedAt = new Date().toISOString();
          }
        }
      }
      return;
    }

    const now = new Date().toISOString();
    for (const schedule of this.config.schedules) {
      const memberships = this.scheduleMemberships.get(schedule.id);
      if (!memberships || memberships.size === 0) {
        continue;
      }
      const shouldEnable = [...memberships].some((groupId) => activeGroups.has(groupId));
      if (schedule.enabled !== shouldEnable) {
        schedule.enabled = shouldEnable;
        schedule.updatedAt = now;
      }
    }
  }

  private toScheduleGroup(group: InternalGroup): ScheduleGroup {
    const schedules = [...group.scheduleIds]
      .map((scheduleId) => this.findSchedule(scheduleId))
      .filter((schedule): schedule is DeviceSchedule => Boolean(schedule))
      .map((schedule) => this.cloneSchedule(schedule));
    return {
      id: group.id,
      ownerKey: group.ownerKey,
      name: group.name,
      description: group.description,
      isActive: group.isActive,
      createdAt: group.createdAt,
      updatedAt: group.updatedAt,
      schedules,
    };
  }

  loadConfig(): Promise<ScheduleConfig> {
    return Promise.resolve(deepClone(this.config));
  }

  loadOwnerSchedules(ownerKey: string): Promise<OwnerScheduleSnapshot> {
    const ownerSchedules = this.config.schedules
      .filter((schedule) => schedule.scope === "owner" && schedule.ownerKey === ownerKey)
      .map((schedule) => this.cloneSchedule(schedule));
    const globalSchedules = this.config.schedules
      .filter((schedule) => schedule.scope === "global")
      .map((schedule) => this.cloneSchedule(schedule));
    return Promise.resolve({
      metadata: deepClone(this.config.metadata),
      ownerSchedules,
      globalSchedules,
    });
  }

  loadGroups(ownerKey: string): Promise<ScheduleGroupList> {
    const ownerGroups = [...this.groups.values()]
      .filter((group) => group.ownerKey === ownerKey)
      .map((group) => this.toScheduleGroup(group));
    const globalGroups = [...this.groups.values()]
      .filter((group) => !group.ownerKey)
      .map((group) => this.toScheduleGroup(group));
    return Promise.resolve({ ownerGroups, globalGroups });
  }

  async createSchedule(input: CreateScheduleInput): Promise<DeviceSchedule> {
    const now = new Date().toISOString();
    const id = generateId(input.scope === "owner" && input.ownerKey ? input.ownerKey : "global");
    const schedule: DeviceSchedule = {
      id,
      scope: input.scope,
      ownerKey: input.ownerKey,
      groupIds: [...(input.groupIds ?? [])],
      label: input.label,
      description: input.description,
      targets: deepClone(input.targets),
      action: input.action,
      endAction: input.endAction,
      window: deepClone(input.window),
      recurrence: deepClone(input.recurrence),
      exceptions: deepClone(input.exceptions ?? []),
      enabled: input.enabled ?? true,
      createdAt: now,
      updatedAt: now,
    };
    this.config.schedules.push(schedule);
    for (const groupId of schedule.groupIds) {
      const group = this.ensureGroup(groupId);
      this.addMembership(group, schedule.id);
    }
    this.enforceActivation();
    return Promise.resolve(this.cloneSchedule(schedule));
  }

  deleteSchedule(scheduleId: string): Promise<void> {
    const index = this.config.schedules.findIndex((schedule) => schedule.id === scheduleId);
    if (index === -1) {
      return Promise.resolve();
    }
    const schedule = this.config.schedules[index];
    for (const groupId of [...schedule.groupIds]) {
      const group = this.ensureGroup(groupId);
      this.removeMembership(group, scheduleId);
    }
    this.config.schedules.splice(index, 1);
    this.scheduleMemberships.delete(scheduleId);
    this.enforceActivation();
    return Promise.resolve();
  }

  async cloneSchedule(scheduleId: string, targetOwner: string): Promise<DeviceSchedule> {
    const source = this.ensureSchedule(scheduleId);
    const now = new Date().toISOString();
    const clone: DeviceSchedule = {
      ...this.cloneSchedule(source),
      id: generateId(`owner-${targetOwner}`),
      scope: "owner",
      ownerKey: targetOwner,
      groupIds: [],
      enabled: true,
      createdAt: now,
      updatedAt: now,
    };
    this.config.schedules.push(clone);
    return Promise.resolve(this.cloneSchedule(clone));
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
      const toRemove = this.config.schedules.filter(
        (schedule) => schedule.scope === "owner" && schedule.ownerKey === targetOwner,
      );
      replacedCount = toRemove.length;
      for (const schedule of toRemove) {
        for (const groupId of [...schedule.groupIds]) {
          const group = this.ensureGroup(groupId);
          this.removeMembership(group, schedule.id);
        }
        this.scheduleMemberships.delete(schedule.id);
      }
      this.config.schedules = this.config.schedules.filter((schedule) => !toRemove.includes(schedule));
    }

    const created: DeviceSchedule[] = [];
    for (const schedule of sourceSchedules) {
      const now = new Date().toISOString();
      const clone: DeviceSchedule = {
        ...this.cloneSchedule(schedule),
        id: generateId(`owner-${targetOwner}`),
        scope: "owner",
        ownerKey: targetOwner,
        groupIds: [],
        enabled: true,
        createdAt: now,
        updatedAt: now,
      };
      this.config.schedules.push(clone);
      created.push(this.cloneSchedule(clone));
    }
    return Promise.resolve({ created, replacedCount });
  }

  createGroup(input: CreateScheduleGroupInput): Promise<ScheduleGroup> {
    const now = new Date().toISOString();
    const id = generateId("group");
    const group: InternalGroup = {
      id,
      ownerKey: input.ownerKey,
      name: input.name,
      description: input.description,
      isActive: Boolean(input.isActive),
      createdAt: now,
      updatedAt: now,
      scheduleIds: new Set<string>(),
    };
    this.groups.set(id, group);
    for (const scheduleId of input.scheduleIds) {
      this.addMembership(group, scheduleId);
    }
    if (group.scheduleIds.size === 0) {
      group.isActive = false;
    }
    this.enforceActivation();
    return Promise.resolve(this.toScheduleGroup(group));
  }

  updateGroup(input: UpdateScheduleGroupInput): Promise<ScheduleGroup> {
    const group = this.ensureGroup(input.groupId);
    const now = new Date().toISOString();
    if (input.name !== undefined) {
      group.name = input.name;
    }
    if (input.description !== undefined) {
      group.description = input.description;
    }
    if (input.scheduleIds !== undefined) {
      const desired = new Set(input.scheduleIds);
      for (const scheduleId of [...group.scheduleIds]) {
        if (!desired.has(scheduleId)) {
          this.removeMembership(group, scheduleId);
        }
      }
      for (const scheduleId of desired) {
        if (!group.scheduleIds.has(scheduleId)) {
          this.addMembership(group, scheduleId);
        }
      }
      if (group.scheduleIds.size === 0) {
        group.isActive = false;
      }
    }
    if (input.isActive !== undefined) {
      group.isActive = input.isActive;
    }
    group.updatedAt = now;
    this.enforceActivation();
    return Promise.resolve(this.toScheduleGroup(group));
  }

  deleteGroup(groupId: string): Promise<void> {
    const group = this.ensureGroup(groupId);
    for (const scheduleId of [...group.scheduleIds]) {
      this.removeMembership(group, scheduleId);
    }
    this.groups.delete(groupId);
    this.enforceActivation();
    return Promise.resolve();
  }

  toggleGroupActivation(groupId: string, active: boolean): Promise<ScheduleGroup> {
    const group = this.ensureGroup(groupId);
    group.isActive = active;
    group.updatedAt = new Date().toISOString();
    this.enforceActivation();
    return Promise.resolve(this.toScheduleGroup(group));
  }
}
