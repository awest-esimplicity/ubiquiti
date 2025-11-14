import { UnifiApiClient } from "@/lib/api/client";
import { mapAuditEvents } from "@/lib/api/transformers";
import type { AuditEvent } from "@/lib/domain/models";

export class EventService {
  constructor(private readonly client: UnifiApiClient = new UnifiApiClient()) {}

  async listEvents(limit = 200, signal?: AbortSignal): Promise<AuditEvent[]> {
    const response = await this.client.listEvents(limit, signal);
    return mapAuditEvents(response);
  }
}
