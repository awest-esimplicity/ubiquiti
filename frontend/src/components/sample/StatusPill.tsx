interface StatusPillProps {
  label: string;
  variant?: "locked" | "unlocked";
}

export function StatusPill({ label, variant = "unlocked" }: StatusPillProps) {
  const isLocked = variant === "locked";
  return (
    <span
      data-locked={isLocked}
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${
        isLocked
          ? "border-status-locked/40 bg-status-locked/10 text-status-locked"
          : "border-status-unlocked/40 bg-status-unlocked/10 text-status-unlocked"
      }`}
    >
      <span aria-hidden>{isLocked ? "🔒" : "🔓"}</span>
      {label}
    </span>
  );
}
