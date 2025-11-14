import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import type { AuditEvent } from "@/lib/domain/models";
import { EventService } from "@/lib/services/EventService";
import { cn } from "@/lib/utils/cn";
import { formatTimestamp } from "@/lib/utils/date";

const DEFAULT_LIMIT = 200;
const ALL_OPTION = "all";
const eventService = new EventService();

type FilterOption = string;

function buildRelativeTime(iso: string): string {
  const target = new Date(iso);
  const now = new Date();
  const delta = now.getTime() - target.getTime();
  if (Number.isNaN(delta)) {
    return "";
  }
  const seconds = Math.round(delta / 1000);
  if (seconds < 60) {
    return `${seconds}s ago`;
  }
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

export function ControlLog() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [limit, setLimit] = useState(DEFAULT_LIMIT);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [search, setSearch] = useState("");
  const [actionFilter, setActionFilter] = useState<FilterOption>(ALL_OPTION);
  const [subjectFilter, setSubjectFilter] = useState<FilterOption>(ALL_OPTION);
  const [actorFilter, setActorFilter] = useState<FilterOption>(ALL_OPTION);
  const [expandedIds, setExpandedIds] = useState<Set<number | undefined>>(new Set());

  const fetchEvents = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError(undefined);
      try {
        const result = await eventService.listEvents(limit, signal);
        setEvents(result);
      } catch (fetchError) {
        if (!(fetchError instanceof DOMException && fetchError.name === "AbortError")) {
          const message =
            fetchError instanceof Error ? fetchError.message : "Failed to load events.";
          setError(message);
        }
      } finally {
        setLoading(false);
      }
    },
    [limit],
  );

  useEffect(() => {
    const controller = new AbortController();
    void fetchEvents(controller.signal);
    return () => controller.abort();
  }, [fetchEvents]);

  useEffect(() => {
    if (!autoRefresh) {
      return;
    }
    const id = window.setInterval(() => {
      void fetchEvents();
    }, 15_000);
    return () => window.clearInterval(id);
  }, [autoRefresh, fetchEvents]);

  const uniqueActions = useMemo(() => {
    return Array.from(new Set(events.map((event) => event.action))).sort();
  }, [events]);

  const uniqueSubjects = useMemo(() => {
    return Array.from(new Set(events.map((event) => event.subjectType))).sort();
  }, [events]);

  const uniqueActors = useMemo(() => {
    return Array.from(new Set(events.map((event) => event.actor).filter(Boolean))).sort();
  }, [events]);

  const filteredEvents = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return events.filter((event) => {
      if (actionFilter !== ALL_OPTION && event.action !== actionFilter) {
        return false;
      }
      if (subjectFilter !== ALL_OPTION && event.subjectType !== subjectFilter) {
        return false;
      }
      if (actorFilter !== ALL_OPTION && (event.actor ?? "") !== actorFilter) {
        return false;
      }
      if (!needle) {
        return true;
      }
      const target = [
        event.action,
        event.actor ?? "",
        event.subjectType,
        event.subjectId ?? "",
        event.reason ?? "",
        JSON.stringify(event.metadata ?? {}),
      ]
        .join(" ")
        .toLowerCase();
      return target.includes(needle);
    });
  }, [events, actionFilter, subjectFilter, actorFilter, search]);

  const toggleRow = useCallback((id: number | undefined) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const mostRecent = filteredEvents[0]?.timestamp;

  return (
    <div className="space-y-8">
      <header className="rounded-3xl border border-slate-700/50 bg-slate-900/40 p-6 shadow-card">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Control history</p>
            <h1 className="mt-1 text-3xl font-semibold text-slate-100">Control log</h1>
            <p className="mt-2 text-sm text-slate-400">
              View the lock/unlock actions, owner changes, schedule updates, and other enforcement
              activities. Provide `X-Actor`/`X-Reason` headers or payload fields when calling the API
              to annotate entries.
            </p>
            {mostRecent ? (
              <p className="mt-2 text-xs uppercase tracking-[0.3em] text-slate-500">
                Latest entry • {formatTimestamp(mostRecent)} ({buildRelativeTime(mostRecent)})
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
                Auto refresh
              </label>
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(event) => setAutoRefresh(event.target.checked)}
                className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-brand-blue focus:ring-brand-blue"
              />
            </div>
            <select
              value={limit}
              onChange={(event) => setLimit(Number.parseInt(event.target.value, 10))}
              className="rounded-lg border border-slate-700/50 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
            >
              {[100, 200, 300, 500].map((value) => (
                <option key={value} value={value}>
                  Last {value}
                </option>
              ))}
            </select>
            <Button
              variant="ghost"
              onClick={() => void fetchEvents()}
              disabled={loading}
              className="border border-transparent hover:border-slate-700"
            >
              {loading ? "Refreshing…" : "Refresh"}
            </Button>
          </div>
        </div>
        {error ? (
          <p className="mt-4 rounded-2xl border border-status-locked/40 bg-status-locked/10 p-4 text-sm text-status-locked">
            {error}
          </p>
        ) : null}
      </header>

      <section className="rounded-3xl border border-slate-700/40 bg-slate-900/40 p-6 shadow-card">
        <div className="grid gap-4 lg:grid-cols-4">
          <div className="flex flex-col gap-2">
            <label className="text-xs uppercase tracking-[0.3em] text-slate-400">Action</label>
            <select
              value={actionFilter}
              onChange={(event) => setActionFilter(event.target.value)}
              className="rounded-lg border border-slate-700/50 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
            >
              <option value={ALL_OPTION}>All actions</option>
              {uniqueActions.map((action) => (
                <option key={action} value={action}>
                  {action}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-2">
            <label className="text-xs uppercase tracking-[0.3em] text-slate-400">Subject</label>
            <select
              value={subjectFilter}
              onChange={(event) => setSubjectFilter(event.target.value)}
              className="rounded-lg border border-slate-700/50 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
            >
              <option value={ALL_OPTION}>All subjects</option>
              {uniqueSubjects.map((subject) => (
                <option key={subject} value={subject}>
                  {subject}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-2">
            <label className="text-xs uppercase tracking-[0.3em] text-slate-400">Actor</label>
            <select
              value={actorFilter}
              onChange={(event) => setActorFilter(event.target.value)}
              className="rounded-lg border border-slate-700/50 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
            >
              <option value={ALL_OPTION}>All actors</option>
              {uniqueActors.map((actor) => (
                <option key={actor} value={actor}>
                  {actor}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-2">
            <label className="text-xs uppercase tracking-[0.3em] text-slate-400">Search</label>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search actor, subject, reason…"
              className="rounded-lg border border-slate-700/50 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
            />
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-3xl border border-slate-700/40 bg-slate-900/40 shadow-card">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-800/60 text-sm text-slate-200">
            <thead className="bg-slate-950/50 text-xs uppercase tracking-[0.3em] text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left">Timestamp</th>
                <th className="px-4 py-3 text-left">Action</th>
                <th className="px-4 py-3 text-left">Subject</th>
                <th className="px-4 py-3 text-left">Actor</th>
                <th className="px-4 py-3 text-left">Reason</th>
                <th className="px-4 py-3 text-left">Metadata</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 bg-slate-950/30">
              {filteredEvents.map((event) => {
                const rowId = event.id;
                const isExpanded = expandedIds.has(rowId);
                return (
                  <tr
                    key={`${event.timestamp}-${event.action}-${event.subjectId ?? "none"}-${rowId ?? "na"}`}
                    className={cn("transition hover:bg-slate-900/60", {
                      "bg-slate-900/50": isExpanded,
                    })}
                    onClick={() => toggleRow(rowId)}
                  >
                    <td className="whitespace-nowrap px-4 py-3 align-top">
                      <div className="font-medium text-slate-100">
                        {formatTimestamp(event.timestamp)}
                      </div>
                      <div className="text-xs text-slate-500">{buildRelativeTime(event.timestamp)}</div>
                    </td>
                    <td className="px-4 py-3 align-top">
                      <span className="inline-flex items-center rounded-full border border-brand-blue/40 bg-brand-blue/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] text-brand-blue">
                        {event.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-top">
                      <div className="font-medium capitalize text-slate-200">{event.subjectType}</div>
                      {event.subjectId ? (
                        <div className="text-xs text-slate-500">{event.subjectId}</div>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 align-top text-slate-200">{event.actor ?? "system"}</td>
                    <td className="px-4 py-3 align-top text-slate-200">
                      {event.reason ? (
                        <span className="rounded-full border border-slate-700/50 bg-slate-900/60 px-3 py-1 text-xs text-slate-300">
                          {event.reason}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-500">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 align-top text-slate-200">
                      <div className="flex flex-wrap gap-2 text-xs text-slate-300">
                        {Object.entries(event.metadata ?? {}).slice(0, 3).map(([key, value]) => (
                          <span
                            key={key}
                            className="rounded-full border border-slate-700/40 bg-slate-900/60 px-3 py-1"
                          >
                            {key}: {String(value)}
                          </span>
                        ))}
                        {Object.keys(event.metadata ?? {}).length === 0 ? (
                          <span className="text-slate-500">—</span>
                        ) : null}
                      </div>
                      {isExpanded ? (
                        <pre className="mt-3 overflow-x-auto rounded-lg border border-slate-800/50 bg-slate-950/60 p-3 text-xs text-slate-300">
                          {JSON.stringify(event.metadata ?? {}, null, 2)}
                        </pre>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
              {filteredEvents.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-400">
                    No events match the current filters.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
