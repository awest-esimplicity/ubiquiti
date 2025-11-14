import rawSnapshot from "@/data/mock-config.json";
import type { OwnerInfo } from "@/lib/api/types";
import type { AdminPort } from "@/lib/ports/AdminPort";

const snapshotData = rawSnapshot as { owners: Array<OwnerInfo & { pin?: string | null }> };

function generateOwnerKey(name: string, existing: Set<string>): string {
  const base =
    name
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "owner";
  let candidate = base;
  let suffix = 2;
  while (existing.has(candidate)) {
    candidate = `${base}-${suffix}`;
    suffix += 1;
  }
  return candidate;
}

const DEFAULT_DEVICE_TYPES = [
  "computer",
  "tv",
  "switch",
  "streaming",
  "console",
  "phone",
  "tablet",
  "unknown",
];

export class MockAdminAdapter implements AdminPort {
  private owners: OwnerInfo[];
  private deviceTypes: string[];

  constructor() {
    this.owners = snapshotData.owners.map((owner) => ({
      key: owner.key,
      displayName: owner.displayName,
    }));
    this.deviceTypes = Array.from(new Set(DEFAULT_DEVICE_TYPES));
  }

  listOwners(): Promise<OwnerInfo[]> {
    return Promise.resolve(
      [...this.owners].sort((a, b) => a.displayName.localeCompare(b.displayName)),
    );
  }

  createOwner(displayName: string, pin: string): Promise<OwnerInfo> {
    const trimmedName = displayName.trim();
    if (!trimmedName) {
      throw new Error("Owner name must not be empty.");
    }
    const existingKeys = new Set(this.owners.map((owner) => owner.key));
    const key = generateOwnerKey(trimmedName, existingKeys);
    const entry: OwnerInfo = { key, displayName: trimmedName };
    this.owners.push(entry);

    snapshotData.owners.push({
      key,
      displayName: trimmedName,
      pin,
    });

    return Promise.resolve(entry);
  }

  listDeviceTypes(): Promise<string[]> {
    return Promise.resolve([...this.deviceTypes].sort((a, b) => a.localeCompare(b)));
  }

  createDeviceType(name: string): Promise<string[]> {
    const trimmed = name.trim();
    if (!trimmed) {
      throw new Error("Device type must not be empty.");
    }
    if (!this.deviceTypes.some((type) => type.toLowerCase() === trimmed.toLowerCase())) {
      this.deviceTypes.push(trimmed);
    }
    return this.listDeviceTypes();
  }
}
