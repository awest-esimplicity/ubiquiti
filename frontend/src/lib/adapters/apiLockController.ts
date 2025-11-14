import { UnifiApiClient } from "@/lib/api/client";
import {
  mapDevice,
  mapDeviceDetail,
  mapMetadata,
  mapOwner,
  mapUnregistered,
} from "@/lib/api/transformers";
import type {
  DashboardSnapshot,
  Device,
  DeviceDetail,
  DeviceRegistrationPayload,
  OwnerSummary,
  SessionIdentity,
  UnregisteredDevice,
} from "@/lib/domain/models";
import type { LockControllerPort } from "@/lib/ports/LockControllerPort";

export class ApiLockControllerAdapter implements LockControllerPort {
  private readonly client: UnifiApiClient;

  constructor(baseUrl?: string) {
    this.client = new UnifiApiClient(baseUrl);
  }

  async loadSnapshot(): Promise<DashboardSnapshot> {
    const [summary, ownersResponse, unregisteredResponse] = await Promise.all([
      this.client.getDashboardSummary(),
      this.client.listOwnerSummaries(),
      this.client.listUnregisteredClients(),
    ]);

    const owners: OwnerSummary[] = await Promise.all(
      ownersResponse.owners.map(async (owner) => {
        const devicesResponse = await this.client.listOwnerDevices(owner.key);
        return mapOwner(owner, devicesResponse.devices);
      }),
    );

    return {
      owners,
      unregistered: (unregisteredResponse.clients ?? []).map(mapUnregistered),
      metadata: mapMetadata(summary),
    };
  }

  async refresh(): Promise<DashboardSnapshot> {
    return this.loadSnapshot();
  }

  async loadUnregistered(): Promise<UnregisteredDevice[]> {
    const response = await this.client.listUnregisteredClients();
    return response.clients.map(mapUnregistered);
  }

  async lockDevices(devices: Device[]): Promise<void> {
    const targets = devices.map((device) => ({
      mac: device.mac,
      name: device.name,
      type: device.type,
      owner: undefined,
    }));
    await this.client.lockDevices(targets);
  }

  async unlockDevices(devices: Device[]): Promise<void> {
    const targets = devices.map((device) => ({
      mac: device.mac,
      name: device.name,
      type: device.type,
      owner: undefined,
    }));
    await this.client.lockDevices(targets, true);
  }

  async lockOwner(owner: OwnerSummary): Promise<void> {
    await this.client.lockOwner(owner.key, false);
  }

  async unlockOwner(owner: OwnerSummary): Promise<void> {
    await this.client.lockOwner(owner.key, true);
  }

  async lockFiltered(devices: Device[]): Promise<void> {
    await this.lockDevices(devices);
  }

  async unlockFiltered(devices: Device[]): Promise<void> {
    await this.unlockDevices(devices);
  }

  async verifyOwnerPin(ownerKey: string, pin: string): Promise<boolean> {
    return this.client.verifyOwnerPin(ownerKey, pin);
  }

  async registerDevice(ownerKey: string, payload: DeviceRegistrationPayload): Promise<Device> {
    const response = await this.client.registerOwnerDevice(ownerKey, {
      mac: payload.mac,
      name: payload.name?.trim() || undefined,
      type: payload.type?.trim().toLowerCase() || undefined,
    });
    return mapDevice(response);
  }

  async whoAmI(): Promise<SessionIdentity> {
    const response = await this.client.whoAmI();
    return {
      ip: response.ip ?? undefined,
      forwardedFor: response.forwardedFor ?? [],
      probableClients: (response.probableClients ?? []).map(mapUnregistered),
    };
  }

  async getDeviceDetail(mac: string, lookbackMinutes?: number): Promise<DeviceDetail> {
    const detail = await this.client.getDeviceDetail(mac, lookbackMinutes);
    return mapDeviceDetail(detail);
  }
}
