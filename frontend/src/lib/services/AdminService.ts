import type { OwnerInfo } from "@/lib/api/types";
import type { AdminPort } from "@/lib/ports/AdminPort";

export class AdminService {
  constructor(private readonly port: AdminPort) {}

  async listOwners(): Promise<OwnerInfo[]> {
    return this.port.listOwners();
  }

  async createOwner(displayName: string, pin: string): Promise<OwnerInfo> {
    return this.port.createOwner(displayName, pin);
  }

  async listDeviceTypes(): Promise<string[]> {
    return this.port.listDeviceTypes();
  }

  async createDeviceType(name: string): Promise<string[]> {
    return this.port.createDeviceType(name);
  }
}
