import { useCallback, useEffect, useMemo, useState } from "react";

import { ICONS } from "@/components/icons";
import { PinModal } from "@/components/modals/PinModal";
import { ScheduleModal } from "@/components/modals/ScheduleModal";
import { Button } from "@/components/ui/button";
import { lockControllerService } from "@/lib/bootstrap/lockController";
import { MASTER_OWNER, MASTER_PIN } from "@/lib/domain/constants";
import type {
  DashboardSnapshot,
  Device,
  OwnerSummary,
  UnregisteredDevice,
} from "@/lib/domain/models";
import { cn } from "@/lib/utils/cn";
import { formatTimestamp } from "@/lib/utils/date";

type StatusFilter = "all" | "locked" | "unlocked";

interface FullConsoleState {
  snapshot: DashboardSnapshot | null;
  loading: boolean;
  refreshing: boolean;
  error?: string;
}

interface FilterCounts {
  totalDevices: number;
  lockedDevices: number;
  unknownVendors: number;
  filteredDevices: number;
  filteredLocked: number;
  filteredUnknown: number;
}

interface FilteredOwners {
  owners: OwnerSummary[];
  unregistered: UnregisteredDevice[];
  counts: FilterCounts;
}

const STATUS_OPTIONS: { label: string; value: StatusFilter }[] = [
  { label: "All statuses", value: "all" },
  { label: "Locked only", value: "locked" },
  { label: "Unlocked only", value: "unlocked" },
];

function filterDeviceByStatus(device: Device | UnregisteredDevice, status: StatusFilter) {
  if (status === "all") {
    return true;
  }
  return status === "locked" ? device.locked : !device.locked;
}

function matchesSearch(device: Device | UnregisteredDevice, searchTerm: string) {
  if (!searchTerm) {
    return true;
  }
  const value = searchTerm.toLowerCase();
  const candidates = [
    "name" in device ? device.name : "",
    "mac" in device ? device.mac : "",
    "vendor" in device ? (device.vendor ?? "") : "",
    "type" in device ? (device.type ?? "") : "",
  ];
  return candidates.some((entry) => entry?.toLowerCase().includes(value));
}

function computeFilteredData(
  snapshot: DashboardSnapshot | null,
  searchTerm: string,
  status: StatusFilter,
  ownerFilter: string,
  typeFilter: string,
): FilteredOwners {
  if (!snapshot) {
    return {
      owners: [],
      unregistered: [],
      counts: {
        totalDevices: 0,
        lockedDevices: 0,
        unknownVendors: 0,
        filteredDevices: 0,
        filteredLocked: 0,
        filteredUnknown: 0,
      },
    };
  }

  const filteredOwners = snapshot.owners
    .filter((owner) => ownerFilter === "all" || owner.key === ownerFilter)
    .map<OwnerSummary>((owner) => ({
      ...owner,
      devices: owner.devices.filter(
        (device) =>
          filterDeviceByStatus(device, status) &&
          matchesSearch(device, searchTerm) &&
          (typeFilter === "all" || device.type === typeFilter),
      ),
    }))
    .filter((owner) => owner.devices.length > 0);

  const filteredUnregistered = (snapshot.unregistered ?? []).filter(
    (device) => filterDeviceByStatus(device, status) && matchesSearch(device, searchTerm),
  );

  const filteredDevices = filteredOwners.flatMap((owner) => owner.devices);
  const filteredLocked = filteredDevices.filter((device) => device.locked).length;
  const filteredUnknown =
    filteredDevices.filter((device) => !device.vendor || device.vendor.toLowerCase() === "unknown")
      .length +
    filteredUnregistered.filter(
      (device) => !device.vendor || device.vendor.toLowerCase() === "unknown",
    ).length;

  return {
    owners: filteredOwners,
    unregistered: filteredUnregistered,
    counts: {
      totalDevices: snapshot.metadata.totalDevices,
      lockedDevices: snapshot.metadata.lockedDevices,
      unknownVendors: snapshot.metadata.unknownVendors,
      filteredDevices: filteredDevices.length + filteredUnregistered.length,
      filteredLocked,
      filteredUnknown,
    },
  };
}

