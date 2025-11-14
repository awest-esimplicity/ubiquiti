import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import type { OwnerInfo } from "@/lib/api/types";
import { adminService } from "@/lib/bootstrap/admin";
import { cn } from "@/lib/utils/cn";

interface OwnerFormState {
  displayName: string;
  pin: string;
}

interface DeviceTypeFormState {
  name: string;
}

export function ManageInventory() {
  const [owners, setOwners] = useState<OwnerInfo[]>([]);
  const [deviceTypes, setDeviceTypes] = useState<string[]>([]);
  const [ownerForm, setOwnerForm] = useState<OwnerFormState>({ displayName: "", pin: "" });
  const [typeForm, setTypeForm] = useState<DeviceTypeFormState>({ name: "" });
  const [ownerSubmitting, setOwnerSubmitting] = useState(false);
  const [typeSubmitting, setTypeSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      try {
        const [ownerList, types] = await Promise.all([
          adminService.listOwners(),
          adminService.listDeviceTypes(),
        ]);
        if (cancelled) {
          return;
        }
        setOwners(ownerList);
        setDeviceTypes(types);
      } catch (err) {
        if (cancelled) {
          return;
        }
        const message = err instanceof Error ? err.message : "Unable to load management data.";
        setError(message);
      }
    }
    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  const sortedOwners = useMemo(
    () => [...owners].sort((a, b) => a.displayName.localeCompare(b.displayName)),
    [owners],
  );

  const sortedDeviceTypes = useMemo(
    () => [...deviceTypes].sort((a, b) => a.localeCompare(b)),
    [deviceTypes],
  );

  const handleOwnerSubmit = async () => {
    setOwnerSubmitting(true);
    setFeedback(undefined);
    setError(undefined);
    try {
      const created = await adminService.createOwner(ownerForm.displayName, ownerForm.pin);
      setOwners((prev) => [...prev, created]);
      setOwnerForm({ displayName: "", pin: "" });
      setFeedback(`Owner “${created.displayName}” created successfully.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to create owner.";
      setError(message);
    } finally {
      setOwnerSubmitting(false);
    }
  };

  const handleDeviceTypeSubmit = async () => {
    setTypeSubmitting(true);
    setFeedback(undefined);
    setError(undefined);
    try {
      const updated = await adminService.createDeviceType(typeForm.name);
      setDeviceTypes(updated);
      setTypeForm({ name: "" });
      setFeedback(`Device type “${typeForm.name.trim()}” added.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to add device type.";
      setError(message);
    } finally {
      setTypeSubmitting(false);
    }
  };

  return (
    <div className="space-y-10">
      <header className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.35em] text-slate-500">Network directory</p>
        <h1 className="text-3xl font-semibold text-slate-50">Manage owners &amp; device types</h1>
        <p className="text-sm text-slate-300">
          Add new household members or device classifications. These updates immediately become
          available in the console and self-registration flows.
        </p>
      </header>

      {feedback ? (
        <div className="rounded-2xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
          {feedback}
        </div>
      ) : null}

      {error ? (
        <div className="rounded-2xl border border-status-locked/40 bg-status-locked/10 px-4 py-3 text-sm text-status-locked">
          {error}
        </div>
      ) : null}

      <section className="grid gap-6 md:grid-cols-2">
        <div className="space-y-4 rounded-3xl border border-slate-800/60 bg-slate-900/60 p-6">
          <h2 className="text-sm font-semibold text-slate-100">Create owner</h2>
          <p className="text-xs text-slate-400">
            Owners require a display name and a four-digit pin used for console unlocking.
          </p>
          <label className="flex flex-col gap-2 text-sm text-slate-200">
            Display name
            <input
              value={ownerForm.displayName}
              onChange={(event) =>
                setOwnerForm((prev) => ({ ...prev, displayName: event.target.value }))
              }
              placeholder="Household member or location"
              className="rounded-lg border border-slate-700/60 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
            />
          </label>
          <label className="flex flex-col gap-2 text-sm text-slate-200">
            PIN
            <input
              value={ownerForm.pin}
              onChange={(event) => setOwnerForm((prev) => ({ ...prev, pin: event.target.value }))}
              placeholder="1234"
              className="w-40 rounded-lg border border-slate-700/60 bg-slate-950/70 px-3 py-2 text-sm tracking-[0.5em] text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
            />
            <span className="text-xs text-slate-500">
              Avoid reusing sensitive codes. PINs are stored as plain text in mock mode.
            </span>
          </label>
          <Button
            onClick={() => {
              void handleOwnerSubmit();
            }}
            disabled={
              ownerSubmitting || ownerForm.displayName.trim() === "" || ownerForm.pin.trim() === ""
            }
            className={cn("w-full md:w-auto", ownerSubmitting ? "opacity-80" : undefined)}
          >
            {ownerSubmitting ? "Creating owner…" : "Create owner"}
          </Button>
        </div>

        <div className="space-y-4 rounded-3xl border border-slate-800/60 bg-slate-900/60 p-6">
          <h2 className="text-sm font-semibold text-slate-100">Add device type</h2>
          <p className="text-xs text-slate-400">
            Device types improve filtering and reporting. They appear as options in
            self-registration and the console filters.
          </p>
          <label className="flex flex-col gap-2 text-sm text-slate-200">
            Type label
            <input
              value={typeForm.name}
              onChange={(event) => setTypeForm({ name: event.target.value })}
              placeholder="Smart speaker"
              className="rounded-lg border border-slate-700/60 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
            />
          </label>
          <Button
            onClick={() => {
              void handleDeviceTypeSubmit();
            }}
            disabled={typeSubmitting || typeForm.name.trim() === ""}
            className={cn("w-full md:w-auto", typeSubmitting ? "opacity-80" : undefined)}
          >
            {typeSubmitting ? "Adding type…" : "Add device type"}
          </Button>
        </div>
      </section>

      <section className="grid gap-6 md:grid-cols-2">
        <div className="rounded-3xl border border-slate-800/60 bg-slate-900/60 p-6">
          <h3 className="text-sm font-semibold text-slate-100">Registered owners</h3>
          <ul className="mt-4 space-y-2 text-sm text-slate-200">
            {sortedOwners.map((owner) => (
              <li
                key={owner.key}
                className="flex items-center justify-between rounded-xl border border-slate-800/60 bg-slate-950/50 px-3 py-2"
              >
                <span>{owner.displayName}</span>
                <span className="font-mono text-xs uppercase tracking-[0.3em] text-slate-500">
                  {owner.key}
                </span>
              </li>
            ))}
            {sortedOwners.length === 0 ? (
              <li className="rounded-xl border border-dashed border-slate-800/60 px-3 py-4 text-sm text-slate-400">
                No owners registered yet.
              </li>
            ) : null}
          </ul>
        </div>

        <div className="rounded-3xl border border-slate-800/60 bg-slate-900/60 p-6">
          <h3 className="text-sm font-semibold text-slate-100">Device types</h3>
          <ul className="mt-4 flex flex-wrap gap-2">
            {sortedDeviceTypes.map((type) => (
              <li
                key={type}
                className="rounded-full border border-slate-700/60 bg-slate-950/50 px-3 py-1 text-xs uppercase tracking-[0.25em] text-slate-200"
              >
                {type}
              </li>
            ))}
            {sortedDeviceTypes.length === 0 ? (
              <li className="text-sm text-slate-400">No device types available.</li>
            ) : null}
          </ul>
        </div>
      </section>
    </div>
  );
}
