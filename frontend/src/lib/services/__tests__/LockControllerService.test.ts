import { describe, expect, it, vi } from "vitest";

import type { Device, SessionIdentity } from "@/lib/domain/models";
import type { LockControllerPort } from "@/lib/ports/LockControllerPort";
import { LockControllerService } from "@/lib/services/LockControllerService";

describe("LockControllerService", () => {
  it("delegates device registration to the underlying port", async () => {
    const device: Device = {
      name: "Gaming Laptop",
      mac: "aa:bb:cc:dd:ee:ff",
      type: "computer",
      vendor: "Acme",
      locked: false,
    };

    const registerDevice = vi.fn<LockControllerPort["registerDevice"]>().mockResolvedValue(device);
    const service = new LockControllerService({
      registerDevice,
    } as unknown as LockControllerPort);

    const payload = {
      mac: device.mac,
      name: device.name,
      type: device.type,
    };

    const result = await service.registerDevice("kade", payload);

    expect(registerDevice).toHaveBeenCalledWith("kade", payload);
    expect(result).toEqual(device);
  });

  it("exposes whoAmI details from the underlying port", async () => {
    const identity: SessionIdentity = {
      ip: "10.0.0.5",
      forwardedFor: ["10.0.0.5"],
      probableClients: [],
    };
    const whoAmI = vi.fn<LockControllerPort["whoAmI"]>().mockResolvedValue(identity);
    const service = new LockControllerService({ whoAmI } as unknown as LockControllerPort);

    const result = await service.whoAmI();

    expect(whoAmI).toHaveBeenCalledOnce();
    expect(result).toEqual(identity);
  });
});
