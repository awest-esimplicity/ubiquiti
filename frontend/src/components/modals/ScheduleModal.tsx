import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import type { OwnerInfo } from "@/lib/api/types";
import { adminService } from "@/lib/bootstrap/admin";
import { scheduleService } from "@/lib/bootstrap/lockController";
import type {
  DeviceSchedule,
  ScheduleAction,
  ScheduleConfig,
  ScheduleGroup,
  ScheduleRecurrence,
  ScheduleRecurrenceType
} from "@/lib/domain/schedules";
import { formatTimestamp } from "@/lib/utils/date";

interface ScheduleModalProps {
  ownerKey: string;
  ownerName: string;
  onClose: () => void;
}

interface ModalState {
  loading: boolean;
  ownerSchedules: DeviceSchedule[];
  globalSchedules: DeviceSchedule[];
  metadata?: ScheduleConfig["metadata"];
  error?: string;
}

interface EventFormState {
  label: string;
  description: string;
  start: string;
  end: string;
  startAction: ScheduleAction;
  endAction: ScheduleAction;
  recurrenceType: ScheduleRecurrenceType;
  interval: string;
  daysOfWeek: string[];
  dayOfMonth: string;
  until: string;
}

const INITIAL_FORM: EventFormState = {
  label: "",
  description: "",
  start: "",
  end: "",
  startAction: "lock",
  endAction: "unlock",
  recurrenceType: "one_shot",
  interval: "1",
  daysOfWeek: [],
  dayOfMonth: "",
  until: ""
};

const WEEK_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;
type ChangeHandler = (
  field: keyof EventFormState
) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => void;

interface CopyState {
  mode: "single" | "bulk";
  schedule?: DeviceSchedule;
  targetOwner: string;
  replace: boolean;
}

type GroupScope = "owner" | "global";

interface GroupState {
  loading: boolean;
  ownerGroups: ScheduleGroup[];
  globalGroups: ScheduleGroup[];
  error?: string;
}

interface GroupDialogState {
  mode: "create" | "edit";
  scope: GroupScope;
  group?: ScheduleGroup;
}

interface GroupFormValues {
  name: string;
  description: string;
  scheduleIds: string[];
  activeScheduleId?: string;
}

