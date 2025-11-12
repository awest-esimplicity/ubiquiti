import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import type { OwnerSummary } from "@/lib/domain/models";

interface PinModalProps {
  owner: OwnerSummary;
  pinValue: string;
  error?: string;
  onDigit: (digit: string) => void;
  onBackspace: () => void;
  onClear: () => void;
  onCancel: () => void;
  onSubmit: () => void;
}

const keypadRows = [
  ["1", "2", "3"],
  ["4", "5", "6"],
  ["7", "8", "9"]
] as const;

export function PinModal({
  owner,
  pinValue,
  error,
  onDigit,
  onBackspace,
  onClear,
  onCancel,
  onSubmit
}: PinModalProps) {
  const isComplete = pinValue.length === 4;
  const displayValue = useMemo(() => "*".repeat(pinValue.length).padEnd(4, "•"), [pinValue]);

  return (
    <div className="fixed inset-0 z-[1200] flex items-center justify-center bg-slate-950/70 backdrop-blur-md px-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-700/50 bg-slate-900/90 p-7 shadow-[0_30px_70px_rgba(15,23,42,0.6)]">
        <div className="mb-6">
          <h2 className="text-xl font-semibold text-slate-50">Unlock {owner.displayName}</h2>
          <p className="mt-2 text-sm text-slate-400">Enter the 4-digit PIN to continue.</p>
        </div>

        <div className="mb-4 flex items-center justify-between rounded-xl border border-slate-700/60 bg-slate-800/60 px-4 py-3 font-mono text-2xl tracking-[0.6em] text-slate-100">
          {displayValue.split("").map((char, index) => (
            <span key={index}>{char}</span>
          ))}
        </div>

        {error ? <p className="mb-4 rounded-lg border border-status-locked/40 bg-status-locked/10 px-3 py-2 text-sm text-status-locked">{error}</p> : null}

        <div className="grid grid-cols-3 gap-3">
          {keypadRows.map((row) =>
            row.map((digit) => (
              <Button
                key={digit}
                variant="secondary"
                size="lg"
                className="h-14 text-lg font-semibold"
                onClick={() => onDigit(digit)}
                disabled={pinValue.length >= 4}
              >
                {digit}
              </Button>
            ))
          )}
          <Button variant="ghost" size="lg" className="h-14 text-sm uppercase tracking-wide text-slate-300" onClick={onClear}>
            Clear
          </Button>
          <Button
            variant="secondary"
            size="lg"
            className="h-14 text-lg font-semibold"
            onClick={() => onDigit("0")}
            disabled={pinValue.length >= 4}
          >
            0
          </Button>
          <Button variant="ghost" size="lg" className="h-14 text-lg" onClick={onBackspace}>
            ⌫
          </Button>
        </div>

        <div className="mt-6 flex gap-3">
          <Button variant="ghost" className="flex-1 border border-slate-700" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="primary" className="flex-1" onClick={onSubmit} disabled={!isComplete}>
            Unlock
          </Button>
        </div>
      </div>
    </div>
  );
}
