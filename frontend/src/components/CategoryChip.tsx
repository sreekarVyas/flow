import type { CatInfo } from "../categories";

/**
 * stamp  — Siri tagged or confirmed it: solid violet.
 * pencil — a rule guessed it and nobody confirmed it yet: dashed, grey.
 * empty  — no category yet.
 */
export type ChipState = "stamp" | "pencil" | "empty";

export function CategoryChip({ info, state, animate }: { info?: CatInfo; state: ChipState; animate?: boolean }) {
  if (state === "empty" || !info) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-dashed border-stamp/60 px-1.5 py-0.5 text-xs font-medium text-stamp">
        + Tag
      </span>
    );
  }
  const base = "inline-flex max-w-full items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium";
  if (state === "pencil") {
    return (
      <span className={`${base} border border-dashed border-pencil text-ink-muted`} title={`${info.path} (set by a rule)`}>
        <span aria-hidden>{info.icon}</span>
        <span className="truncate">{info.label}</span>
        <span className="sr-only">, set by a rule, not confirmed</span>
      </span>
    );
  }
  return (
    <span
      className={`${base} border border-stamp bg-stamp text-on-stamp ${animate ? "animate-stamp" : ""}`}
      title={info.path}
    >
      <span aria-hidden>{info.icon}</span>
      <span className="truncate">{info.label}</span>
    </span>
  );
}