export function ScheduleModal({ ownerKey, ownerName, onClose }: ScheduleModalProps) {
  const [state, setState] = useState<ModalState>({
    loading: true,
    ownerSchedules: [],
    globalSchedules: []
  });
  const [form, setForm] = useState<EventFormState>(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string>();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [ownerOptions, setOwnerOptions] = useState<OwnerInfo[]>([]);
  const [ownersLoading, setOwnersLoading] = useState(false);
  const [ownerLoadError, setOwnerLoadError] = useState<string>();
  const [copyState, setCopyState] = useState<CopyState | null>(null);
  const [copying, setCopying] = useState(false);
  const [copyError, setCopyError] = useState<string>();
  const [groupState, setGroupState] = useState<GroupState>({
    loading: true,
    ownerGroups: [],
    globalGroups: []
  });
  const [groupDialog, setGroupDialog] = useState<GroupDialogState | null>(null);
  const [groupSubmitting, setGroupSubmitting] = useState(false);
  const [groupDialogError, setGroupDialogError] = useState<string>();
  const [deletingGroupIds, setDeletingGroupIds] = useState<Set<string>>(new Set());
  const [activatingGroupKey, setActivatingGroupKey] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const result = await scheduleService.getSchedulesForOwner(ownerKey);
        if (!cancelled) {
          setState({
            loading: false,
            ownerSchedules: result.ownerSchedules,
            globalSchedules: result.globalSchedules,
            metadata: result.metadata
          });
        }
      } catch (error) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Failed to load schedules.";
          setState({
            loading: false,
            ownerSchedules: [],
            globalSchedules: [],
            metadata: undefined,
            error: message
          });
        }
      }
    };

    setState((prev) => ({ ...prev, loading: true, error: undefined }));
    setForm(INITIAL_FORM);
    void load();

    return () => {
      cancelled = true;
    };
  }, [ownerKey]);

  useEffect(() => {
    let cancelled = false;
    setOwnersLoading(true);
    adminService
      .listOwners()
      .then((owners) => {
        if (!cancelled) {
          setOwnerOptions(owners);
          setOwnerLoadError(undefined);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Failed to load owners.";
          setOwnerLoadError(message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setOwnersLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setGroupState((prev) => ({
      ...prev,
      loading: true,
      error: undefined
    }));

    scheduleService
      .getScheduleGroups(ownerKey)
      .then((result) => {
        if (!cancelled) {
          setGroupState({
            loading: false,
            ownerGroups: result.ownerGroups,
            globalGroups: result.globalGroups
          });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : "Failed to load schedule groups.";
          setGroupState({
            loading: false,
            ownerGroups: [],
            globalGroups: [],
            error: message
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [ownerKey]);

  const timezone = state.metadata?.timezone ?? "UTC";

  const sortedOwnerSchedules = useMemo(
    () =>
      [...state.ownerSchedules].sort(
        (a, b) => new Date(a.window.start).getTime() - new Date(b.window.start).getTime()
      ),
    [state.ownerSchedules]
  );

  const sortedGlobalSchedules = useMemo(
    () =>
      [...state.globalSchedules].sort(
        (a, b) => new Date(a.window.start).getTime() - new Date(b.window.start).getTime()
      ),
    [state.globalSchedules]
  );

  const timelineEvents = useMemo(() => {
    const entries: TimelineEntry[] = [
      ...sortedOwnerSchedules.map((schedule) => ({ schedule, scope: "owner" as const })),
      ...sortedGlobalSchedules.map((schedule) => ({ schedule, scope: "global" as const }))
    ];
    return entries
      .sort((a, b) => new Date(a.schedule.window.start).getTime() - new Date(b.schedule.window.start).getTime())
      .slice(0, 12);
  }, [sortedOwnerSchedules, sortedGlobalSchedules]);

  const availableOwners = useMemo(
    () => ownerOptions.filter((owner) => owner.key !== ownerKey),
    [ownerOptions, ownerKey]
  );

  const handleChange: ChangeHandler = (field) => (event) => {
    setForm((prev) => ({
      ...prev,
      [field]: event.target.value
    }));
  };

  const toggleDay = (day: string) => {
    setForm((prev) => {
      const exists = prev.daysOfWeek.includes(day);
      return {
        ...prev,
        daysOfWeek: exists ? prev.daysOfWeek.filter((value) => value !== day) : [...prev.daysOfWeek, day]
      };
    });
  };

  const handleCopySchedule = (schedule: DeviceSchedule) => {
    if (availableOwners.length === 0) {
      return;
    }
    setCopyError(undefined);
    setCopyState({
      mode: "single",
      schedule,
      targetOwner: availableOwners[0]?.key ?? "",
      replace: false
    });
  };

  const handleOpenBulkCopy = () => {
    if (availableOwners.length === 0) {
      return;
    }
    setCopyError(undefined);
    setCopyState({
      mode: "bulk",
      targetOwner: availableOwners[0]?.key ?? "",
      replace: false
    });
  };

  const handleCloseCopyDialog = () => {
    setCopyState(null);
    setCopyError(undefined);
  };

  const handleCopyTargetChange = (value: string) => {
    setCopyError(undefined);
    setCopyState((prev) => (prev ? { ...prev, targetOwner: value } : prev));
  };

  const handleCopyReplaceToggle = (value: boolean) => {
    setCopyError(undefined);
    setCopyState((prev) => (prev ? { ...prev, replace: value } : prev));
  };

  const getSchedulesForScope = useCallback(
    (scope: GroupScope) => (scope === "owner" ? sortedOwnerSchedules : sortedGlobalSchedules),
    [sortedOwnerSchedules, sortedGlobalSchedules]
  );

  const handleOpenCreateGroup = (scope: GroupScope) => {
    if (getSchedulesForScope(scope).length === 0) {
      setGroupDialogError("Create a schedule before building a group.");
      return;
    }
    setGroupDialogError(undefined);
    setGroupDialog({
      mode: "create",
      scope
    });
  };

  const handleOpenEditGroup = (group: ScheduleGroup, scope: GroupScope) => {
    setGroupDialogError(undefined);
    setGroupDialog({
      mode: "edit",
      scope,
      group
    });
  };

  const handleCloseGroupDialog = () => {
    setGroupDialog(null);
    setGroupDialogError(undefined);
  };

  const handleSubmitGroup = async (values: GroupFormValues) => {
    if (!groupDialog) {
      return;
    }
    if (values.scheduleIds.length === 0) {
      setGroupDialogError("Select at least one schedule.");
      return;
    }
    const trimmedName = values.name.trim();
    if (!trimmedName) {
      setGroupDialogError("Group name is required.");
      return;
    }

    const scope = groupDialog.scope;
    const description = values.description.trim();
    const scheduleIds = values.scheduleIds;
    const activeScheduleId = scheduleIds.includes(values.activeScheduleId ?? "")
      ? values.activeScheduleId
      : scheduleIds[0];

    setGroupSubmitting(true);
    setGroupDialogError(undefined);

    try {
      if (groupDialog.mode === "create") {
        const created = await scheduleService.createGroup({
          name: trimmedName,
          description: description || undefined,
          scheduleIds,
          activeScheduleId,
          ownerKey: scope === "owner" ? ownerKey : undefined
        });
        setGroupState((prev) => ({
          ...prev,
          error: undefined,
          ownerGroups:
            scope === "owner" ? [...prev.ownerGroups, created] : prev.ownerGroups,
          globalGroups:
            scope === "global" ? [...prev.globalGroups, created] : prev.globalGroups
        }));
      } else if (groupDialog.group) {
        const updated = await scheduleService.updateGroup({
          groupId: groupDialog.group.id,
          name: trimmedName,
          description: description || undefined,
          scheduleIds,
          activeScheduleId
        });
        setGroupState((prev) => ({
          ...prev,
          error: undefined,
          ownerGroups:
            scope === "owner"
              ? prev.ownerGroups.map((group) => (group.id === updated.id ? updated : group))
              : prev.ownerGroups,
          globalGroups:
            scope === "global"
              ? prev.globalGroups.map((group) => (group.id === updated.id ? updated : group))
              : prev.globalGroups
        }));
      }
      setGroupDialog(null);
      setGroupDialogError(undefined);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save group.";
      setGroupDialogError(message);
    } finally {
      setGroupSubmitting(false);
    }
  };

  const handleDeleteGroup = async (group: ScheduleGroup, scope: GroupScope) => {
    const confirmDelete =
      typeof window !== "undefined"
        ? window.confirm(`Delete “${group.name}”? This will not remove schedules.`)
        : true;
    if (!confirmDelete) {
      return;
    }

    setDeletingGroupIds((prev) => {
      const next = new Set(prev);
      next.add(group.id);
      return next;
    });

    try {
      await scheduleService.deleteGroup(group.id);
      setGroupState((prev) => ({
        ...prev,
        error: undefined,
        ownerGroups:
          scope === "owner"
            ? prev.ownerGroups.filter((entry) => entry.id !== group.id)
            : prev.ownerGroups,
        globalGroups:
          scope === "global"
            ? prev.globalGroups.filter((entry) => entry.id !== group.id)
            : prev.globalGroups
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete group.";
      setGroupState((prev) => ({
        ...prev,
        error: message
      }));
    } finally {
      setDeletingGroupIds((prev) => {
        const next = new Set(prev);
        next.delete(group.id);
        return next;
      });
    }
  };

  const handleActivateSchedule = async (
    group: ScheduleGroup,
    scope: GroupScope,
    scheduleId: string
  ) => {
    setActivatingGroupKey(`${group.id}:${scheduleId}`);
    try {
      const updated = await scheduleService.activateGroup(group.id, scheduleId);
      setGroupState((prev) => ({
        ...prev,
        error: undefined,
        ownerGroups:
          scope === "owner"
            ? prev.ownerGroups.map((entry) => (entry.id === updated.id ? updated : entry))
            : prev.ownerGroups,
        globalGroups:
          scope === "global"
            ? prev.globalGroups.map((entry) => (entry.id === updated.id ? updated : entry))
            : prev.globalGroups
      }));
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to activate schedule in group.";
      setGroupState((prev) => ({
        ...prev,
        error: message
      }));
    } finally {
      setActivatingGroupKey(null);
    }
  };

  const handleConfirmCopy = async () => {
    if (!copyState) {
      return;
    }
    if (!copyState.targetOwner) {
      setCopyError("Select a target owner.");
      return;
    }
    setCopying(true);
    setCopyError(undefined);
    try {
      if (copyState.mode === "single" && copyState.schedule) {
        const cloned = await scheduleService.cloneSchedule(copyState.schedule.id, copyState.targetOwner);
        if (copyState.targetOwner === ownerKey) {
          setState((prev) => ({
            ...prev,
            ownerSchedules: [...prev.ownerSchedules, cloned]
          }));
        }
      } else if (copyState.mode === "bulk") {
        const response = await scheduleService.copyOwnerSchedules(
          ownerKey,
          copyState.targetOwner,
          copyState.replace ? "replace" : "merge"
        );
        if (copyState.targetOwner === ownerKey) {
          setState((prev) => ({
            ...prev,
            ownerSchedules: copyState.replace
              ? response.created
              : [...prev.ownerSchedules, ...response.created]
          }));
        }
      }
      setCopyState(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to copy schedules.";
      setCopyError(message);
    } finally {
      setCopying(false);
    }
  };

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(undefined);

    if (!form.start || !form.end) {
      setFormError("Start and end times are required.");
      return;
    }

    const startDate = new Date(form.start);
    const endDate = new Date(form.end);
    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
      setFormError("Invalid start or end date.");
      return;
    }
    if (startDate >= endDate) {
      setFormError("End time must be after the start time.");
      return;
    }

    const intervalValue = Math.max(1, Number.parseInt(form.interval, 10) || 1);
    const untilISO =
      form.until && !Number.isNaN(new Date(form.until).getTime())
        ? new Date(form.until).toISOString()
        : null;

    const recurrence = buildRecurrence({
      type: form.recurrenceType,
      startDate,
      interval: intervalValue,
      daysOfWeek: form.daysOfWeek,
      dayOfMonth: form.dayOfMonth,
      until: untilISO
    });

    setSubmitting(true);
    scheduleService
      .createEventForOwner(ownerKey, {
        label: form.label || `${ownerName} schedule`,
        description: form.description,
        start: startDate.toISOString(),
        end: endDate.toISOString(),
        startAction: form.startAction,
        endAction: form.endAction,
        recurrence
      })
      .then((newSchedule) => {
        setState((prev) => ({
          ...prev,
          ownerSchedules: [...prev.ownerSchedules, newSchedule]
        }));
        setForm(INITIAL_FORM);
        setIsFormOpen(false);
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : "Failed to create schedule.";
        setFormError(message);
      })
      .finally(() => {
        setSubmitting(false);
      });
  };

  const handleDeleteSchedule = (schedule: DeviceSchedule, scope: "owner" | "global") => {
    setDeletingIds((prev) => {
      const next = new Set(prev);
      next.add(schedule.id);
      return next;
    });

    scheduleService
      .deleteSchedule(schedule.id)
      .then(() => {
        setState((prev) => {
          const nextOwner = scope === "owner" ? prev.ownerSchedules.filter((s) => s.id !== schedule.id) : prev.ownerSchedules;
          const nextGlobal = scope === "global" ? prev.globalSchedules.filter((s) => s.id !== schedule.id) : prev.globalSchedules;
          return {
            ...prev,
            ownerSchedules: nextOwner,
            globalSchedules: nextGlobal
          };
        });
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : "Failed to delete schedule.";
        setState((prev) => ({
          ...prev,
          error: message
        }));
      })
      .finally(() => {
        setDeletingIds((prev) => {
          const next = new Set(prev);
          next.delete(schedule.id);
          return next;
        });
      });
  };

  return (
    <div className="fixed inset-0 z-[1300] flex items-center justify-center bg-slate-950/70 px-4 backdrop-blur-md">
      <div className="relative h-[90vh] w-full max-w-4xl overflow-hidden rounded-3xl border border-slate-700/40 bg-slate-900/95 shadow-[0_35px_90px_rgba(10,12,34,0.65)]">
        <header className="flex items-center justify-between border-b border-slate-700/40 px-6 py-4">
          <div>
            <h2 className="text-xl font-semibold text-slate-50">Schedule for {ownerName}</h2>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Timezone · {timezone}</p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={handleOpenBulkCopy}
              disabled={ownersLoading || availableOwners.length === 0 || copying}
            >
              Copy owner schedules
            </Button>
            <Button
              variant={isFormOpen ? "secondary" : "primary"}
              onClick={() => {
                setIsFormOpen((prev) => !prev);
                setFormError(undefined);
                if (!isFormOpen) {
                  setForm((prev) => ({
                    ...INITIAL_FORM,
                    start: prev.start,
                    end: prev.end
                  }));
                }
              }}
            >
              {isFormOpen ? "Cancel new event" : "New event"}
            </Button>
            <Button variant="ghost" onClick={onClose} className="text-slate-300 hover:text-slate-100">
              Close
            </Button>
          </div>
        </header>

        <div className="flex h-full flex-col overflow-hidden">
          <section className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
            {state.loading ? (
              <div className="flex h-full items-center justify-center text-slate-400">
                <span>Loading schedules…</span>
              </div>
            ) : (
              <>
                {state.error ? (
                  <div className="rounded-2xl border border-status-locked/40 bg-status-locked/10 p-4 text-sm text-status-locked">
                    {state.error}
                  </div>
                ) : null}
                {ownerLoadError ? (
                  <div className="rounded-2xl border border-status-locked/40 bg-status-locked/10 p-3 text-xs text-status-locked">
                    {ownerLoadError}
                  </div>
                ) : null}

                {isFormOpen ? (
                  <EventForm
                    form={form}
                    submitting={submitting}
                    error={formError}
                    timezone={timezone}
                    onChange={handleChange}
                    onToggleDay={toggleDay}
                    onSubmit={handleSubmit}
                  />
                ) : null}

                <ScheduleGroupSection
                  ownerName={ownerName}
                  state={groupState}
                  ownerSchedules={sortedOwnerSchedules}
                  globalSchedules={sortedGlobalSchedules}
                  onCreateGroup={handleOpenCreateGroup}
                  onEditGroup={handleOpenEditGroup}
                  onDeleteGroup={handleDeleteGroup}
                  onActivateSchedule={handleActivateSchedule}
                  deletingGroupIds={deletingGroupIds}
                  activatingKey={activatingGroupKey}
                  inlineError={!groupDialog ? groupDialogError : undefined}
                />

                <EventTimeline ownerName={ownerName} timeline={timelineEvents} />
                <div className="grid gap-4 lg:grid-cols-2">
                  <EventList
                    title={`${ownerName} schedules`}
                    schedules={sortedOwnerSchedules}
                    emptyMessage="No schedules yet for this owner."
                    onDelete={(schedule) => handleDeleteSchedule(schedule, "owner")}
                    deletingIds={deletingIds}
                    onCopy={availableOwners.length === 0 ? undefined : handleCopySchedule}
                    showCopyButton
                    copyDisabled={copying || ownersLoading || availableOwners.length === 0}
                  />
                  <EventList
                    title="Global schedules"
                    schedules={sortedGlobalSchedules}
                    emptyMessage="No global schedules."
                    onDelete={(schedule) => handleDeleteSchedule(schedule, "global")}
                    deletingIds={deletingIds}
                  />
                </div>
              </>
            )}
          </section>
        </div>
        {copyState ? (
          <CopyScheduleDialog
            owners={availableOwners}
            ownerName={ownerName}
            state={copyState}
            onTargetChange={handleCopyTargetChange}
            onToggleReplace={handleCopyReplaceToggle}
            onCancel={handleCloseCopyDialog}
            onConfirm={() => void handleConfirmCopy()}
            copying={copying}
            error={copyError}
          />
        ) : null}
        {groupDialog ? (
          <GroupEditorDialog
            ownerName={ownerName}
            state={groupDialog}
            availableSchedules={getSchedulesForScope(groupDialog.scope)}
            onClose={handleCloseGroupDialog}
            onSubmit={(values) => void handleSubmitGroup(values)}
            submitting={groupSubmitting}
            error={groupDialogError}
          />
        ) : null}
      </div>
    </div>
  );
}

interface CopyScheduleDialogProps {
  owners: OwnerInfo[];
  ownerName: string;
  state: CopyState;
  onTargetChange: (value: string) => void;
  onToggleReplace: (value: boolean) => void;
  onCancel: () => void;
  onConfirm: () => void;
  copying: boolean;
  error?: string;
}

function CopyScheduleDialog({
  owners,
  ownerName,
  state,
  onTargetChange,
  onToggleReplace,
  onCancel,
  onConfirm,
  copying,
  error
}: CopyScheduleDialogProps) {
  const disableConfirm = owners.length === 0 || (!state.targetOwner && owners.length > 0) || copying;
  const title = state.mode === "single" ? "Copy schedule" : "Copy owner schedules";
  const subtitle =
    state.mode === "single"
      ? `Duplicate “${state.schedule?.label ?? "Schedule"}” to another owner`
      : `Copy all schedules from ${ownerName} to another owner`;

  return (
    <div className="absolute inset-0 z-[1400] flex items-center justify-center bg-slate-950/85 px-4">
      <div className="w-full max-w-lg rounded-3xl border border-slate-700/60 bg-slate-900/95 p-6 shadow-[0_40px_80px_rgba(5,7,17,0.6)]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold text-slate-50">{title}</h3>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">{subtitle}</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onCancel} disabled={copying}>
            ✕
          </Button>
        </div>

        <div className="mt-4 space-y-4">
          <label className="block text-xs uppercase tracking-[0.3em] text-slate-500">
            Target owner
            <select
              className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
              value={state.targetOwner}
              onChange={(event) => onTargetChange(event.target.value)}
              disabled={copying || owners.length === 0}
            >
              {owners.length === 0 ? (
                <option value="">No other owners available</option>
              ) : (
                owners.map((owner) => (
                  <option key={owner.key} value={owner.key}>
                    {owner.displayName}
                  </option>
                ))
              )}
            </select>
          </label>

          {state.mode === "single" && state.schedule ? (
            <div className="rounded-2xl border border-slate-700/50 bg-slate-900/60 p-4 text-sm text-slate-300">
              <p className="text-slate-100">Schedule</p>
              <p className="mt-1 font-semibold text-slate-50">{state.schedule.label}</p>
              {state.schedule.description ? (
                <p className="mt-1 text-xs text-slate-400">{state.schedule.description}</p>
              ) : null}
            </div>
          ) : null}

          {state.mode === "bulk" ? (
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                className="rounded border border-slate-600 bg-slate-900 text-brand-blue focus:ring-brand-blue"
                checked={state.replace}
                onChange={(event) => onToggleReplace(event.target.checked)}
                disabled={copying}
              />
              Replace existing schedules for the target owner
            </label>
          ) : null}

          {error ? <p className="text-sm text-status-locked">{error}</p> : null}
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <Button variant="ghost" onClick={onCancel} disabled={copying}>
            Cancel
          </Button>
          <Button onClick={() => void onConfirm()} disabled={disableConfirm}>
            {copying
              ? "Copying…"
              : state.mode === "single"
                ? "Copy schedule"
                : state.replace
                  ? "Copy & replace"
                  : "Copy schedules"}
          </Button>
        </div>
      </div>
    </div>
  );
}

type TimelineEntry = {
  schedule: DeviceSchedule;
  scope: "owner" | "global";
};

interface EventTimelineProps {
  ownerName: string;
  timeline: TimelineEntry[];
}

function EventTimeline({ ownerName, timeline }: EventTimelineProps) {
  if (timeline.length === 0) {
    return (
      <div className="rounded-3xl border border-slate-700/40 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
        No upcoming schedules yet.
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-slate-700/40 bg-gradient-to-br from-slate-900/80 via-slate-900/60 to-slate-900/80 p-6 shadow-inner">
      <h3 className="text-sm uppercase tracking-[0.4em] text-slate-400">Upcoming schedules</h3>
      <div className="relative mt-5 pl-6">
        <div className="absolute left-[10px] top-0 h-full w-px bg-slate-700/60" />
        <div className="space-y-4">
          {timeline.map((entry) => (
            <TimelineCard key={entry.schedule.id} entry={entry} ownerName={ownerName} />
          ))}
        </div>
      </div>
    </div>
  );
}

function TimelineCard({ entry, ownerName }: { entry: TimelineEntry; ownerName: string }) {
  const { schedule, scope } = entry;
  const colorClasses =
    schedule.action === "lock"
      ? "border-rose-400/40 bg-gradient-to-br from-rose-500/20 via-rose-500/10 to-transparent text-rose-100"
      : "border-emerald-400/40 bg-gradient-to-br from-emerald-500/20 via-emerald-500/10 to-transparent text-emerald-100";

  const scopeLabel = scope === "global" ? "Global" : ownerName;

  return (
    <div className="relative pl-4">
      <span className="absolute left-[-10px] top-2 h-3 w-3 rounded-full border-2 border-slate-900 bg-gradient-to-br from-brand-blue/90 to-brand-blue" />
      <div className={`rounded-2xl border ${colorClasses} px-4 py-3`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-100">{schedule.label}</p>
            <p className="text-xs text-slate-300">{scopeLabel}</p>
          </div>
          <span className="rounded-full border border-slate-700/60 px-3 py-1 text-xs text-slate-200">
            {schedule.action.toUpperCase()} → {(schedule.endAction ?? oppositeAction(schedule.action)).toUpperCase()}
          </span>
        </div>
        <div className="mt-3 grid gap-3 text-xs text-slate-200 md:grid-cols-2">
          <div className="rounded-xl border border-slate-700/40 bg-slate-900/50 px-3 py-2">
            <p className="text-[11px] uppercase tracking-[0.3em] text-slate-400">Starts</p>
            <p className="mt-1 font-medium text-slate-100">{formatTimestamp(schedule.window.start)}</p>
          </div>
          <div className="rounded-xl border border-slate-700/40 bg-slate-900/50 px-3 py-2">
            <p className="text-[11px] uppercase tracking-[0.3em] text-slate-400">Ends</p>
            <p className="mt-1 font-medium text-slate-100">{formatTimestamp(schedule.window.end)}</p>
          </div>
        </div>
        {schedule.description ? (
          <p className="mt-3 text-xs text-slate-300">{schedule.description}</p>
        ) : null}
      </div>
    </div>
  );
}

interface ScheduleGroupSectionProps {
  ownerName: string;
  state: GroupState;
  ownerSchedules: DeviceSchedule[];
  globalSchedules: DeviceSchedule[];
  onCreateGroup: (scope: GroupScope) => void;
  onEditGroup: (group: ScheduleGroup, scope: GroupScope) => void;
  onDeleteGroup: (group: ScheduleGroup, scope: GroupScope) => void | Promise<void>;
  onActivateSchedule: (group: ScheduleGroup, scope: GroupScope, scheduleId: string) => void | Promise<void>;
  deletingGroupIds: Set<string>;
  activatingKey: string | null;
  inlineError?: string;
}

function ScheduleGroupSection({
  ownerName,
  state,
  ownerSchedules,
  globalSchedules,
  onCreateGroup,
  onEditGroup,
  onDeleteGroup,
  onActivateSchedule,
  deletingGroupIds,
  activatingKey,
  inlineError
}: ScheduleGroupSectionProps) {
  return (
    <section className="space-y-4 rounded-3xl border border-slate-700/40 bg-slate-900/40 p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-[0.4em] text-slate-400">
            Schedule groups
          </h3>
          <p className="text-xs text-slate-500">
            Bundle schedules and pick a single active policy per group.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onCreateGroup("owner")}
            disabled={ownerSchedules.length === 0}
          >
            New owner group
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onCreateGroup("global")}
            disabled={globalSchedules.length === 0}
          >
            New global group
          </Button>
        </div>
      </header>
      {state.error ? (
        <div className="rounded-2xl border border-status-locked/40 bg-status-locked/10 p-3 text-sm text-status-locked">
          {state.error}
        </div>
      ) : null}
      {inlineError ? (
        <div className="rounded-2xl border border-status-locked/40 bg-status-locked/10 p-3 text-sm text-status-locked">
          {inlineError}
        </div>
      ) : null}
      {state.loading ? (
        <div className="flex items-center justify-center rounded-2xl border border-slate-700/40 bg-slate-900/60 p-6 text-sm text-slate-400">
          Loading groups…
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <GroupColumn
            scope="owner"
            title={`${ownerName} groups`}
            emptyMessage="No owner groups yet."
            groups={state.ownerGroups}
            schedules={ownerSchedules}
            onCreateGroup={onCreateGroup}
            onEditGroup={onEditGroup}
            onDeleteGroup={onDeleteGroup}
            onActivateSchedule={onActivateSchedule}
            deletingGroupIds={deletingGroupIds}
            activatingKey={activatingKey}
          />
          <GroupColumn
            scope="global"
            title="Global groups"
            emptyMessage="No global groups yet."
            groups={state.globalGroups}
            schedules={globalSchedules}
            onCreateGroup={onCreateGroup}
            onEditGroup={onEditGroup}
            onDeleteGroup={onDeleteGroup}
            onActivateSchedule={onActivateSchedule}
            deletingGroupIds={deletingGroupIds}
            activatingKey={activatingKey}
          />
        </div>
      )}
    </section>
  );
}

interface GroupColumnProps {
  scope: GroupScope;
  title: string;
  emptyMessage: string;
  groups: ScheduleGroup[];
  schedules: DeviceSchedule[];
  onCreateGroup: (scope: GroupScope) => void;
  onEditGroup: (group: ScheduleGroup, scope: GroupScope) => void;
  onDeleteGroup: (group: ScheduleGroup, scope: GroupScope) => void | Promise<void>;
  onActivateSchedule: (group: ScheduleGroup, scope: GroupScope, scheduleId: string) => void | Promise<void>;
  deletingGroupIds: Set<string>;
  activatingKey: string | null;
}

function GroupColumn({
  scope,
  title,
  emptyMessage,
  groups,
  schedules,
  onCreateGroup,
  onEditGroup,
  onDeleteGroup,
  onActivateSchedule,
  deletingGroupIds,
  activatingKey
}: GroupColumnProps) {
  return (
    <div className="rounded-2xl border border-slate-700/30 bg-slate-900/40 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-xs uppercase tracking-[0.3em] text-slate-500">{title}</h4>
        <Button
          variant="ghost"
          size="sm"
          className="text-xs text-slate-300 hover:text-slate-100"
          onClick={() => onCreateGroup(scope)}
          disabled={schedules.length === 0}
        >
          Add group
        </Button>
      </div>
      {groups.length === 0 ? (
        <p className="rounded-xl border border-slate-700/40 bg-slate-900/50 p-4 text-sm text-slate-400">
          {emptyMessage}
        </p>
      ) : (
        <ul className="space-y-3">
          {groups.map((group) => (
            <li key={group.id}>
              <GroupCard
                group={group}
                scope={scope}
                onEditGroup={onEditGroup}
                onDeleteGroup={onDeleteGroup}
                onActivateSchedule={onActivateSchedule}
                deleting={deletingGroupIds.has(group.id)}
                activatingKey={activatingKey}
              />
            </li>
          ))}
        </ul>
      )}
      {schedules.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500">
          Create {scope === "owner" ? "owner" : "global"} schedules to enable grouping.
        </p>
      ) : null}
    </div>
  );
}

interface GroupCardProps {
  group: ScheduleGroup;
  scope: GroupScope;
  onEditGroup: (group: ScheduleGroup, scope: GroupScope) => void;
  onDeleteGroup: (group: ScheduleGroup, scope: GroupScope) => void | Promise<void>;
  onActivateSchedule: (group: ScheduleGroup, scope: GroupScope, scheduleId: string) => void | Promise<void>;
  deleting: boolean;
  activatingKey: string | null;
}

function GroupCard({
  group,
  scope,
  onEditGroup,
  onDeleteGroup,
  onActivateSchedule,
  deleting,
  activatingKey
}: GroupCardProps) {
  const activeScheduleId = group.activeScheduleId;
  const schedules = group.schedules ?? [];

  return (
    <div className="rounded-2xl border border-slate-700/40 bg-slate-900/60 p-4 shadow-inner">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-semibold text-slate-100">{group.name}</p>
            {scope === "global" ? (
              <span className="rounded-full border border-slate-700/60 px-2 py-0.5 text-[10px] uppercase tracking-[0.25em] text-slate-400">
                Global
              </span>
            ) : null}
          </div>
          {group.description ? (
            <p className="mt-1 text-xs text-slate-400">{group.description}</p>
          ) : null}
        </div>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="text-xs text-slate-300 hover:text-slate-100"
            onClick={() => onEditGroup(group, scope)}
          >
            Edit
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-xs text-status-locked hover:text-status-locked"
            disabled={deleting}
            onClick={() => {
              void onDeleteGroup(group, scope);
            }}
          >
            {deleting ? "Removing…" : "Delete"}
          </Button>
        </div>
      </div>
      <div className="mt-3 space-y-3">
        {schedules.length === 0 ? (
          <p className="rounded-xl border border-slate-700/40 bg-slate-900/70 p-3 text-xs text-slate-400">
            This group has no schedules assigned.
          </p>
        ) : (
          schedules.map((schedule) => {
            const isActive = schedule.id === activeScheduleId;
            const key = `${group.id}:${schedule.id}`;
            const isActivating = activatingKey === key;
            return (
              <div
                key={schedule.id}
                className={`rounded-xl border px-3 py-3 text-xs transition ${
                  isActive
                    ? "border-brand-blue/70 bg-brand-blue/10"
                    : "border-slate-700/40 bg-slate-900/60 hover:border-brand-blue/40"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-100">
                      {schedule.label}
                    </p>
                    <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">
                      {formatTimestamp(schedule.window.start)} → {formatTimestamp(schedule.window.end)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {isActive ? (
                      <span className="rounded-full border border-brand-blue/40 bg-brand-blue/20 px-3 py-1 text-[11px] uppercase tracking-[0.35em] text-brand-blue">
                        Active
                      </span>
                    ) : (
                      <Button
                        variant="secondary"
                        size="sm"
                        className="text-xs"
                        disabled={isActivating}
                        onClick={() => {
                          void onActivateSchedule(group, scope, schedule.id);
                        }}
                      >
                        {isActivating ? "Setting…" : "Set active"}
                      </Button>
                    )}
                  </div>
                </div>
                <div className="mt-2 grid gap-2 text-[11px] text-slate-400 md:grid-cols-2">
                  <p>
                    <span className="uppercase tracking-[0.3em] text-slate-500">Start</span>
                    <span className="ml-2 capitalize text-slate-200">{schedule.action}</span>
                  </p>
                  <p>
                    <span className="uppercase tracking-[0.3em] text-slate-500">End</span>
                    <span className="ml-2 capitalize text-slate-200">
                      {schedule.endAction ?? oppositeAction(schedule.action)}
                    </span>
                  </p>
                  <p className="md:col-span-2">
                    <span className="uppercase tracking-[0.3em] text-slate-500">Recurs</span>
                    <span className="ml-2 text-slate-200">{describeRecurrence(schedule)}</span>
                  </p>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

interface GroupEditorDialogProps {
  ownerName: string;
  state: GroupDialogState;
  availableSchedules: DeviceSchedule[];
  onClose: () => void;
  onSubmit: (values: GroupFormValues) => void | Promise<void>;
  submitting: boolean;
  error?: string;
}

function GroupEditorDialog({
  ownerName,
  state,
  availableSchedules,
  onClose,
  onSubmit,
  submitting,
  error
}: GroupEditorDialogProps) {
  const initialValues = useMemo<GroupFormValues>(() => {
    if (state.mode === "edit" && state.group) {
      const scheduleIds = state.group.schedules.map((schedule) => schedule.id);
      const activeId =
        state.group.activeScheduleId && scheduleIds.includes(state.group.activeScheduleId)
          ? state.group.activeScheduleId
          : scheduleIds[0];
      return {
        name: state.group.name,
        description: state.group.description ?? "",
        scheduleIds,
        activeScheduleId: activeId
      };
    }
    const firstId = availableSchedules[0]?.id;
    return {
      name: "",
      description: "",
      scheduleIds: firstId ? [firstId] : [],
      activeScheduleId: firstId
    };
  }, [state, availableSchedules]);

  const [form, setForm] = useState<GroupFormValues>(initialValues);

  useEffect(() => {
    setForm(initialValues);
  }, [initialValues]);

  const toggleSchedule = (scheduleId: string) => {
    setForm((prev) => {
      const exists = prev.scheduleIds.includes(scheduleId);
      if (exists) {
        const nextIds = prev.scheduleIds.filter((id) => id !== scheduleId);
        const nextActive = prev.activeScheduleId === scheduleId ? nextIds[0] ?? undefined : prev.activeScheduleId;
        return {
          ...prev,
          scheduleIds: nextIds,
          activeScheduleId: nextActive
        };
      }
      const nextIds = [...prev.scheduleIds, scheduleId];
      return {
        ...prev,
        scheduleIds: nextIds,
        activeScheduleId: prev.activeScheduleId ?? scheduleId
      };
    });
  };

  const setActiveSchedule = (scheduleId: string) => {
    setForm((prev) =>
      prev.scheduleIds.includes(scheduleId)
        ? {
            ...prev,
            activeScheduleId: scheduleId
          }
        : prev
    );
  };

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void onSubmit(form);
  };

  const scopeLabel = state.scope === "owner" ? `${ownerName} group` : "Global group";

  return (
    <div className="absolute inset-0 z-[1450] flex items-center justify-center bg-slate-950/90 px-4">
      <div className="w-full max-w-3xl rounded-3xl border border-slate-700/40 bg-slate-900/95 p-6 shadow-[0_35px_90px_rgba(10,12,34,0.7)]">
        <header className="mb-4 flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.4em] text-slate-500">
              {state.mode === "create" ? "Create group" : "Edit group"}
            </p>
            <h4 className="text-lg font-semibold text-slate-100">{scopeLabel}</h4>
          </div>
          <Button variant="ghost" onClick={onClose} className="text-slate-300 hover:text-slate-100">
            Close
          </Button>
        </header>
        {availableSchedules.length === 0 ? (
          <div className="rounded-2xl border border-slate-700/40 bg-slate-900/50 p-4 text-sm text-slate-400">
            No schedules available to assign. Create a schedule first.
          </div>
        ) : (
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
                Group name
                <input
                  className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
                  value={form.name}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      name: event.target.value
                    }))
                  }
                  placeholder="Weeknight curfew"
                />
              </label>
              <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
                Description
                <input
                  className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
                  value={form.description}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      description: event.target.value
                    }))
                  }
                  placeholder="Optional details"
                />
              </label>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Schedules</p>
              <ul className="mt-3 space-y-2">
                {availableSchedules.map((schedule) => {
                  const selected = form.scheduleIds.includes(schedule.id);
                  const isActive = form.activeScheduleId === schedule.id;
                  return (
                    <li
                      key={schedule.id}
                      className={`rounded-xl border px-3 py-3 text-xs transition ${
                        selected
                          ? "border-brand-blue/50 bg-brand-blue/10"
                          : "border-slate-700/40 bg-slate-900/60 hover:border-brand-blue/40"
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <label className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={() => toggleSchedule(schedule.id)}
                            className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-brand-blue focus:ring-brand-blue"
                          />
                          <span className="text-sm text-slate-100">{schedule.label}</span>
                        </label>
                        <div className="flex items-center gap-2">
                          {selected ? (
                            <Button
                              type="button"
                              variant={isActive ? "outline" : "secondary"}
                              size="sm"
                              className="text-xs"
                              disabled={isActive}
                              onClick={() => setActiveSchedule(schedule.id)}
                            >
                              {isActive ? "Active" : "Set active"}
                            </Button>
                          ) : null}
                        </div>
                      </div>
                      <div className="mt-2 grid gap-2 text-[11px] text-slate-400 md:grid-cols-2">
                        <p>
                          <span className="uppercase tracking-[0.3em] text-slate-500">Window</span>
                          <span className="ml-2 text-slate-200">
                            {formatTimestamp(schedule.window.start)} → {formatTimestamp(schedule.window.end)}
                          </span>
                        </p>
                        <p>
                          <span className="uppercase tracking-[0.3em] text-slate-500">Recurs</span>
                          <span className="ml-2 text-slate-200">{describeRecurrence(schedule)}</span>
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
            {error ? (
              <div className="rounded-xl border border-status-locked/40 bg-status-locked/10 p-3 text-xs text-status-locked">
                {error}
              </div>
            ) : null}
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                className="text-slate-300 hover:text-slate-100"
                onClick={onClose}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? "Saving…" : state.mode === "create" ? "Create group" : "Save changes"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

interface EventListProps {
  title: string;
  schedules: DeviceSchedule[];
  emptyMessage: string;
  onDelete: (schedule: DeviceSchedule) => void;
  deletingIds: Set<string>;
  onCopy?: (schedule: DeviceSchedule) => void;
  showCopyButton?: boolean;
  copyDisabled?: boolean;
}

function EventList({
  title,
  schedules,
  emptyMessage,
  onDelete,
  deletingIds,
  onCopy,
  showCopyButton = false,
  copyDisabled = false
}: EventListProps) {
  return (
    <div>
      <h3 className="text-sm uppercase tracking-[0.3em] text-slate-500">{title}</h3>
      {schedules.length === 0 ? (
        <p className="mt-3 rounded-2xl border border-slate-700/40 bg-slate-900/40 p-4 text-sm text-slate-400">
          {emptyMessage}
        </p>
      ) : (
        <ul className="mt-3 space-y-3">
          {schedules.map((schedule) => (
            <li
              key={schedule.id}
              className="rounded-2xl border border-slate-700/40 bg-slate-900/50 p-4 shadow-inner transition hover:border-brand-blue/50 hover:bg-slate-900/70"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-100">{schedule.label}</p>
                  {schedule.description ? (
                    <p className="text-xs text-slate-400">{schedule.description}</p>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                  <span className="rounded-full border border-slate-700/60 px-3 py-1 text-slate-300">
                    Starts · {formatTimestamp(schedule.window.start)}
                  </span>
                  <span className="rounded-full border border-slate-700/60 px-3 py-1 text-slate-300">
                    Ends · {formatTimestamp(schedule.window.end)}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {showCopyButton ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      className="text-xs"
                      disabled={copyDisabled || !onCopy}
                      onClick={() => onCopy?.(schedule)}
                    >
                      Copy
                    </Button>
                  ) : null}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-xs text-status-locked hover:text-status-locked"
                    disabled={deletingIds.has(schedule.id)}
                    onClick={() => onDelete(schedule)}
                  >
                    {deletingIds.has(schedule.id) ? "Removing…" : "Delete"}
                  </Button>
                </div>
              </div>
              <div className="mt-3 grid gap-3 text-xs text-slate-400 md:grid-cols-2">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Start action</p>
                  <p className="mt-1 text-slate-200 capitalize">{schedule.action}</p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">End action</p>
                  <p className="mt-1 text-slate-200 capitalize">
                    {schedule.endAction ?? oppositeAction(schedule.action)}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Recurrence</p>
                  <p className="mt-1 text-slate-200 capitalize">{describeRecurrence(schedule)}</p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Status</p>
                  <p className="mt-1 text-slate-200">{schedule.enabled ? "Enabled" : "Disabled"}</p>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface EventFormProps {
  form: EventFormState;
  submitting: boolean;
  error?: string;
  timezone: string;
  onChange: ChangeHandler;
  onToggleDay: (day: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
}

function EventForm({ form, submitting, error, timezone, onChange, onToggleDay, onSubmit }: EventFormProps) {
  return (
    <form
      className="space-y-4 rounded-3xl border border-slate-700/40 bg-gradient-to-br from-slate-900/80 via-slate-900/70 to-slate-900/80 p-6 shadow-inner"
      onSubmit={onSubmit}
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm uppercase tracking-[0.4em] text-slate-400">Create new event</h3>
        <span className="text-xs text-slate-500">All times in {timezone}</span>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="md:col-span-2">
          <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Event label
            <input
              className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
              placeholder="Homework lock window"
              value={form.label}
              onChange={onChange("label")}
            />
          </label>
        </div>
        <div>
          <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Starts
            <input
              type="datetime-local"
              className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
              value={form.start}
              onChange={onChange("start")}
            />
          </label>
        </div>
        <div>
          <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Ends
            <input
              type="datetime-local"
              className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
              value={form.end}
              onChange={onChange("end")}
            />
          </label>
        </div>
        <div>
          <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Action at start
            <select
              className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
              value={form.startAction}
              onChange={onChange("startAction")}
            >
              <option value="lock">Lock devices</option>
              <option value="unlock">Unlock devices</option>
            </select>
          </label>
        </div>
        <div>
          <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Action at end
            <select
              className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
              value={form.endAction}
              onChange={onChange("endAction")}
            >
              <option value="lock">Lock devices</option>
              <option value="unlock">Unlock devices</option>
            </select>
          </label>
        </div>
        <div>
          <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Recurrence
            <select
              className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
              value={form.recurrenceType}
              onChange={onChange("recurrenceType")}
            >
              <option value="one_shot">One-time</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>
        </div>
        {form.recurrenceType !== "one_shot" ? (
          <div>
            <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
              Every
              <input
                type="number"
                min={1}
                className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
                value={form.interval}
                onChange={onChange("interval")}
              />
            </label>
          </div>
        ) : null}
        {form.recurrenceType === "weekly" ? (
          <div className="md:col-span-2">
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Days of week</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {WEEK_DAYS.map((day) => {
                const active = form.daysOfWeek.includes(day);
                return (
                  <button
                    key={day}
                    type="button"
                    onClick={() => onToggleDay(day)}
                    className={`rounded-full border px-3 py-1 text-xs transition ${
                      active
                        ? "border-brand-blue/60 bg-brand-blue/20 text-brand-blue"
                        : "border-slate-700/60 bg-slate-900/70 text-slate-200 hover:border-brand-blue/50 hover:text-brand-blue"
                    }`}
                  >
                    {day}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
        {form.recurrenceType === "monthly" ? (
          <div>
            <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
              Day of month
              <input
                type="number"
                min={1}
                max={31}
                className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
                value={form.dayOfMonth}
                onChange={onChange("dayOfMonth")}
              />
            </label>
          </div>
        ) : null}
        {form.recurrenceType !== "one_shot" ? (
          <div>
            <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
              Until (optional)
              <input
                type="date"
                className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
                value={form.until}
                onChange={onChange("until")}
              />
            </label>
          </div>
        ) : null}
        <div className="md:col-span-2">
          <label className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Notes
            <textarea
              className="mt-2 w-full rounded-lg border border-slate-700/60 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 focus:border-brand-blue focus:outline-none focus:ring-1 focus:ring-brand-blue"
              rows={2}
              placeholder="Optional description"
              value={form.description}
              onChange={onChange("description")}
            />
          </label>
        </div>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-xs text-status-locked">{error ?? ""}</span>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : "Add event"}
        </Button>
      </div>
    </form>
  );
}

function describeRecurrence(schedule: DeviceSchedule): string {
  const recurrence = schedule.recurrence;
  switch (recurrence.type) {
    case "one_shot":
      return "One-time";
    case "daily":
      return recurrence.interval && recurrence.interval > 1 ? `Every ${recurrence.interval} days` : "Daily";
    case "weekly":
      return recurrence.daysOfWeek?.length
        ? `Weekly on ${recurrence.daysOfWeek.join(", ")}`
        : recurrence.interval && recurrence.interval > 1
        ? `Every ${recurrence.interval} weeks`
        : "Weekly";
    case "monthly":
      return recurrence.dayOfMonth
        ? recurrence.interval && recurrence.interval > 1
          ? `Every ${recurrence.interval} months on day ${recurrence.dayOfMonth}`
          : `Monthly on day ${recurrence.dayOfMonth}`
        : "Monthly";
    default:
      return "Recurring";
  }
}

function oppositeAction(action: ScheduleAction): ScheduleAction {
  return action === "lock" ? "unlock" : "lock";
}

function buildRecurrence(params: {
  type: ScheduleRecurrenceType;
  startDate: Date;
  interval: number;
  daysOfWeek: string[];
  dayOfMonth: string;
  until: string | null;
}): ScheduleRecurrence {
  const { type, startDate, interval, daysOfWeek, dayOfMonth, until } = params;

  if (type === "one_shot") {
    return {
      type: "one_shot"
    };
  }

  if (type === "daily") {
    return {
      type: "daily",
      interval,
      until
    };
  }

  if (type === "weekly") {
    const normalizedDays =
      daysOfWeek.length > 0
        ? daysOfWeek
        : [
            new Intl.DateTimeFormat("en-US", {
              weekday: "short"
            })
              .format(startDate)
              .slice(0, 3)
          ];
    return {
      type: "weekly",
      interval,
      daysOfWeek: normalizedDays,
      until
    };
  }

  const parsedDay = Number.parseInt(dayOfMonth, 10);
  const fallbackDay = startDate.getDate();
  const normalizedDay = Number.isFinite(parsedDay) && parsedDay >= 1 && parsedDay <= 31 ? parsedDay : fallbackDay;

  return {
    type: "monthly",
    interval,
    dayOfMonth: normalizedDay,
    until
  };
}
