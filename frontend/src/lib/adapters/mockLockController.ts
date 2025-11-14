import rawSnapshot from "@/data/mock-config.json";
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

  private normalizeDeviceType(input?: string): Device["type"] {
    if (!input) {
      return "unknown";
    }
    const normalized = input.trim();
    return normalized === "" ? "unknown" : normalized;
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

  registerDevice(ownerKey: string, payload: DeviceRegistrationPayload): Promise<Device> {
    const mac = payload.mac.toLowerCase();
    const ownerKeyNormalized = ownerKey.toLowerCase();
    const type = this.normalizeDeviceType(payload.type);
    const name = payload.name?.trim() || payload.mac;

    let ownerFound = false;
    this.snapshot.owners = this.snapshot.owners.map((owner) => {
      const filteredDevices = owner.devices.filter((device) => device.mac !== mac);
      if (owner.key === ownerKeyNormalized) {
        ownerFound = true;
        const registeredDevice: Device = {
          name,
          mac,
          type,
          vendor: undefined,
          locked: false,
        };
        return {
          ...owner,
          devices: [...filteredDevices, registeredDevice].sort((a, b) =>
            a.name.localeCompare(b.name),
          ),
        };
      }
      return {
        ...owner,
        devices: filteredDevices,
      };
    });

    if (!ownerFound) {
      throw new Error(`Owner ${ownerKey} not found in mock data.`);
    }

    this.snapshot.unregistered = (this.snapshot.unregistered ?? []).filter(
      (device) => device.mac !== mac,
    );

    return Promise.resolve({
      name,
      mac,
      type,
      vendor: undefined,
      locked: false,
    });
  }

  whoAmI(): Promise<SessionIdentity> {
    return Promise.resolve({
      ip: undefined,
      forwardedFor: [],
      probableClients: [],
    });
  }

  getDeviceDetail(mac: string, lookbackMinutes = 60): Promise<DeviceDetail> {
    const normalizedMac = mac.toLowerCase();
    const owner = this.snapshot.owners.find((entry) =>
      entry.devices.some((device) => device.mac === normalizedMac),
    );
    if (!owner) {
      throw new Error(`Device ${mac} not found in mock data.`);
    }

    const device = owner.devices.find((entry) => entry.mac === normalizedMac);
    if (!device) {
      throw new Error(`Device ${mac} not found in mock data.`);
    }

    const interval = Math.min(24 * 60, Math.max(5, Math.trunc(lookbackMinutes)));
    const now = new Date();
    const sampleStep = Math.max(5, Math.trunc(interval / 12) || 5);
    const samples: {
      timestamp: string;
      rxBytes: number;
      txBytes: number;
      totalBytes: number;
    }[] = [];

    const seed = normalizedMac.split(":").reduce((acc, chunk) => acc + parseInt(chunk, 16), 0);

    for (let minutes = interval; minutes >= 0; minutes -= sampleStep) {
      const timestamp = new Date(now.getTime() - minutes * 60 * 1000).toISOString();
      const rxBytes = ((seed + minutes * 47) % 2048) * 1024;
      const txBytes = ((seed + (interval - minutes) * 31) % 2048) * 768;
      samples.push({
        timestamp,
        rxBytes,
        txBytes,
        totalBytes: rxBytes + txBytes,
      });
    }

    const totalRxBytes = samples.reduce((sum, sample) => sum + sample.rxBytes, 0);
    const totalTxBytes = samples.reduce((sum, sample) => sum + sample.txBytes, 0);
    const start = samples[0]?.timestamp;
    const end = samples[samples.length - 1]?.timestamp ?? start;

    const ipSubnet = 10 + (seed % 50);
    const ipHost = 20 + (seed % 200);

    const detail: DeviceDetail = {
      ...device,
      owner: owner.key,
      ip: `10.0.${ipSubnet}.${ipHost}`,
      lastSeen: now.toISOString(),
      connection: seed % 2 === 0 ? "wired" : "wireless",
      accessPoint: seed % 2 === 0 ? undefined : "00:11:22:33:44:55",
      signal: seed % 2 === 0 ? undefined : -40 + (seed % 6),
      online: true,
      networkName: `${owner.displayName}'s Network`,
      traffic: {
        intervalMinutes: interval,
        start,
        end,
        totalRxBytes,
        totalTxBytes,
        samples,
      },
      destinations:
        seed % 2 === 0
          ? [`Switch-${owner.displayName}`, "WAN Gateway"]
          : [`AP-${owner.displayName}`, "WAN Gateway"],
      dpiApplications: [
        {
          application: seed % 2 === 0 ? "YouTube" : "Instagram",
          category: seed % 2 === 0 ? "Streaming Media" : "Social Networks",
          rxBytes: Math.round(totalRxBytes * 0.6),
          txBytes: Math.round(totalTxBytes * 0.4),
        },
        {
          application: "DNS",
          category: "Infrastructure",
          rxBytes: 25_600,
          txBytes: 12_800,
        },
      ],
    };

    return Promise.resolve(detail);
  }

  setUnregisteredLock(device: UnregisteredDevice, unlock = false): Promise<void> {
    const mac = device.mac.toLowerCase();
    this.snapshot.unregistered = this.snapshot.unregistered.map((entry) =>
      entry.mac.toLowerCase() === mac ? { ...entry, locked: !unlock } : entry,
    );
    return Promise.resolve();
  }

  private updateDeviceLocks(devices: Device[], locked: boolean) {
    const macs = new Set(devices.map((d) => d.mac));
    this.snapshot.owners = this.snapshot.owners.map((owner) => ({
      ...owner,
      devices: owner.devices.map((device) =>
        macs.has(device.mac) ? { ...device, locked } : device,
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
        : owner,
    );
  }
}
