import { useCallback, useEffect, useMemo, useState } from "react";

import { OwnerCard } from "@/components/dashboard/OwnerCard";
import { ICONS } from "@/components/icons";
import { PinModal } from "@/components/modals/PinModal";
import { Button } from "@/components/ui/button";
import { lockControllerService } from "@/lib/bootstrap/lockController";
import { MASTER_OWNER, MASTER_PIN } from "@/lib/domain/constants";
import type { DashboardSnapshot, OwnerSummary } from "@/lib/domain/models";

interface HomeDashboardState {
  snapshot: DashboardSnapshot | null;
  loading: boolean;
  error?: string;
  refreshing: boolean;
  pinOwner?: OwnerSummary;
  pinValue: string;
  pinError?: string;
  pinDestination?: "owner" | "console";
}

export function HomeDashboard() {
  const [state, setState] = useState<HomeDashboardState>({
    snapshot: null,
    loading: true,
    refreshing: false,
    pinValue: ""
  });

  useEffect(() => {
    lockControllerService
      .loadSnapshot()
      .then((snapshot) => {
        setState((prev) => ({ ...prev, snapshot, loading: false }));
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : "Failed to load dashboard";
        setState((prev) => ({ ...prev, loading: false, error: message }));
      });
  }, []);

  useEffect(() => {
    if (!state.snapshot || typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const authOwnerKey = params.get("auth_owner");
    if (!authOwnerKey) {
      return;
    }
    const targetOwner = state.snapshot.owners.find((owner) => owner.key === authOwnerKey);
    if (targetOwner) {
      setState((prev) => ({
        ...prev,
        pinOwner: prev.pinOwner?.key === targetOwner.key ? prev.pinOwner : targetOwner,
        pinValue: "",
        pinError: undefined,
        pinDestination: "owner"
      }));
    }
  }, [state.snapshot]);

  const handleRefresh = useCallback(() => {
    setState((prev) => ({ ...prev, refreshing: true }));
    lockControllerService
      .refresh()
      .then((snapshot) => setState((prev) => ({ ...prev, snapshot, refreshing: false })))
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : "Failed to refresh data";
        setState((prev) => ({ ...prev, error: message, refreshing: false }));
      });
  }, []);

  const handleSelectOwner = useCallback((owner: OwnerSummary) => {
    setState((prev) => ({
      ...prev,
      pinOwner: owner,
      pinValue: "",
      pinError: undefined,
      pinDestination: "owner"
    }));
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      params.set("auth_owner", owner.key);
      window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
    }
  }, []);

  const handleOpenConsole = useCallback(() => {
    setState((prev) => ({
      ...prev,
      pinOwner: MASTER_OWNER,
      pinValue: "",
      pinError: undefined,
      pinDestination: "console"
    }));
  }, []);

  const handlePinDigit = useCallback((digit: string) => {
    setState((prev) => ({
      ...prev,
      pinValue: prev.pinValue.length >= 4 ? prev.pinValue : prev.pinValue + digit,
      pinError: undefined
    }));
  }, []);

  const handlePinBackspace = useCallback(() => {
    setState((prev) => ({
      ...prev,
      pinValue: prev.pinValue.slice(0, -1),
      pinError: undefined
    }));
  }, []);

  const handlePinClear = useCallback(() => {
    setState((prev) => ({
      ...prev,
      pinValue: "",
      pinError: undefined
    }));
  }, []);

  const handlePinCancel = useCallback(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      params.delete("auth_owner");
      window.history.replaceState(
        null,
        "",
        params.toString() ? `${window.location.pathname}?${params.toString()}` : window.location.pathname
      );
    }
    setState((prev) => ({
      ...prev,
      pinOwner: undefined,
      pinValue: "",
      pinError: undefined,
      pinDestination: undefined
    }));
  }, []);

  const pinOwner = state.pinOwner;
  const pinValue = state.pinValue;
  const pinDestination = state.pinDestination;

  const handlePinSubmit = useCallback(async () => {
    if (!pinOwner) {
      return;
    }

    setState((prev) => ({ ...prev, pinError: undefined }));

    const completeNavigation = () => {
      if (typeof window !== "undefined") {
        const params = new URLSearchParams(window.location.search);
        params.delete("auth_owner");
        if (pinDestination === "console" || pinOwner.key === MASTER_OWNER.key) {
          window.sessionStorage.setItem("unifi-master-console", "true");
          window.location.href = "/console";
        } else {
          window.location.href = `/owner/${pinOwner.key}`;
        }
      }
      setState((prev) => ({
        ...prev,
        pinOwner: undefined,
        pinValue: "",
        pinError: undefined,
        pinDestination: undefined
      }));
    };

    if (pinValue === MASTER_PIN) {
      completeNavigation();
      return;
    }

    if (pinOwner.pin && pinValue === pinOwner.pin) {
      completeNavigation();
      return;
    }

    try {
      const valid = await lockControllerService.verifyOwnerPin(pinOwner.key, pinValue);
      if (valid) {
        completeNavigation();
        return;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to verify PIN. Please try again.";
      setState((prev) => ({
        ...prev,
        pinError: message,
        pinValue: ""
      }));
      return;
    }

    setState((prev) => ({
      ...prev,
      pinError: "Invalid PIN. Please try again.",
      pinValue: ""
    }));
  }, [pinDestination, pinOwner, pinValue]);

  const handlePinSubmitSafe = useCallback(() => {
    void handlePinSubmit();
  }, [handlePinSubmit]);

  const owners = useMemo(() => state.snapshot?.owners ?? [], [state.snapshot]);

  if (state.loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-300">
        <span className="inline-flex items-center gap-3 text-sm uppercase tracking-[0.4em]">
          <span className="h-2 w-2 animate-ping rounded-full bg-brand-blue" />
          Loading dashboard
        </span>
      </div>
    );
  }

  if (state.error) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="rounded-2xl border border-status-locked/40 bg-status-locked/10 px-6 py-5 text-status-locked">
          <h2 className="text-lg font-semibold">Something went wrong</h2>
          <p className="mt-2 text-sm">{state.error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-10 pb-16">
      <div className="flex justify-end">
        <Button
          variant="outline"
          onClick={handleOpenConsole}
          className="gap-2 border-slate-600/60 bg-slate-900/50 text-slate-100 hover:border-brand-blue/60 hover:bg-slate-900/70"
        >
          {ICONS.devices}
          <span>Open full console</span>
        </Button>
      </div>

      <section>
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-slate-100">Owners</h2>
          <Button variant="ghost" size="icon" onClick={handleRefresh} aria-label="Refresh owners">
            {ICONS.refresh}
          </Button>
        </div>
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4 auto-rows-fr">
          {owners.map((owner) => (
            <OwnerCard key={owner.key} owner={owner} onSelect={handleSelectOwner} />
          ))}
        </div>
      </section>

      {state.pinOwner ? (
        <PinModal
          owner={state.pinOwner}
          pinValue={state.pinValue}
          error={state.pinError}
          onDigit={handlePinDigit}
          onBackspace={handlePinBackspace}
          onClear={handlePinClear}
          onCancel={handlePinCancel}
          onSubmit={handlePinSubmitSafe}
        />
      ) : null}
    </div>
  );
}
