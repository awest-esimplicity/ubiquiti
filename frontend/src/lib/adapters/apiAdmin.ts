import { UnifiApiClient } from "@/lib/api/client";
import type { OwnerInfo } from "@/lib/api/types";
import type { AdminPort } from "@/lib/ports/AdminPort";

export class ApiAdminAdapter implements AdminPort {
  private readonly client: UnifiApiClient;

  constructor(baseUrl?: string) {
    this.client = new UnifiApiClient(baseUrl);
  }

  async listOwners(): Promise<OwnerInfo[]> {
    const response = await this.client.listAllOwners();
    return response.owners;
  }

  async createOwner(displayName: string, pin: string): Promise<OwnerInfo> {
    return this.client.createOwner({ displayName, pin });
  }

  async deleteOwner(ownerKey: string): Promise<void> {
    await this.client.deleteOwner(ownerKey);
  }

  async listDeviceTypes(): Promise<string[]> {
    const response = await this.client.listDeviceTypes();
    return response.types;
  }

  async createDeviceType(name: string): Promise<string[]> {
    const response = await this.client.createDeviceType({ name });
    return response.types;
  }

  async deleteDeviceType(name: string): Promise<void> {
    await this.client.deleteDeviceType(name);
  }
}
