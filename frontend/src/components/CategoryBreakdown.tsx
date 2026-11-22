import { useState } from "react";
import type { CategorySummary, ParentSpend } from "../api";
import { money } from "../format";

export type CatFilter = { type: "cat"; id: number; parentId: number | null; label: string } | { type: "untagged" } | null;

const TOP = 5;

function Bar({ value, max, pencil }: { value: number; max: number; pencil?: boolean }) {
  const pct = max > 0 ? Math.max(2, (value / max) * 100) : 0;
  return (
    <span className="mt-1 block h-1.5 w-full overflow-hidden rounded-full bg-surface-2" aria-hidden>
      <span
        className={`block h-full rounded-full ${pencil ? "bg-pencil" : "bg-stamp"}`}
        style={{ width: `${pct}%` }}
      />
    </span>
  );
}

export function CategoryBreakdown({
  data,
  filter,
  onFilter,
}: {
  data: CategorySummary;
  filter: CatFilter;
  onFilter: (f: CatFilter) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const total = Number(data.total);
  const untagged = Number(data.untagged_total);
  const parents = data.parents.filter((p) => Number(p.total) !== 0);
  const max = Math.max(untagged, ...parents.map((p) => Number(p.total)), 0);
  const shown = showAll ? parents : parents.slice(0, TOP);

  const openParent = filter?.type === "cat" ? (filter.parentId ?? filter.id) : null;
  const isActive = (id: number) => filter?.type === "cat" && filter.id === id;
  const toggle = (f: Exclude<CatFilter, null>) =>
    onFilter(
      (f.type === "untagged" && filter?.type === "untagged") || (f.type === "cat" && isActive(f.id)) ? null : f,
    );

  if (total === 0 && untagged === 0) {
    return null;
  }

  const rowClass = (active: boolean) =>
    "w-full rounded-lg px-2 py-2 text-left transition-colors " +
    (active ? "bg-stamp-soft ring-1 ring-stamp" : "hover:bg-surface-2/70");

  const parentRow = (p: ParentSpend) => (
    <li key={p.id}>
      <button
        type="button"
        aria-pressed={isActive(p.id)}
        aria-expanded={openParent === p.id}
        onClick={() => toggle({ type: "cat", id: p.id, parentId: null, label: p.name })}
        className={rowClass(isActive(p.id))}
      >
        <span className="flex items-baseline justify-between gap-3">
          <span className="truncate font-medium">
            <span aria-hidden className="mr-1.5">
              {p.icon}
            </span>
            {p.name}
          </span>
          <span className="shrink-0 font-semibold">{money(p.total)}</span>
        </span>
        <Bar value={Number(p.total)} max={max} />
      </button>
      {openParent === p.id && (p.children.length > 0 || Number(p.own_total) !== 0) && (
        <ul className="mb-1 ml-7 mt-0.5 space-y-0.5 border-l-2 border-line pl-2">
          {p.children.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                aria-pressed={isActive(c.id)}
                onClick={() => toggle({ type: "cat", id: c.id, parentId: p.id, label: c.name })}
                className={rowClass(isActive(c.id)) + " py-1.5 text-sm"}
              >
                <span className="flex items-baseline justify-between gap-3">
                  <span className="truncate">
                    <span aria-hidden className="mr-1.5">
                      {c.icon}
                    </span>
                    {c.name}
                    <span className="ml-1.5 text-ink-muted">{c.count}</span>
                  </span>
                  <span className="shrink-0">{money(c.total)}</span>
                </span>
              </button>
            </li>
          ))}
          {Number(p.own_total) !== 0 && (
            <li className="flex justify-between px-2 py-1.5 text-sm text-ink-muted">
              <span>Tagged as {p.name} only</span>
              <span>{money(p.own_total)}</span>
            </li>
          )}
        </ul>
      )}
    </li>
  );

  return (
    <section aria-labelledby="breakdown-heading" className="rounded-xl border border-line bg-surface p-3">
      <div className="flex items-baseline justify-between gap-3 px-2">
        <h2 id="breakdown-heading" className="font-semibold">
          Spending by category
        </h2>
        <span className="text-lg font-semibold">{money(total)}</span>
      </div>

      {/* One proportional strip: each parent's share of the month, untagged last in pencil. */}
      <div className="mx-2 mt-2 flex h-2.5 gap-0.5 overflow-hidden rounded-full" aria-hidden>
        {parents.map((p, i) => (
          <span
            key={p.id}
            className="h-full bg-stamp"
            style={{ flexGrow: Number(p.total), opacity: Math.max(0.25, 1 - i * 0.09) }}
          />
        ))}
        {untagged > 0 && (
          <span
            className="h-full"
            style={{
              flexGrow: untagged,
              background: "repeating-linear-gradient(135deg, var(--pencil) 0 3px, transparent 3px 6px)",
            }}
          />
        )}
      </div>

      <ul className="mt-2 space-y-0.5">
        {shown.map(parentRow)}
        {untagged !== 0 && (
          <li>
            <button
              type="button"
              aria-pressed={filter?.type === "untagged"}
              onClick={() => toggle({ type: "untagged" })}
              className={rowClass(filter?.type === "untagged")}
            >
              <span className="flex items-baseline justify-between gap-3">
                <span className="text-ink-muted">
                  Untagged
                  <span className="ml-1.5">{data.untagged_count}</span>
                </span>
                <span className="shrink-0 font-semibold text-ink-muted">{money(untagged)}</span>
              </span>
              <Bar value={untagged} max={max} pencil />
            </button>
          </li>
        )}
      </ul>

      {parents.length > TOP && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-1 px-2 text-sm font-medium text-stamp hover:underline"
        >
          {showAll ? "Show top 5" : `Show all ${parents.length} categories`}
        </button>
      )}
    </section>
  );
}
