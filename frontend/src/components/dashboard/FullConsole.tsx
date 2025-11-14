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
  DeviceType,
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

interface RegistrationFormValues {
  ownerKey: string;
  name: string;
  type: string;
}

const REGISTRATION_TYPES: DeviceType[] = [
  "computer",
  "tv",
  "switch",
  "streaming",
  "console",
  "phone",
  "tablet",
  "unknown",
];

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
  const [registrationForms, setRegistrationForms] = useState<
    Record<string, RegistrationFormValues>
  >({});
  const [pendingRegistrationMacs, setPendingRegistrationMacs] = useState<Set<string>>(new Set());
  const [registrationSuccess, setRegistrationSuccess] = useState<Set<string>>(new Set());
  const [expandedRegistrations, setExpandedRegistrations] = useState<Set<string>>(new Set());

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

  useEffect(() => {
    if (!state.snapshot) {
      return;
    }
    const activeMacs = new Set(state.snapshot.unregistered.map((device) => device.mac));
    setRegistrationSuccess((prev) => {
      const next = new Set(Array.from(prev).filter((mac) => activeMacs.has(mac)));
      return next.size === prev.size ? prev : next;
    });
  }, [state.snapshot]);

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

  const updateSnapshot = useCallback(
    (mutator: (current: DashboardSnapshot) => DashboardSnapshot) => {
      setState((prev) => {
        if (!prev.snapshot) {
          return prev;
        }
        const nextSnapshot = mutator(prev.snapshot);
        return { ...prev, snapshot: nextSnapshot };
      });
    },
    [],
  );

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

  const handleToggleUnregistered = useCallback(
    (device: UnregisteredDevice) => {
      const desiredState = !device.locked;
      updateSnapshot((current) => {
        const unregistered = (current.unregistered ?? []).map((item) =>
          item.mac === device.mac ? { ...item, locked: desiredState } : item,
        );
        return { ...current, unregistered };
      });
    },
    [updateSnapshot],
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

  const handleRegistrationChange = useCallback(
    (mac: string, updates: Partial<RegistrationFormValues>, defaults: RegistrationFormValues) => {
      setRegistrationForms((prev) => {
        const current = prev[mac] ?? defaults;
        const next = { ...current, ...updates };
        return { ...prev, [mac]: next };
      });
    },
    [],
  );

  const handleRegisterDevice = useCallback(
    (device: UnregisteredDevice) => {
      const defaults: RegistrationFormValues = {
        ownerKey: "",
        name: device.name,
        type: "unknown",
      };
      const form = registrationForms[device.mac] ?? defaults;

      if (!form.ownerKey) {
        setState((prev) => ({
          ...prev,
          error: "Select an owner before registering this device.",
        }));
        return;
      }

      setPendingRegistrationMacs((prev) => {
        const next = new Set(prev);
        next.add(device.mac);
        return next;
      });

      lockControllerService
        .registerDevice(form.ownerKey, {
          mac: device.mac,
          name: form.name?.trim() || device.mac,
          type: form.type?.trim() || undefined,
        })
        .then(() => {
          setRegistrationForms((prev) => {
            const next = { ...prev };
            delete next[device.mac];
            return next;
          });
          setRegistrationSuccess((prev) => {
            const next = new Set(prev);
            next.add(device.mac);
            return next;
          });
          setExpandedRegistrations((prev) => {
            const next = new Set(prev);
            next.delete(device.mac);
            return next;
          });
          return refreshSnapshot();
        })
        .catch((error: Error) => {
          setState((prev) => ({
            ...prev,
            error: error.message,
          }));
        })
        .finally(() => {
          setPendingRegistrationMacs((prev) => {
            const next = new Set(prev);
            next.delete(device.mac);
            return next;
          });
        });
    },
    [refreshSnapshot, registrationForms],
  );

  const filtered = useMemo(
    () =>
      computeFilteredData(state.snapshot, searchTerm.trim(), statusFilter, ownerFilter, typeFilter),
    [state.snapshot, searchTerm, statusFilter, ownerFilter, typeFilter],
  );

  const toggleRegistrationPanel = useCallback((mac: string) => {
    setExpandedRegistrations((prev) => {
      const next = new Set(prev);
      if (next.has(mac)) {
        next.delete(mac);
      } else {
        next.add(mac);
      }
      return next;
    });
  }, []);

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

      {filtered.owners.length === 0 && filtered.unregistered.length === 0 ? (
        <div className="rounded-3xl border border-slate-700/40 bg-slate-900/40 p-10 text-center text-slate-400">
          No devices match the current filters. Adjust filters above to continue troubleshooting.
        </div>
      ) : null}

      {filtered.owners.map((owner, index) => (
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

          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {owner.devices.map((device) => (
              <article
                key={device.mac}
                className="overflow-hidden rounded-2xl border border-slate-700/40 bg-slate-900/50 p-5 transition hover:border-brand-blue/50 hover:bg-slate-900/70"
              >
                <div>
                  <h3 className="text-lg font-medium text-slate-50">{device.name}</h3>
                  <p className="text-xs text-slate-500">{device.mac}</p>
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
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400">
                  <div className="flex flex-wrap items-center gap-2 text-slate-300">
                    <span className="text-sm capitalize text-slate-200">{device.type}</span>
                    <span>•</span>
                    <span>{device.vendor ?? "Unknown vendor"}</span>
                  </div>
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
              </article>
            ))}
            {owner.devices.length === 0 ? (
              <p className="rounded-xl border border-dashed border-slate-700/40 bg-slate-900/30 p-6 text-sm text-slate-400">
                No devices match the current filters.
              </p>
            ) : null}
          </div>
        </section>
      ))}

      {filtered.unregistered.length > 0 ? (
        <section className="rounded-3xl border border-slate-700/40 bg-slate-900/40 p-6 shadow-card">
          <div className="flex items-center justify-between border-b border-slate-700/40 pb-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.35em] text-slate-500">Unregistered</p>
              <h2 className="mt-1 text-xl font-semibold text-slate-50">
                Active unregistered devices
              </h2>
            </div>
          </div>
          <div className="mt-5 grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {filtered.unregistered.map((device) => {
              const defaults: RegistrationFormValues = {
                ownerKey: "",
                name: device.name,
                type: "unknown",
              };
              const form = registrationForms[device.mac] ?? defaults;
              const isRegistering = pendingRegistrationMacs.has(device.mac);
              const isRegistered = registrationSuccess.has(device.mac);
              const ownerMatch =
                form.ownerKey && ownerOptions.find((owner) => owner.key === form.ownerKey);
              const vendorName = device.vendor ?? "Unknown vendor";
              const isUnknownVendor = vendorName.toLowerCase() === "unknown vendor";
              const isExpanded = expandedRegistrations.has(device.mac);

              return (
                <article
                  key={device.mac}
                className="hover:shadow-card-xl rounded-2xl border border-slate-700/40 bg-gradient-to-br from-slate-900/80 via-slate-900/60 to-slate-950/90 p-5 shadow-inner transition hover:border-brand-blue/50 overflow-hidden"
                >
                  <div className="space-y-2">
                    <div className="space-y-1">
                      <h3 className="text-lg font-semibold text-slate-50">{device.name}</h3>
                      <p className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
                        {device.mac}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span
                        className={cn(
                          "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold tracking-wide",
                          device.locked
                            ? "border-status-locked/40 text-status-locked"
                            : "border-status-unlocked/40 text-status-unlocked",
                        )}
                      >
                        {device.locked ? ICONS.locked : ICONS.unlocked}
                        {device.locked ? "Locked" : "Unlocked"}
                      </span>
                      <Button
                        size="sm"
                        variant={device.locked ? "secondary" : "destructive"}
                        onClick={() => handleToggleUnregistered(device)}
                        disabled={state.refreshing}
                        className="min-w-[88px]"
                      >
                        {device.locked ? "Unlock" : "Lock"}
                      </Button>
                    </div>
                  </div>

                  <dl className="mt-4 grid grid-cols-2 gap-y-2 text-sm text-slate-200">
                    <div>
                      <dt className="text-xs uppercase tracking-[0.3em] text-slate-500">IP</dt>
                      <dd className="mt-1 font-medium">{device.ip ?? "Unknown"}</dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-[0.3em] text-slate-500">
                        Last seen
                      </dt>
                      <dd className="mt-1 font-medium">
                        {device.lastSeen ? formatTimestamp(device.lastSeen) : "Unavailable"}
                      </dd>
                    </div>
                    <div className="col-span-2">
                      <dt className="text-xs uppercase tracking-[0.3em] text-slate-500">Vendor</dt>
                      <dd className="mt-1 flex items-center gap-2 font-medium">
                        {isUnknownVendor ? (
                          <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-amber-200">
                            {ICONS.alert}
                            Unknown vendor
                          </span>
                        ) : (
                          vendorName
                        )}
                      </dd>
                    </div>
                  </dl>

                  <div className="mt-6">
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full justify-between text-slate-200"
                      onClick={() => toggleRegistrationPanel(device.mac)}
                    >
                      <span className="text-sm font-medium">
                        {isExpanded ? "Hide registration" : "Register this device"}
                      </span>
                      <span className="text-xs uppercase tracking-[0.25em] text-slate-400">
                        {isExpanded ? "−" : "+"}
                      </span>
                    </Button>
                  </div>

                  {isExpanded ? (
                    <div className="mt-4 space-y-4 rounded-2xl border border-slate-800/60 bg-slate-950/40 p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <h4 className="text-sm font-semibold text-slate-200">
                            Register this device
                          </h4>
                        <p className="text-xs text-slate-400">
                          Assign an owner to move the client into the managed inventory.
                        </p>
                      </div>
                      {isRegistered ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-300">
                          {ICONS.unlocked}
                          Registered
                        </span>
                      ) : null}
                    </div>

                    <div className="space-y-3">
                      <label className="flex flex-col gap-1 text-sm text-slate-300">
                        <span>Device name</span>
                        <span className="text-xs text-slate-500">
                          Optional override – defaults to the MAC address.
                        </span>
                      </label>
                      <input
                        type="text"
                        value={form.name}
                        onChange={(event) =>
                          handleRegistrationChange(
                            device.mac,
                            { name: event.target.value },
                            defaults,
                          )
                        }
                        disabled={isRegistering || state.refreshing}
                        placeholder={device.mac}
                        className="w-full rounded-lg border border-slate-700/50 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
                      />
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-slate-300">Assign owner</span>
                          {ownerMatch ? (
                            <span className="inline-flex items-center gap-2 rounded-full bg-slate-800/70 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider text-slate-200">
                              <span className="flex size-5 items-center justify-center rounded-full bg-brand-blue/20 text-[10px] font-semibold text-brand-blue/80">
                                {ownerMatch.displayName.slice(0, 1)}
                              </span>
                              {ownerMatch.displayName}
                            </span>
                          ) : null}
                        </div>
                        <select
                          value={form.ownerKey}
                          onChange={(event) =>
                            handleRegistrationChange(
                              device.mac,
                              { ownerKey: event.target.value },
                              defaults,
                            )
                          }
                          disabled={isRegistering || state.refreshing}
                          className="w-full rounded-lg border border-slate-700/50 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
                        >
                          <option value="">Select owner</option>
                          {ownerOptions.map((owner) => (
                            <option key={owner.key} value={owner.key}>
                              {owner.displayName}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="flex flex-col gap-1">
                        <span className="text-sm text-slate-300">Device type</span>
                        <select
                          value={form.type}
                          onChange={(event) =>
                            handleRegistrationChange(
                              device.mac,
                              { type: event.target.value },
                              defaults,
                            )
                          }
                          disabled={isRegistering || state.refreshing}
                          className="w-full rounded-lg border border-slate-700/50 bg-slate-950/70 px-3 py-2 text-sm capitalize text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
                        >
                          {REGISTRATION_TYPES.map((type) => (
                            <option key={type} value={type}>
                              {type}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <Button
                        size="sm"
                        onClick={() => handleRegisterDevice(device)}
                        disabled={
                          !form.ownerKey || isRegistering || state.refreshing || isRegistered
                        }
                        className="min-w-[140px]"
                      >
                        {isRegistering
                          ? "Registering…"
                          : isRegistered
                            ? "Registered"
                            : "Register to owner"}
                      </Button>
                      <p className="text-xs text-slate-500">
                        Registration removes the device from this list and applies owner policies.
                      </p>
                    </div>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        </section>
      ) : null}
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
