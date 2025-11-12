import rawSnapshot from "@/data/mock-config.json";
import type { DashboardSnapshot, Device, OwnerSummary, UnregisteredDevice } from "@/lib/domain/models";
import type { LockControllerPort } from "@/lib/ports/LockControllerPort";

const snapshotData = rawSnapshot as DashboardSnapshot;

function deepCloneSnapshot(): DashboardSnapshot {
  return structuredClone(snapshotData);
}

export class MockLockControllerAdapter implements LockControllerPort {
  private snapshot: DashboardSnapshot;
  private readonly ownerPins: Map<string, string>;

  constructor() {
    this.snapshot = deepCloneSnapshot();
    this.ownerPins = new Map(snapshotData.owners.map((owner) => [owner.key, owner.pin ?? ""]));
  }

  loadSnapshot(): Promise<DashboardSnapshot> {
    return Promise.resolve(deepCloneSnapshot());
  }

  refresh(): Promise<DashboardSnapshot> {
    this.snapshot = deepCloneSnapshot();
    return Promise.resolve(this.snapshot);
  }

  loadUnregistered(): Promise<UnregisteredDevice[]> {
    return Promise.resolve(deepCloneSnapshot().unregistered);
  }

  lockDevices(devices: Device[]): Promise<void> {
    this.updateDeviceLocks(devices, true);
    return Promise.resolve();
  }

  unlockDevices(devices: Device[]): Promise<void> {
    this.updateDeviceLocks(devices, false);
    return Promise.resolve();
  }

  lockOwner(owner: OwnerSummary): Promise<void> {
    this.updateDevicesByOwner(owner.key, true);
    return Promise.resolve();
  }

  unlockOwner(owner: OwnerSummary): Promise<void> {
    this.updateDevicesByOwner(owner.key, false);
    return Promise.resolve();
  }

  lockFiltered(devices: Device[]): Promise<void> {
    return this.lockDevices(devices);
  }

  unlockFiltered(devices: Device[]): Promise<void> {
    return this.unlockDevices(devices);
  }

  verifyOwnerPin(ownerKey: string, pin: string): Promise<boolean> {
    return Promise.resolve(this.ownerPins.get(ownerKey) === pin);
  }

  private updateDeviceLocks(devices: Device[], locked: boolean) {
    const macs = new Set(devices.map((d) => d.mac));
    this.snapshot.owners = this.snapshot.owners.map((owner) => ({
      ...owner,
      devices: owner.devices.map((device) =>
        macs.has(device.mac) ? { ...device, locked } : device
      ),
    }));
  }

  private updateDevicesByOwner(ownerKey: string, locked: boolean) {
    this.snapshot.owners = this.snapshot.owners.map((owner) =>
      owner.key === ownerKey
        ? {
            ...owner,
            devices: owner.devices.map((device) => ({ ...device, locked })),
          }
        : owner
    );
  }
}
