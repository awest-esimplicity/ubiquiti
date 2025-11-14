import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { adminService } from "@/lib/bootstrap/admin";
import { lockControllerService } from "@/lib/bootstrap/lockController";
import type { DeviceType, OwnerSummary, UnregisteredDevice } from "@/lib/domain/models";
import { cn } from "@/lib/utils/cn";
import { formatTimestamp } from "@/lib/utils/date";

type SubmitState =
  | { status: "idle"; message?: string }
  | { status: "submitting" }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

interface DetectedDeviceInfo {
  name: string;
  type: DeviceType;
  notes: string;
}

const FALLBACK_DEVICE_TYPES: DeviceType[] = [
  "computer",
  "tv",
  "switch",
  "streaming",
  "console",
  "phone",
  "tablet",
  "unknown",
];

function detectDevice(): DetectedDeviceInfo {
  if (typeof window === "undefined") {
    return { name: "Unknown device", type: "unknown", notes: "Browser context unavailable." };
  }

  const ua = navigator.userAgent ?? "";
  const platform =
    // biome-ignore lint/style/noNonNullAssertion: fallback handled below
    (navigator as { userAgentData?: { platform?: string } }).userAgentData?.platform ??
    navigator.platform ??
    "Unknown platform";

  const lowerUA = ua.toLowerCase();

  const type: DeviceType =
    lowerUA.includes("iphone") || (lowerUA.includes("android") && lowerUA.includes("mobile"))
      ? "phone"
      : lowerUA.includes("ipad") || lowerUA.includes("tablet")
        ? "tablet"
        : lowerUA.includes("tv")
          ? "tv"
          : lowerUA.includes("xbox")
            ? "console"
            : "computer";

  const browserMatch =
    ua.match(/(Edg|Chrome|Firefox|Safari|Brave|Vivaldi|DuckDuckGo|Opera)[/\s](\d+)/i) ?? [];
  const browserName = browserMatch[1] ?? "Browser";
  const deviceLabel = `${platform} ${browserName}`;

  return {
    name: deviceLabel.trim(),
    type,
    notes: `Detected from user agent: ${browserName} on ${platform}.`,
  };
}