export function FullConsole() {
  const [state, setState] = useState<FullConsoleState>({
    snapshot: null,
    loading: false,
    refreshing: false,
  });
  const [isUnlocked, setIsUnlocked] = useState(false);
  const [pinValue, setPinValue] = useState("");
  const [pinError, setPinError] = useState<string>();
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [ownerFilter, setOwnerFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [scheduleOwner, setScheduleOwner] = useState<{ key: string; name: string }>();
  const [pendingDeviceMacs, setPendingDeviceMacs] = useState<Set<string>>(new Set());
  const [pendingOwnerKeys, setPendingOwnerKeys] = useState<Set<string>>(new Set());
  const [pendingFilteredAction, setPendingFilteredAction] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const unlocked = window.sessionStorage.getItem("unifi-master-console") === "true";
    if (unlocked) {
      setIsUnlocked(true);
    }
  }, []);

  useEffect(() => {
    if (!isUnlocked) {
      return;
    }
    setState({ snapshot: null, loading: true });
    lockControllerService
      .loadSnapshot()
      .then((snapshot) => {
        setState({ snapshot, loading: false, refreshing: false, error: undefined });
      })
      .catch((error: Error) => {
        setState({ snapshot: null, loading: false, refreshing: false, error: error.message });
      });
  }, [isUnlocked]);

  const handlePinDigit = useCallback((digit: string) => {
    setPinValue((prev) => (prev.length >= 4 ? prev : prev + digit));
    setPinError(undefined);
  }, []);

  const handlePinBackspace = useCallback(() => {
    setPinValue((prev) => prev.slice(0, -1));
    setPinError(undefined);
  }, []);

  const handlePinClear = useCallback(() => {
    setPinValue("");
    setPinError(undefined);
  }, []);

  const handlePinCancel = useCallback(() => {
    if (typeof window !== "undefined") {
      window.location.href = "/";
    }
  }, []);

  const refreshSnapshot = useCallback(() => {
    setState((prev) => ({
      ...prev,
      refreshing: true,
      error: undefined,
    }));
    return lockControllerService
      .refresh()
      .then((snapshot) => {
        setState({
          snapshot,
          loading: false,
          refreshing: false,
          error: undefined,
        });
      })
      .catch((error: Error) => {
        setState((prev) => ({
          ...prev,
          refreshing: false,
          error: error.message,
        }));
      });
  }, []);

  const handleOpenSchedule = useCallback((owner: OwnerSummary) => {
    setScheduleOwner({ key: owner.key, name: owner.displayName });
  }, []);

  const handleCloseSchedule = useCallback(() => {
    setScheduleOwner(undefined);
  }, []);

  const handlePinSubmit = useCallback(() => {
    if (pinValue === MASTER_PIN) {
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem("unifi-master-console", "true");
      }
      setIsUnlocked(true);
      setPinValue("");
      setPinError(undefined);
    } else {
      setPinError("Invalid PIN. Please try again.");
      setPinValue("");
    }
  }, [pinValue]);

  const handleToggleDevice = useCallback(
    (ownerKey: string, device: Device) => {
      setPendingDeviceMacs((prev) => {
        const next = new Set(prev);
        next.add(device.mac);
        return next;
      });

      const actionPromise = device.locked
        ? lockControllerService.unlockDevice(device)
        : lockControllerService.lockDevice(device);

      actionPromise
        .then(() => refreshSnapshot())
        .catch((error: Error) => {
          setState((prev) => ({
            ...prev,
            error: error.message,
          }));
        })
        .finally(() => {
          setPendingDeviceMacs((prev) => {
            const next = new Set(prev);
            next.delete(device.mac);
            return next;
          });
        });
    },
    [refreshSnapshot],
  );

  const handleOwnerBulk = useCallback(
    (ownerKey: string, locked: boolean) => {
      setPendingOwnerKeys((prev) => {
        const next = new Set(prev);
        next.add(ownerKey);
        return next;
      });

      const ownerSummary = state.snapshot?.owners.find((owner) => owner.key === ownerKey);
      if (!ownerSummary) {
        setState((prev) => ({
          ...prev,
          error: "Owner not found.",
        }));
        setPendingOwnerKeys((prev) => {
          const next = new Set(prev);
          next.delete(ownerKey);
          return next;
        });
        return;
      }

      const actionPromise = locked
        ? lockControllerService.lockOwner(ownerSummary)
        : lockControllerService.unlockOwner(ownerSummary);

      actionPromise
        .then(() => refreshSnapshot())
        .catch((error: Error) => {
          setState((prev) => ({
            ...prev,
            error: error.message,
          }));
        })
        .finally(() => {
          setPendingOwnerKeys((prev) => {
            const next = new Set(prev);
            next.delete(ownerKey);
            return next;
          });
        });
    },
    [refreshSnapshot, state.snapshot?.owners],
  );

  const filtered = useMemo(
    () =>
      computeFilteredData(state.snapshot, searchTerm.trim(), statusFilter, ownerFilter, typeFilter),
    [state.snapshot, searchTerm, statusFilter, ownerFilter, typeFilter],
  );

  const metadata = state.snapshot?.metadata;
  const inventoryLockRate =
    metadata && metadata.totalDevices > 0
      ? Math.round((metadata.lockedDevices / metadata.totalDevices) * 100)
      : 0;
  const hasFilteredResults = filtered.counts.filteredDevices > 0;
  const ownerOptions = useMemo(() => state.snapshot?.owners ?? [], [state.snapshot]);
  const deviceTypeOptions = useMemo(() => {
    const types = new Set<string>();
    ownerOptions.forEach((owner) => {
      owner.devices.forEach((device) => types.add(device.type));
    });
    return Array.from(types).sort();
  }, [ownerOptions]);

  const handleResetFilters = useCallback(() => {
    setSearchTerm("");
    setStatusFilter("all");
    setOwnerFilter("all");
    setTypeFilter("all");
  }, []);

  const handleOwnerFilterChange = useCallback((value: string) => {
    setOwnerFilter(value);
  }, []);

  const handleTypeFilterChange = useCallback((value: string) => {
    setTypeFilter(value);
  }, []);

  const handleFilteredBulk = useCallback(
    (locked: boolean) => {
      if (filtered.owners.length === 0) {
        return;
      }

      const registeredDevices = filtered.owners.flatMap((owner) => owner.devices);
      if (registeredDevices.length === 0) {
        return;
      }

      setPendingFilteredAction(true);

      const actionPromise = locked
        ? lockControllerService.lockFiltered(registeredDevices)
        : lockControllerService.unlockFiltered(registeredDevices);

      actionPromise
        .then(() => refreshSnapshot())
        .catch((error: Error) => {
          setState((prev) => ({
            ...prev,
            error: error.message,
          }));
        })
        .finally(() => {
          setPendingFilteredAction(false);
        });
    },
    [filtered, refreshSnapshot],
  );

  if (!isUnlocked) {
    return (
      <PinModal
        owner={MASTER_OWNER}
        pinValue={pinValue}
        error={pinError}
        onDigit={handlePinDigit}
        onBackspace={handlePinBackspace}
        onClear={handlePinClear}
        onCancel={handlePinCancel}
        onSubmit={handlePinSubmit}
      />
    );
  }

  if (state.loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-slate-300">
        <span className="inline-flex items-center gap-3 text-sm uppercase tracking-[0.4em]">
          <span className="h-2 w-2 animate-ping rounded-full bg-brand-blue" />
          Loading console
        </span>
      </div>
    );
  }

  if (state.error) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="rounded-2xl border border-status-locked/40 bg-status-locked/10 px-6 py-5 text-status-locked">
          <h2 className="text-lg font-semibold">Unable to load device console</h2>
          <p className="mt-2 text-sm">{state.error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-10 pb-20">
      <header className="flex flex-wrap items-center justify-between gap-6">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-50">
            Full device console
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-300">
            Review every managed device, apply bulk network locks, and investigate unknown clients
            with advanced filtering.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <a
            href="/"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-600/60 bg-slate-900/40 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-brand-blue/50 hover:text-slate-50"
          >
            ← All owners
          </a>
          <a
            href="/register"
            className="inline-flex items-center gap-2 rounded-lg border border-brand-blue/40 bg-brand-blue/20 px-4 py-2 text-sm font-semibold text-brand-blue transition hover:border-brand-blue hover:bg-brand-blue/30 hover:text-white"
          >
            Register a device
          </a>
          <a
            href="/manage"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-600/60 bg-slate-900/40 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-brand-blue/50 hover:text-slate-50"
          >
            Manage owners &amp; types
          </a>
          <a
            href="/activity"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-600/60 bg-slate-900/40 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-brand-blue/50 hover:text-slate-50"
          >
            Control log
          </a>
        </div>
      </header>

      <section className="rounded-3xl border border-slate-700/40 bg-slate-900/40 p-6 shadow-card">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-4">
            <div className="flex flex-col gap-2">
              <label
                htmlFor="console-owner"
                className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400"
              >
                Owner
              </label>
              <select
                id="console-owner"
                value={ownerFilter}
                onChange={(event) => handleOwnerFilterChange(event.target.value)}
                className="w-52 rounded-lg border border-slate-700/50 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
              >
                <option value="all">All owners</option>
                {ownerOptions.map((owner) => (
                  <option key={owner.key} value={owner.key}>
                    {owner.displayName}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-2">
              <label
                htmlFor="console-type"
                className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400"
              >
                Type
              </label>
              <select
                id="console-type"
                value={typeFilter}
                onChange={(event) => handleTypeFilterChange(event.target.value)}
                className="w-48 rounded-lg border border-slate-700/50 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
              >
                <option value="all">All types</option>
                {deviceTypeOptions.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-2">
              <label
                htmlFor="console-search"
                className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400"
              >
                Search
              </label>
              <input
                id="console-search"
                type="search"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Search by name, MAC, vendor…"
                className="w-full min-w-[220px] rounded-lg border border-slate-700/50 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 shadow-inner focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue lg:w-64"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label
                htmlFor="console-status"
                className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400"
              >
                Status
              </label>
              <select
                id="console-status"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
                className="w-full rounded-lg border border-slate-700/50 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue lg:w-48"
              >
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="ghost"
              onClick={handleResetFilters}
              className="border border-transparent hover:border-slate-700"
            >
              Reset filters
            </Button>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                onClick={() => handleFilteredBulk(false)}
                disabled={!hasFilteredResults || pendingFilteredAction || state.refreshing}
              >
                {pendingFilteredAction ? "Working…" : "Unlock filtered"}
              </Button>
              <Button
                variant="destructive"
                onClick={() => handleFilteredBulk(true)}
                disabled={!hasFilteredResults || pendingFilteredAction || state.refreshing}
              >
                {pendingFilteredAction ? "Working…" : "Lock filtered"}
              </Button>
            </div>
          </div>
        </div>

        <details className="mt-5 rounded-2xl border border-slate-700/50 bg-slate-900/50 p-4 text-slate-200">
          <summary className="cursor-pointer text-sm font-semibold text-slate-200 hover:text-slate-50">
            Filter details
          </summary>
          <div className="mt-4 grid gap-5 md:grid-cols-3">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Total devices</p>
              <p className="mt-2 text-2xl font-semibold text-slate-50">
                {filtered.counts.totalDevices}
              </p>
              <p className="mt-1 text-xs text-slate-500">Registered across the network</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Locked devices</p>
              <p className="mt-2 text-2xl font-semibold text-slate-50">
                {filtered.counts.lockedDevices}
              </p>
              <p className="mt-1 text-xs text-slate-500">{inventoryLockRate}% of inventory</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Unknown vendors</p>
              <p className="mt-2 text-2xl font-semibold text-slate-50">
                {filtered.counts.unknownVendors}
              </p>
              <p className="mt-1 text-xs text-slate-500">Devices missing vendor metadata</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Filtered devices</p>
              <p className="mt-2 text-2xl font-semibold text-slate-50">
                {filtered.counts.filteredDevices}
              </p>
              <p className="mt-1 text-xs text-slate-500">Match current filters</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Filtered locked</p>
              <p className="mt-2 text-2xl font-semibold text-slate-50">
                {filtered.counts.filteredLocked}
              </p>
              <p className="mt-1 text-xs text-slate-500">Locks within filtered set</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Filtered unknown</p>
              <p className="mt-2 text-2xl font-semibold text-slate-50">
                {filtered.counts.filteredUnknown}
              </p>
              <p className="mt-1 text-xs text-slate-500">Filtered devices without vendors</p>
            </div>
          </div>
        </details>
        <div className="mt-5 text-xs uppercase tracking-[0.3em] text-slate-500">
          Last sync • {metadata ? formatTimestamp(metadata.lastSync) : "Unavailable"}
        </div>
      </section>

      {filtered.owners.length === 0 ? (
        <div className="rounded-3xl border border-slate-700/40 bg-slate-900/40 p-10 text-center text-slate-400">
          No devices match the current filters. Adjust filters above to continue troubleshooting.
        </div>
      ) : null}

      {filtered.owners.map((owner, index) => {
        const lockedCount = owner.devices.filter((device) => device.locked).length;
        const typeCounts = owner.devices.reduce<Record<string, number>>((acc, device) => {
          acc[device.type] = (acc[device.type] ?? 0) + 1;
          return acc;
        }, {});
        const typeEntries = Object.entries(typeCounts).sort(([a], [b]) => a.localeCompare(b));
        const unknownVendors = owner.devices.filter(
          (device) => !device.vendor || device.vendor.toLowerCase() === "unknown vendor",
        ).length;
        const metrics: Array<{ label: string; value: string }> = [
          { label: "Total devices", value: String(owner.devices.length) },
          { label: "Locked devices", value: String(lockedCount) },
          { label: "Unlocked devices", value: String(owner.devices.length - lockedCount) },
          { label: "Unknown vendors", value: String(unknownVendors) },
        ];

        return (
          <section
            key={owner.key}
            className={cn(
              "space-y-4 rounded-3xl border border-slate-700/50 bg-slate-900/40 p-6 shadow-inner transition",
              index > 0 ? "relative" : "",
            )}
          >
            {index > 0 ? <div className="absolute inset-x-6 -top-4 h-px bg-slate-800/70" /> : null}
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-700/40 pb-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.35em] text-slate-500">Owner</p>
              <h2 className="mt-1 text-2xl font-semibold text-slate-50">{owner.displayName}</h2>
            </div>
            <div className="flex gap-3">
              <Button variant="outline" onClick={() => handleOpenSchedule(owner)}>
                Schedule
              </Button>
              <Button
                variant="destructive"
                  onClick={() => handleOwnerBulk(owner.key, true)}
                  disabled={pendingOwnerKeys.has(owner.key) || state.refreshing}
                >
                  {pendingOwnerKeys.has(owner.key) ? "Working…" : "Lock all"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => handleOwnerBulk(owner.key, false)}
                  disabled={pendingOwnerKeys.has(owner.key) || state.refreshing}
                >
                  {pendingOwnerKeys.has(owner.key) ? "Working…" : "Unlock all"}
                </Button>
              </div>
            </div>

            <details className="rounded-2xl border border-slate-700/40 bg-slate-950/40 px-4 py-3 text-slate-200">
              <summary className="cursor-pointer text-sm font-medium text-slate-100">
                Control summary
              </summary>
              <div className="mt-3 overflow-hidden rounded-2xl border border-slate-800/40 bg-slate-950/30">
                <div className="divide-y divide-slate-800/60">
                  {metrics.map((metric) => (
                    <div
                      key={`${owner.key}-${metric.label}`}
                      className="flex items-center justify-between gap-6 px-4 py-3"
                    >
                      <span className="text-xs uppercase tracking-[0.3em] text-slate-500">
                        {metric.label}
                      </span>
                      <span className="text-base font-semibold text-slate-50">{metric.value}</span>
                    </div>
                  ))}
                  <div className="px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
                      Device types
                    </p>
                    {typeEntries.length > 0 ? (
                      <ul className="mt-2 space-y-2 text-sm text-slate-200">
                        {typeEntries.map(([type, count]) => (
                          <li
                            key={`${owner.key}-${type}`}
                            className="flex items-center justify-between gap-4 capitalize"
                          >
                            <span>{type}</span>
                            <span className="text-slate-300">{count}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-xs text-slate-500">
                        No device types available in the current filters.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </details>

            <div className="grid auto-rows-fr gap-6 md:grid-cols-2 xl:grid-cols-4">
              {owner.devices.map((device) => (
                <article
                  key={device.mac}
                  className="relative flex h-full flex-col overflow-hidden rounded-2xl border border-slate-700/40 bg-slate-900/50 p-5 transition hover:border-brand-blue/50 hover:bg-slate-900/70"
                >
                  <div className="flex-1 pr-10">
                    <h3 className="text-lg font-medium leading-tight text-slate-50">{device.name}</h3>
                    <p className="mt-1 text-xs text-slate-500 break-all">{device.mac}</p>
                    <span
                      className={cn(
                        "mt-3 inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium",
                        device.locked
                          ? "border-status-locked/40 text-status-locked"
                          : "border-status-unlocked/40 text-status-unlocked",
                      )}
                    >
                      {device.locked ? ICONS.locked : ICONS.unlocked}
                      {device.locked ? "Locked" : "Unlocked"}
                    </span>
                    <a
                      href={`/devices?mac=${encodeURIComponent(device.mac)}`}
                      className="absolute right-4 top-4 inline-flex h-7 w-7 items-center justify-center rounded-full border border-slate-700/50 bg-slate-900/60 text-slate-300 transition hover:border-brand-blue/50 hover:text-white"
                      title={`View activity details for ${device.name}`}
                      aria-label={`View activity details for ${device.name}`}
                    >
                      <span aria-hidden>{ICONS.info}</span>
                    </a>
                  </div>

                  <div className="mt-4 flex flex-nowrap items-center justify-between gap-3 text-xs text-slate-400">
                    <div className="flex min-w-0 items-center gap-2 text-slate-300">
                      <span className="text-sm capitalize text-slate-200">{device.type}</span>
                      <span className="text-slate-500">•</span>
                      <span className="truncate text-xs text-slate-500">
                        {device.vendor ?? "Unknown vendor"}
                      </span>
                    </div>
                    <div className="flex flex-shrink-0 items-center gap-2">
                      <Button
                        size="sm"
                        variant={device.locked ? "secondary" : "destructive"}
                        onClick={() => handleToggleDevice(owner.key, device)}
                        disabled={pendingDeviceMacs.has(device.mac) || state.refreshing}
                      >
                        {pendingDeviceMacs.has(device.mac)
                          ? "Working…"
                          : device.locked
                            ? "Unlock"
                            : "Lock"}
                      </Button>
                    </div>
                  </div>
                </article>
              ))}
              {owner.devices.length === 0 ? (
                <p className="rounded-xl border border-dashed border-slate-700/40 bg-slate-900/30 p-6 text-sm text-slate-400 md:col-span-2 xl:col-span-4">
                  No devices match the current filters.
                </p>
              ) : null}
            </div>
          </section>
        );
      })}

      {/* Unregistered devices are shown on the Register page */}

      {scheduleOwner ? (
        <ScheduleModal
          ownerKey={scheduleOwner.key}
          ownerName={scheduleOwner.name}
          onClose={handleCloseSchedule}
        />
      ) : null}
    </div>
  );
}
