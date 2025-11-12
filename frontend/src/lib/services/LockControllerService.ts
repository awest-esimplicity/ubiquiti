import type { DashboardSnapshot, Device, OwnerSummary, UnregisteredDevice } from "@/lib/domain/models";
import type { LockControllerPort } from "@/lib/ports/LockControllerPort";

export class LockControllerService {
  constructor(private readonly port: LockControllerPort) {}

  async loadSnapshot(): Promise<DashboardSnapshot> {
    return this.port.loadSnapshot();
  }

  async refresh(): Promise<DashboardSnapshot> {
    return this.port.refresh();
  }

  async lockDevice(device: Device): Promise<void> {
    await this.port.lockDevices([device]);
  }

  async unlockDevice(device: Device): Promise<void> {
    await this.port.unlockDevices([device]);
  }

  async lockOwner(owner: OwnerSummary): Promise<void> {
    await this.port.lockOwner(owner);
  }

  async unlockOwner(owner: OwnerSummary): Promise<void> {
    await this.port.unlockOwner(owner);
  }

  async lockFiltered(devices: Device[]): Promise<void> {
    await this.port.lockFiltered(devices);
  }

  async unlockFiltered(devices: Device[]): Promise<void> {
    await this.port.unlockFiltered(devices);
  }

  async loadUnregistered(): Promise<UnregisteredDevice[]> {
    return this.port.loadUnregistered();
  }

  async verifyOwnerPin(ownerKey: string, pin: string): Promise<boolean> {
    return this.port.verifyOwnerPin(ownerKey, pin);
  }
}
