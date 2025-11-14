import type { OwnerInfo } from "@/lib/api/types";

export interface AdminPort {
  listOwners(): Promise<OwnerInfo[]>;
  createOwner(displayName: string, pin: string): Promise<OwnerInfo>;
  deleteOwner(ownerKey: string): Promise<void>;
  listDeviceTypes(): Promise<string[]>;
  createDeviceType(name: string): Promise<string[]>;
  deleteDeviceType(name: string): Promise<void>;
}
