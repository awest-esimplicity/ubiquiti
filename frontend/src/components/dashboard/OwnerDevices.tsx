import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { lockControllerService } from "@/lib/bootstrap/lockController";
import type { Device, OwnerSummary } from "@/lib/domain/models";

interface OwnerDevicesProps {
  ownerKey: string;
}

interface OwnerDevicesState {
  loading: boolean;
  owner?: OwnerSummary;
  devices: Device[];
  error?: string;
  pendingMacs: Set<string>;
}

const initialState: OwnerDevicesState = {
  loading: true,
  devices: [],
  pendingMacs: new Set<string>()
};

export function OwnerDevices({ ownerKey }: OwnerDevicesProps) {
  const [state, setState] = useState<OwnerDevicesState>(initialState);

  useEffect(() => {
    let cancelled = false;
    setState(initialState);

    const load = async () => {
      try {
        const snapshot = await lockControllerService.loadSnapshot();
        const owner = snapshot.owners.find((item) => item.key === ownerKey);
        if (!owner) {
          throw new Error("Owner not found");
        }
        if (!cancelled) {
          setState({
            loading: false,
            owner,
            devices: owner.devices,
            pendingMacs: new Set<string>()
          });
        }
      } catch (error) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Failed to load owner devices.";
          setState({
            loading: false,
            error: message,
            devices: [],
            pendingMacs: new Set<string>()
          });
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [ownerKey]);

  const refreshOwner = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: undefined }));
    try {
      const snapshot = await lockControllerService.loadSnapshot();
      const owner = snapshot.owners.find((item) => item.key === ownerKey);
      if (!owner) {
        throw new Error("Owner not found");
      }
      setState({
        loading: false,
        owner,
        devices: owner.devices,
        pendingMacs: new Set<string>()
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to refresh owner.";
      setState({
        loading: false,
        error: message,
        devices: [],
        pendingMacs: new Set<string>()
      });
    }
  }, [ownerKey]);

  const handleToggleDevice = useCallback(
    async (target: Device) => {
      let previousLocked = target.locked;

      setState((prev) => {
        const pendingMacs = new Set(prev.pendingMacs);
        pendingMacs.add(target.mac);
        const devices = prev.devices.map((device) => {
          if (device.mac === target.mac) {
            previousLocked = device.locked;
            return { ...device, locked: !device.locked };
          }
          return device;
        });
        return {
          ...prev,
          devices,
          pendingMacs,
          error: undefined
        };
      });

      try {
        if (previousLocked) {
          await lockControllerService.unlockDevice(target);
        } else {
          await lockControllerService.lockDevice(target);
        }
        setState((prev) => {
          const pendingMacs = new Set(prev.pendingMacs);
          pendingMacs.delete(target.mac);
          return {
            ...prev,
            pendingMacs
          };
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to update device lock state.";
        setState((prev) => {
          const pendingMacs = new Set(prev.pendingMacs);
          pendingMacs.delete(target.mac);
          const devices = prev.devices.map((device) =>
            device.mac === target.mac ? { ...device, locked: previousLocked } : device
          );
          return {
            ...prev,
            devices,
            pendingMacs,
            error: message
          };
        });
      }
    },
    []
  );

  const handleBulk = useCallback(
    async (locked: boolean) => {
      let previousDevices: Device[] = [];
      setState((prev) => {
        previousDevices = prev.devices;
        const pendingMacs = new Set(prev.pendingMacs);
        prev.devices.forEach((device) => pendingMacs.add(device.mac));
        const devices = prev.devices.map((device) => ({ ...device, locked }));
        return {
          ...prev,
          devices,
          pendingMacs,
          error: undefined
        };
      });

      const ownerSummary: OwnerSummary = {
        key: ownerKey,
        displayName: state.owner?.displayName ?? ownerKey,
        pin: state.owner?.pin,
        devices: []
      };

      try {
        if (locked) {
          await lockControllerService.lockOwner(ownerSummary);
        } else {
          await lockControllerService.unlockOwner(ownerSummary);
        }
        setState((prev) => ({
          ...prev,
          pendingMacs: new Set<string>()
        }));
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to update devices.";
        setState((prev) => ({
          ...prev,
          devices: previousDevices,
          pendingMacs: new Set<string>(),
          error: message
        }));
      }
    },
    [ownerKey, state.owner?.displayName, state.owner?.pin]
  );

  useEffect(() => {
    if (state.error) {
      const timeout = setTimeout(() => {
        setState((prev) => ({ ...prev, error: undefined }));
      }, 5000);
      return () => clearTimeout(timeout);
    }
    return undefined;
  }, [state.error]);

  const ownerDisplayName = state.owner?.displayName ?? ownerKey;
  const pendingMacs = state.pendingMacs;

  const totalLocked = useMemo(
    () => state.devices.filter((device) => device.locked).length,
    [state.devices]
  );

  if (state.loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-slate-300">
        <span className="inline-flex items-center gap-3 text-sm uppercase tracking-[0.4em]">
          <span className="h-2 w-2 animate-ping rounded-full bg-brand-blue" />
          Loading devices
        </span>
      </div>
    );
  }

  if (state.error && state.devices.length === 0) {
    return (
      <div className="rounded-2xl border border-status-locked/40 bg-status-locked/10 p-6 text-center text-status-locked">
        <h2 className="text-lg font-semibold">Something went wrong</h2>
        <p className="mt-2 text-sm">{state.error}</p>
        <Button className="mt-4" variant="secondary" onClick={() => void refreshOwner()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-slate-100">{ownerDisplayName}</h1>
          <p className="mt-1 text-sm text-slate-400">
            {state.devices.length} devices · {totalLocked} locked
          </p>
        </div>
        <div className="flex gap-3">
          <Button variant="destructive" className="px-4" onClick={() => void handleBulk(true)}>
            Lock all
          </Button>
          <Button variant="secondary" className="px-4" onClick={() => void handleBulk(false)}>
            Unlock all
          </Button>
        </div>
      </header>

      {state.error ? (
        <div className="rounded-2xl border border-status-locked/40 bg-status-locked/10 p-4 text-sm text-status-locked">
          {state.error}
        </div>
      ) : null}

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {state.devices.map((device) => (
          <DeviceCard
            key={device.mac}
            device={device}
            isPending={pendingMacs.has(device.mac)}
            onToggle={() => void handleToggleDevice(device)}
          />
        ))}
        {state.devices.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-slate-700/50 bg-slate-900/40 p-6 text-center text-sm text-slate-400 md:col-span-2 xl:col-span-4">
            No devices found for this owner.
          </p>
        ) : null}
      </div>

      <Button variant="ghost" onClick={() => void refreshOwner()} className="border border-transparent hover:border-slate-700">
        Refresh devices
      </Button>
    </div>
  );
}

interface DeviceCardProps {
  device: Device;
  isPending: boolean;
  onToggle: () => void;
}

function DeviceCard({ device, isPending, onToggle }: DeviceCardProps) {
  const pillClass = device.locked
    ? "border-status-locked/40 text-status-locked"
    : "border-status-unlocked/40 text-status-unlocked";
  const actionVariant = device.locked ? "secondary" : "destructive";
  const actionLabel = device.locked ? "Unlock" : "Lock";

  return (
    <article className="rounded-2xl border border-slate-700/50 bg-slate-900/50 p-5 transition hover:border-brand-blue/50 hover:bg-slate-900/70">
      <div>
        <h3 className="text-lg font-medium text-slate-50">{device.name}</h3>
        <p className="text-xs text-slate-500">{device.mac}</p>
        <span className={`mt-3 inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium ${pillClass}`}>
          {device.locked ? "Locked" : "Unlocked"}
        </span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-slate-400">
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Type</p>
          <p className="text-slate-300 capitalize">{device.type}</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Vendor</p>
          <p className="text-slate-300">{device.vendor ?? "Unknown"}</p>
        </div>
      </div>
      <div className="mt-4 flex justify-end">
        <Button variant={actionVariant} size="sm" onClick={onToggle} disabled={isPending}>
          {isPending ? "Working..." : actionLabel}
        </Button>
      </div>
    </article>
  );
}
