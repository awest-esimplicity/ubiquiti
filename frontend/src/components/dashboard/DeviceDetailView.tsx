import { useCallback, useEffect, useMemo, useState } from "react";

import { ICONS } from "@/components/icons";
import { Button, buttonVariants } from "@/components/ui/button";
import { lockControllerService } from "@/lib/bootstrap/lockController";
import type { DeviceDetail, DeviceTrafficSample } from "@/lib/domain/models";
import { cn } from "@/lib/utils/cn";
import { formatTimestamp } from "@/lib/utils/date";

interface DeviceDetailViewProps {
  mac?: string;
}

const LOOKBACK_OPTIONS: Array<{ label: string; value: number }> = [
  { label: "Last 30 minutes", value: 30 },
  { label: "Last 60 minutes", value: 60 },
  { label: "Last 3 hours", value: 180 },
  { label: "Last 6 hours", value: 360 },
];

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let remaining = value;
  let unitIndex = 0;
  while (remaining >= 1024 && unitIndex < units.length - 1) {
    remaining /= 1024;
    unitIndex += 1;
  }
  return `${remaining.toFixed(remaining >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function describeSamples(samples: DeviceTrafficSample[]): DeviceTrafficSample[] {
  if (samples.length <= 12) {
    return samples;
  }
  const step = Math.ceil(samples.length / 12);
  return samples.filter((_, index) => index % step === 0);
}

export function DeviceDetailView({ mac }: DeviceDetailViewProps) {
  const [detail, setDetail] = useState<DeviceDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>();
  const [lookback, setLookback] = useState<number>(60);
  const [currentMac, setCurrentMac] = useState<string>(() => mac?.trim() ?? "");

  useEffect(() => {
    if (mac && mac.trim() !== currentMac) {
      setCurrentMac(mac.trim());
    }
  }, [mac, currentMac]);

  useEffect(() => {
    if (currentMac || typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const urlMac = params.get("mac");
    if (urlMac) {
      setCurrentMac(urlMac.trim());
    }
  }, [currentMac]);

  const loadDetail = useCallback(
    (signal?: AbortSignal) => {
      const targetMac = currentMac.trim();
      if (!targetMac) {
        setError("Select a device to view details.");
        setDetail(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(undefined);
      lockControllerService
        .getDeviceDetail(targetMac, lookback)
        .then((response) => {
          if (signal?.aborted) {
            return;
          }
          setDetail(response);
          setLoading(false);
        })
        .catch((err: unknown) => {
          if (signal?.aborted) {
            return;
          }
          const message = err instanceof Error ? err.message : "Unable to load device details.";
          setError(message);
          setDetail(null);
          setLoading(false);
        });
    },
    [currentMac, lookback],
  );

  useEffect(() => {
    const controller = new AbortController();
    loadDetail(controller.signal);
    return () => controller.abort();
  }, [loadDetail, currentMac]);

  const trafficSamples = useMemo<DeviceTrafficSample[]>(() => {
    if (!detail?.traffic?.samples) {
      return [];
    }
    return describeSamples(detail.traffic.samples);
  }, [detail]);

  const lastSeen = detail?.lastSeen ? formatTimestamp(detail.lastSeen) : "Unknown";
  const connectionLabel =
    detail?.connection === "wired"
      ? "Wired"
      : detail?.connection === "wireless"
        ? "Wireless"
        : "Unknown";

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.3em] text-slate-500">
            <span>{detail?.owner ?? "Owner"}</span>
            <span>•</span>
            <span>{detail?.type ?? "Device"}</span>
          </div>
          <h1 className="text-3xl font-semibold text-slate-100">
            {detail?.name ?? (currentMac || "Select a device")}
          </h1>
          <p className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
            {currentMac || "—"}
          </p>
          {detail?.vendor ? (
            <p className="text-sm text-slate-400">Vendor: {detail.vendor}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={lookback}
            onChange={(event) => setLookback(Number.parseInt(event.target.value, 10))}
            className="rounded-lg border border-slate-700/60 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
          >
            {LOOKBACK_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <Button
            variant="ghost"
            onClick={() => loadDetail()}
            disabled={loading}
            className="border border-transparent hover:border-slate-700"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </Button>
          <a
            href="/console"
            className={cn(
              buttonVariants({ variant: "outline", size: "sm" }),
              "border-slate-700 text-slate-200 hover:border-brand-blue/60 hover:text-white",
            )}
          >
            Back to console
          </a>
        </div>
      </header>

      {loading ? (
        <div className="rounded-3xl border border-slate-800/60 bg-slate-950/30 p-8 text-slate-400">
          <p className="text-sm uppercase tracking-[0.3em]">Loading device details…</p>
        </div>
      ) : null}

      {error ? (
        <div className="flex items-start gap-3 rounded-3xl border border-status-locked/40 bg-status-locked/10 p-6 text-status-locked">
          <span>{ICONS.alert}</span>
          <div>
            <h2 className="text-lg font-semibold">Something went wrong</h2>
            <p className="mt-1 text-sm text-status-locked/80">{error}</p>
          </div>
        </div>
      ) : null}

      {!loading && !error && detail ? (
        <div className="space-y-8">
          <section className="rounded-3xl border border-slate-800/50 bg-slate-950/30 p-6 shadow-inner">
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={cn(
                  "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold tracking-wide",
                  detail.locked
                    ? "border-status-locked/40 text-status-locked"
                    : "border-status-unlocked/40 text-status-unlocked",
                )}
              >
                {detail.locked ? ICONS.locked : ICONS.unlocked}
                {detail.locked ? "Locked" : "Unlocked"}
              </span>
              <span className="text-xs uppercase tracking-[0.3em] text-slate-500">
                Last seen: {lastSeen}
              </span>
              <span className="text-xs uppercase tracking-[0.3em] text-slate-500">
                Status: {detail.online ? "Online" : "Offline"}
              </span>
            </div>

            <dl className="mt-6 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              <div className="space-y-2 rounded-2xl border border-slate-800/50 bg-slate-950/40 p-4">
                <dt className="text-xs uppercase tracking-[0.3em] text-slate-500">IP address</dt>
                <dd className="text-sm text-slate-200">{detail.ip ?? "Unavailable"}</dd>
              </div>
              <div className="space-y-2 rounded-2xl border border-slate-800/50 bg-slate-950/40 p-4">
                <dt className="text-xs uppercase tracking-[0.3em] text-slate-500">Connection</dt>
                <dd className="text-sm text-slate-200">
                  {connectionLabel}
                  {detail.accessPoint ? (
                    <span className="ml-2 text-xs text-slate-500">via {detail.accessPoint}</span>
                  ) : null}
                </dd>
              </div>
              <div className="space-y-2 rounded-2xl border border-slate-800/50 bg-slate-950/40 p-4">
                <dt className="text-xs uppercase tracking-[0.3em] text-slate-500">Signal</dt>
                <dd className="text-sm text-slate-200">
                  {typeof detail.signal === "number" ? `${detail.signal} dBm` : "Unavailable"}
                </dd>
              </div>
              <div className="space-y-2 rounded-2xl border border-slate-800/50 bg-slate-950/40 p-4">
                <dt className="text-xs uppercase tracking-[0.3em] text-slate-500">Network name</dt>
                <dd className="text-sm text-slate-200">{detail.networkName ?? "Unknown"}</dd>
              </div>
              <div className="space-y-2 rounded-2xl border border-slate-800/50 bg-slate-950/40 p-4">
                <dt className="text-xs uppercase tracking-[0.3em] text-slate-500">Owner</dt>
                <dd className="text-sm text-slate-200 capitalize">{detail.owner}</dd>
              </div>
              <div className="space-y-2 rounded-2xl border border-slate-800/50 bg-slate-950/40 p-4">
                <dt className="text-xs uppercase tracking-[0.3em] text-slate-500">Vendor</dt>
                <dd className="text-sm text-slate-200">{detail.vendor ?? "Unknown vendor"}</dd>
              </div>
            </dl>
          </section>

          <section className="rounded-3xl border border-slate-800/50 bg-slate-950/30 p-6 shadow-inner">
            <header className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-100">Traffic summary</h2>
                {detail.traffic?.start && detail.traffic?.end ? (
                  <p className="mt-1 text-xs uppercase tracking-[0.3em] text-slate-500">
                    {formatTimestamp(detail.traffic.start)} – {formatTimestamp(detail.traffic.end)}
                  </p>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-3 text-sm text-slate-200">
                <span className="rounded-xl border border-slate-700/60 bg-slate-900/60 px-3 py-1">
                  Downloaded {formatBytes(detail.traffic?.totalRxBytes ?? 0)}
                </span>
                <span className="rounded-xl border border-slate-700/60 bg-slate-900/60 px-3 py-1">
                  Uploaded {formatBytes(detail.traffic?.totalTxBytes ?? 0)}
                </span>
              </div>
            </header>

            {trafficSamples.length > 0 ? (
              <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {trafficSamples.map((sample) => (
                  <div
                    key={sample.timestamp}
                    className="rounded-2xl border border-slate-800/40 bg-gradient-to-br from-slate-950/50 to-slate-900/30 p-4"
                  >
                    <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
                      {formatTimestamp(sample.timestamp)}
                    </p>
                    <div className="mt-2 space-y-1 text-sm text-slate-200">
                      <p>Download • {formatBytes(sample.rxBytes)}</p>
                      <p>Upload • {formatBytes(sample.txBytes)}</p>
                      <p className="text-xs text-slate-500">
                        Total {formatBytes(sample.totalBytes)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-6 rounded-2xl border border-dashed border-slate-800/50 bg-slate-950/20 p-6 text-sm text-slate-400">
                No traffic history was returned for this device in the selected window. Ensure
                historical client data is enabled in the UniFi controller.
              </p>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}
