import type { OwnerSummary } from "@/lib/domain/models";

export const MASTER_PIN = "5161";

export const MASTER_OWNER: OwnerSummary = {
  key: "master",
  displayName: "Master Control",
  pin: MASTER_PIN,
  devices: []
};
