import { ICONS } from "@/components/icons";
import type { OwnerSummary } from "@/lib/domain/models";
import { cn } from "@/lib/utils/cn";

interface OwnerCardProps {
  owner: OwnerSummary;
  onSelect: (owner: OwnerSummary) => void;
  className?: string;
}

export function OwnerCard({ owner, onSelect, className }: OwnerCardProps) {
  const lockedCount = owner.devices.filter((device) => device.locked).length;
  const unlockedCount = owner.devices.length - lockedCount;
  const ratio = owner.devices.length === 0 ? 0 : Math.round((lockedCount / owner.devices.length) * 100);

  return (
    <button
      type="button"
      onClick={() => onSelect(owner)}
      className={cn(
        "group relative w-full rounded-2xl border border-border/60 bg-gradient-to-br from-[#141f35] via-[#0d1427] to-[#0a1223] p-6 text-left shadow-card transition-all duration-200 hover:-translate-y-1 hover:border-brand-blue/50 hover:shadow-[0_24px_45px_rgba(37,99,235,0.35)]",
        className
      )}
    >
      <header className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold tracking-tight text-slate-50">{owner.displayName}</h3>
          <p className="text-xs uppercase tracking-[0.2em] text-slate-400 mt-1">Owner overview</p>
        </div>
        <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-brand-blue/40 bg-brand-blue/20 text-brand-blue">
          {ICONS.users}
        </span>
      </header>

      <div className="mt-6 space-y-5">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-brand-blue/20 text-brand-blue">
            {ICONS.devices}
          </span>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Total devices</p>
            <p className="text-2xl font-semibold text-slate-100">{owner.devices.length}</p>
          </div>
        </div>

        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-2 text-sm font-medium text-status-locked">
            {ICONS.locked}
            <span>{lockedCount} locked</span>
          </span>
          <span className="inline-flex items-center gap-2 text-sm font-medium text-status-unlocked">
            {ICONS.unlocked}
            <span>{unlockedCount} unlocked</span>
          </span>
        </div>

        <div>
          <div className="h-2 w-full rounded-full bg-slate-700/60">
            <div
              className="h-2 rounded-full bg-gradient-to-r from-status-locked to-red-500 transition-all"
              style={{ width: `${ratio}%` }}
            />
          </div>
          <p className="mt-2 text-xs font-medium text-slate-400">{ratio}% locked</p>
        </div>
      </div>
    </button>
  );
}
