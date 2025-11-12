import type { DashboardSnapshot, OwnerSummary, Device, UnregisteredDevice } from "@/lib/domain/models";

export interface LockControllerPort {
  loadSnapshot(): Promise<DashboardSnapshot>;
  lockDevices(devices: Device[]): Promise<void>;
  unlockDevices(devices: Device[]): Promise<void>;
  lockOwner(owner: OwnerSummary): Promise<void>;
  unlockOwner(owner: OwnerSummary): Promise<void>;
  lockFiltered(devices: Device[]): Promise<void>;
  unlockFiltered(devices: Device[]): Promise<void>;
  refresh(): Promise<DashboardSnapshot>;
  loadUnregistered(): Promise<UnregisteredDevice[]>;
  verifyOwnerPin(ownerKey: string, pin: string): Promise<boolean>;
}