export function SelfRegisterDevice() {
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [ownerKey, setOwnerKey] = useState("");
  const [macAddress, setMacAddress] = useState("");
  const [deviceName, setDeviceName] = useState("");
  const [deviceType, setDeviceType] = useState<DeviceType>("unknown");
  const [submitState, setSubmitState] = useState<SubmitState>({ status: "idle" });
  const [loadingOwners, setLoadingOwners] = useState(true);
  const [detectedNotes, setDetectedNotes] = useState("");
  const [selfIp, setSelfIp] = useState<string | undefined>();
  const [forwardedIps, setForwardedIps] = useState<string[]>([]);
  const [probableClients, setProbableClients] = useState<UnregisteredDevice[]>([]);
  const [selectedProbableMac, setSelectedProbableMac] = useState<string | null>(null);
  const [identityError, setIdentityError] = useState<string | undefined>();
  const [availableTypes, setAvailableTypes] = useState<string[]>(FALLBACK_DEVICE_TYPES);
  const [unregisteredDevices, setUnregisteredDevices] = useState<UnregisteredDevice[]>([]);
  const [loadingUnregistered, setLoadingUnregistered] = useState(false);
  const [unregisteredError, setUnregisteredError] = useState<string | undefined>();
  const [pendingLockMacs, setPendingLockMacs] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    setLoadingOwners(true);
    void lockControllerService
      .loadSnapshot()
      .then((snapshot) => {
        if (cancelled) {
          return;
        }
        setOwners(snapshot.owners);
        if (snapshot.owners.length > 0) {
          setOwnerKey((current) => current || snapshot.owners[0].key);
        }
      })
      .catch((error: Error) => {
        if (cancelled) {
          return;
        }
        setSubmitState({ status: "error", message: error.message });
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingOwners(false);
        }
      });

    const detected = detectDevice();
    setDeviceName(detected.name);
    setDeviceType(detected.type);
    setDetectedNotes(detected.notes);
    setSubmitState((prev) =>
      prev.status === "idle" ? { status: "idle", message: detected.notes } : prev,
    );

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void lockControllerService
      .whoAmI()
      .then((identity) => {
        if (cancelled) {
          return;
        }
        setSelfIp(identity.ip ?? undefined);
        setForwardedIps(identity.forwardedFor ?? []);
        setProbableClients(identity.probableClients ?? []);
        const firstMatch = identity.probableClients?.[0];
        if (firstMatch) {
          setSelectedProbableMac(firstMatch.mac);
          setMacAddress((current) => current || firstMatch.mac.toUpperCase());
          setDeviceName((current) => current || firstMatch.name);
        }
      })
      .catch((error: Error) => {
        if (cancelled) {
          return;
        }
        setIdentityError(error.message);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoadingUnregistered(true);
    void lockControllerService
      .loadUnregistered()
      .then((devices) => {
        if (cancelled) {
          return;
        }
        setUnregisteredDevices(devices);
        setUnregisteredError(undefined);
      })
      .catch((error: Error) => {
        if (cancelled) {
          return;
        }
        setUnregisteredError(error.message);
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingUnregistered(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void adminService
      .listDeviceTypes()
      .then((types) => {
        if (cancelled) {
          return;
        }
        if (types.length > 0) {
          setAvailableTypes(types);
          if (!types.includes(deviceType)) {
            setDeviceType(types[0]);
          }
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAvailableTypes(FALLBACK_DEVICE_TYPES);
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ownerOptions = useMemo(
    () => [...owners].sort((a, b) => a.displayName.localeCompare(b.displayName)),
    [owners],
  );

  const canSubmit =
    submitState.status !== "submitting" &&
    macAddress.trim().length > 0 &&
    ownerKey.trim().length > 0;

  const handleSubmit = async () => {
    if (!canSubmit) {
      return;
    }
    setSubmitState({ status: "submitting" });

    try {
      const payload = {
        mac: macAddress.trim(),
        name: deviceName.trim(),
        type: deviceType,
      };

      await lockControllerService.registerDevice(ownerKey.trim(), payload);
      setSubmitState({
        status: "success",
        message:
          "Device registered successfully. It may take a few seconds to appear under the owner.",
      });
      setProbableClients((prev) =>
        prev.filter((client) => client.mac.toLowerCase() !== payload.mac.toLowerCase()),
      );
      setUnregisteredDevices((prev) =>
        prev.filter((device) => device.mac.toLowerCase() !== payload.mac.toLowerCase()),
      );
      setSelectedProbableMac(null);
      setMacAddress("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to register device.";
      setSubmitState({ status: "error", message });
    }
  };

  const handleSelectCandidate = (client: UnregisteredDevice) => {
    setSelectedProbableMac(client.mac);
    setMacAddress(client.mac.toUpperCase());
    setDeviceName((current) => (current && current !== "" ? current : client.name));
  };

  const handlePrefillUnregistered = (device: UnregisteredDevice) => {
    setMacAddress(device.mac.toUpperCase());
    setDeviceName(device.name);
    setSelectedProbableMac(device.mac);
    setSubmitState({ status: "idle", message: "Populated fields from active unregistered device." });
  };

  const handleToggleUnregisteredLock = async (device: UnregisteredDevice) => {
    setPendingLockMacs((prev) => {
      const next = new Set(prev);
      next.add(device.mac);
      return next;
    });
    try {
      await lockControllerService.setUnregisteredLock(device, device.locked);
      setUnregisteredDevices((prev) =>
        prev.map((entry) =>
          entry.mac.toLowerCase() === device.mac.toLowerCase()
            ? { ...entry, locked: !device.locked }
            : entry,
        ),
      );
      setSubmitState({
        status: "idle",
        message: `Device ${device.locked ? "unlocked" : "locked"} successfully.`,
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to update device lock state.";
      setSubmitState({ status: "error", message });
    } finally {
      setPendingLockMacs((prev) => {
        const next = new Set(prev);
        next.delete(device.mac);
        return next;
      });
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-8 rounded-3xl border border-slate-800/60 bg-slate-950/60 p-8 shadow-card">
      <header className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.35em] text-slate-500">Self registration</p>
        <h1 className="text-3xl font-semibold text-slate-50">
          Identify &amp; register this device
        </h1>
        <p className="text-sm text-slate-300">
          We tried to identify the device you are using. Confirm the details, provide the MAC
          address, and choose who should own it. After registration the device will move into the
          owner’s managed inventory.
        </p>
      </header>

      <div className="space-y-3 rounded-2xl border border-slate-800/60 bg-slate-900/60 p-5">
        <div className="flex flex-col gap-1 text-sm text-slate-200">
          <span className="font-semibold text-slate-100">Your network identity</span>
          <span className="text-xs text-slate-400">
            Detected IP: <span className="font-mono text-slate-200">{selfIp ?? "Unknown"}</span>
            {forwardedIps.length > 1 ? (
              <>
                {" "}
                (forwarded chain:{" "}
                {forwardedIps.map((value, index) => (
                  <span key={value} className="font-mono text-slate-300">
                    {value}
                    {index < forwardedIps.length - 1 ? ", " : null}
                  </span>
                ))}
                )
              </>
            ) : null}
          </span>
          {identityError ? (
            <span className="text-xs text-status-locked">
              Unable to check for active devices: {identityError}
            </span>
          ) : null}
        </div>
      </div>

      <section className="grid gap-6 md:grid-cols-2">
        <div className="rounded-2xl border border-slate-800/60 bg-slate-900/60 p-5">
          <h2 className="text-sm font-semibold text-slate-200">Detected details</h2>
          <dl className="mt-4 space-y-2 text-sm text-slate-300">
            <div>
              <dt className="text-xs uppercase tracking-[0.3em] text-slate-500">Suggested name</dt>
              <dd className="mt-1 font-medium text-slate-100">{deviceName || "Unknown device"}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-[0.3em] text-slate-500">Device type</dt>
              <dd className="mt-1 font-medium capitalize text-slate-100">{deviceType}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-[0.3em] text-slate-500">
                Browser platform
              </dt>
              <dd className="mt-1 text-xs text-slate-400">
                {detectedNotes || "Unable to determine device details."}
              </dd>
            </div>
          </dl>
        </div>

        <div className="rounded-2xl border border-slate-800/60 bg-slate-900/60 p-5">
          <h2 className="text-sm font-semibold text-slate-200">Quick tips</h2>
          <ul className="mt-3 space-y-2 text-sm text-slate-300">
            <li className="flex gap-2">
              <span className="mt-1 block size-1.5 rounded-full bg-brand-blue/70" />
              Find the MAC address in your network settings. It usually looks like{" "}
              <code>AA:BB:CC:DD:EE:FF</code>.
            </li>
            <li className="flex gap-2">
              <span className="mt-1 block size-1.5 rounded-full bg-brand-blue/70" />
              Choose the owner responsible for this device. They will inherit lock schedules and
              policies.
            </li>
            <li className="flex gap-2">
              <span className="mt-1 block size-1.5 rounded-full bg-brand-blue/70" />
              Not listed? Reach out to an administrator to create the owner profile before
              registering.
            </li>
          </ul>
        </div>
      </section>

      {probableClients.length > 0 ? (
        <section className="space-y-4 rounded-2xl border border-slate-800/60 bg-slate-900/60 p-5">
          <header>
            <h2 className="text-sm font-semibold text-slate-200">Likely matches</h2>
            <p className="text-xs text-slate-400">
              We found devices recently active at your IP. Select one to pre-fill the form or
              continue manually.
            </p>
          </header>
          <div className="grid gap-3 md:grid-cols-2">
            {probableClients.map((client) => {
              const isSelected = selectedProbableMac === client.mac;
              return (
                <button
                  key={client.mac}
                  type="button"
                  onClick={() => handleSelectCandidate(client)}
                  className={cn(
                    "rounded-2xl border px-4 py-3 text-left transition",
                    isSelected
                      ? "border-brand-blue/60 bg-brand-blue/15 text-slate-100"
                      : "border-slate-800/60 bg-slate-900/60 text-slate-200 hover:border-brand-blue/40 hover:bg-slate-900",
                  )}
                >
                  <div className="flex items-center justify-between text-sm font-semibold">
                    <span>{client.name}</span>
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[11px] uppercase tracking-wider",
                        isSelected
                          ? "bg-brand-blue/80 text-white"
                          : "bg-slate-800/70 text-slate-400",
                      )}
                    >
                      {isSelected ? "Selected" : "Tap to select"}
                    </span>
                  </div>
                  <dl className="mt-3 space-y-1 text-xs text-slate-300">
                    <div className="flex justify-between gap-2">
                      <span className="text-slate-500">MAC</span>
                      <span className="font-mono text-slate-200">{client.mac.toUpperCase()}</span>
                    </div>
                    <div className="flex justify-between gap-2">
                      <span className="text-slate-500">IP</span>
                      <span className="font-mono text-slate-200">{client.ip ?? "Unknown"}</span>
                    </div>
                    <div className="flex justify-between gap-2">
                      <span className="text-slate-500">Vendor</span>
                      <span className="text-slate-200">{client.vendor ?? "Unknown vendor"}</span>
                    </div>
                    {client.lastSeen ? (
                      <div className="flex justify-between gap-2">
                        <span className="text-slate-500">Last seen</span>
                        <span className="text-slate-200">{formatTimestamp(client.lastSeen)}</span>
                      </div>
                    ) : null}
                  </dl>
                </button>
              );
            })}
          </div>
      </section>
    ) : null}

      <section className="space-y-4 rounded-2xl border border-slate-800/60 bg-slate-900/60 p-5">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">Active unregistered devices</h2>
            <p className="text-xs text-slate-400">
              These devices are currently on the network without an assigned owner.
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setLoadingUnregistered(true);
              void lockControllerService
                .loadUnregistered()
                .then((devices) => {
                  setUnregisteredDevices(devices);
                  setUnregisteredError(undefined);
                })
                .catch((error: Error) => {
                  setUnregisteredError(error.message);
                })
                .finally(() => setLoadingUnregistered(false));
            }}
            className="border border-transparent px-3 py-1 text-xs uppercase tracking-[0.25em] text-slate-300 hover:border-slate-700"
          >
            Refresh
          </Button>
        </header>
        {unregisteredError ? (
          <p className="rounded-xl border border-status-locked/40 bg-status-locked/10 px-4 py-3 text-sm text-status-locked">
            {unregisteredError}
          </p>
        ) : null}
        {loadingUnregistered ? (
          <p className="text-sm text-slate-400">Loading active clients…</p>
        ) : unregisteredDevices.length === 0 ? (
          <p className="text-sm text-slate-400">No unregistered devices detected right now.</p>
        ) : (
          <ul className="divide-y divide-slate-800/60">
            {unregisteredDevices.map((device) => {
              const pendingLock = pendingLockMacs.has(device.mac);
              return (
                <li
                  key={device.mac}
                  className="flex flex-wrap items-center justify-between gap-4 py-4"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-slate-100">{device.name}</span>
                      <span
                        className={cn(
                          "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold tracking-wide",
                          device.locked
                            ? "border-status-locked/40 text-status-locked"
                            : "border-status-unlocked/40 text-status-unlocked",
                        )}
                      >
                        {device.locked ? "Locked" : "Unlocked"}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-3 text-xs text-slate-400">
                      <span className="font-mono text-slate-200">
                        {device.mac.toUpperCase()}
                      </span>
                      {device.ip ? <span>IP {device.ip}</span> : null}
                      <span>{device.vendor ?? "Unknown vendor"}</span>
                      {device.lastSeen ? (
                        <span>Last seen {formatTimestamp(device.lastSeen)}</span>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex flex-shrink-0 items-center gap-2">
                    <Button
                      size="sm"
                      variant={device.locked ? "secondary" : "destructive"}
                      onClick={() => void handleToggleUnregisteredLock(device)}
                      disabled={pendingLock}
                    >
                      {pendingLock ? "Working…" : device.locked ? "Unlock" : "Lock"}
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => handlePrefillUnregistered(device)}
                    >
                      Register
                    </Button>
                    <a
                      href={`/devices?mac=${encodeURIComponent(device.mac)}`}
                      className="inline-flex items-center justify-center rounded-lg border border-slate-700/60 bg-slate-900/40 px-3 py-2 text-sm text-slate-200 transition hover:border-brand-blue/50 hover:text-slate-50"
                    >
                      Details
                    </a>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <form
        className="space-y-6 rounded-2xl border border-slate-800/70 bg-slate-900/70 p-6"
        onSubmit={(event) => {
          event.preventDefault();
          void handleSubmit();
        }}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-2 text-sm text-slate-200">
            MAC address
            <input
              required
              value={macAddress}
              onChange={(event) => setMacAddress(event.target.value)}
              placeholder="AA:BB:CC:DD:EE:FF"
              className="rounded-lg border border-slate-700/60 bg-slate-950/70 px-3 py-2 font-mono text-sm uppercase tracking-[0.25em] text-slate-100 placeholder:text-slate-600 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
            />
          </label>

          <label className="flex flex-col gap-2 text-sm text-slate-200">
            Owner
            <select
              value={ownerKey}
              disabled={loadingOwners}
              onChange={(event) => setOwnerKey(event.target.value)}
              className="rounded-lg border border-slate-700/60 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
            >
              <option value="">Select owner</option>
              {ownerOptions.map((owner) => (
                <option key={owner.key} value={owner.key}>
                  {owner.displayName}
                </option>
              ))}
            </select>
            <span className="text-xs text-slate-500">
              Need a new owner? Contact an administrator.
            </span>
          </label>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-2 text-sm text-slate-200">
            Device name
            <input
              value={deviceName}
              onChange={(event) => setDeviceName(event.target.value)}
              placeholder="Family Laptop"
              className="rounded-lg border border-slate-700/60 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
            />
            <span className="text-xs text-slate-500">
              Displayed in dashboards and lock schedules.
            </span>
          </label>

          <label className="flex flex-col gap-2 text-sm text-slate-200">
            Device type
            <select
              value={deviceType}
              onChange={(event) => setDeviceType(event.target.value)}
              className="rounded-lg border border-slate-700/60 bg-slate-950/70 px-3 py-2 text-sm capitalize text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
            >
              {availableTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex flex-col gap-3">
          <Button
            type="submit"
            className={cn(
              "w-full md:w-auto",
              submitState.status === "success" ? "bg-emerald-500/80 hover:bg-emerald-500" : null,
            )}
            disabled={!canSubmit}
          >
            {submitState.status === "submitting"
              ? "Registering…"
              : submitState.status === "success"
                ? "Device registered"
                : "Register device"}
          </Button>
          {submitState.status === "error" ? (
            <p className="text-sm text-status-locked">{submitState.message}</p>
          ) : null}
          {submitState.status === "success" ? (
            <p className="text-sm text-emerald-300">{submitState.message}</p>
          ) : null}
          {submitState.status === "idle" && submitState.message ? (
            <p className="text-xs text-slate-500">{submitState.message}</p>
          ) : null}
        </div>
      </form>
    </div>
  );
}
