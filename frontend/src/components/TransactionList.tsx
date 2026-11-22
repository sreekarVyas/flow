import type { Transaction } from "../api";
import { hasCategory, KIND_LABEL, type CatInfo } from "../categories";
import { dayKey, dayLabel, money, timeLabel } from "../format";
import { CategoryChip, type ChipState } from "./CategoryChip";

export function chipState(t: Transaction): ChipState {
  if (t.category_id == null) return "empty";
  return t.confirmed || t.category_source === "manual" ? "stamp" : "pencil";
}

/** Needs Siri: no kind, an expense with no category, or a rule's guess not yet confirmed. */
export function needsReview(t: Transaction): boolean {
  if (t.kind == null) return true;
  if (!hasCategory(t.kind)) return false;
  return t.category_id == null || !t.confirmed;
}

function Row({
  t,
  info,
  stamped,
  onSelect,
  onConfirm,
}: {
  t: Transaction;
  info?: CatInfo;
  stamped: boolean;
  onSelect: (t: Transaction) => void;
  onConfirm: (t: Transaction) => void;
}) {
  const debit = t.direction === "debit";
  const title = t.counterparty_name || t.vpa_or_merchant || "Unknown payee";
  const state = chipState(t);
  const shared = t.splits.filter((s) => s.paid_by === "me");
  return (
    <li className="flex items-stretch">
      <button
        type="button"
        onClick={() => onSelect(t)}
        className="flex min-w-0 flex-1 items-start justify-between gap-3 px-4 py-3 text-left hover:bg-surface-2/60 focus-visible:bg-surface-2/60"
      >
        <span className="min-w-0">
          <span className="block truncate font-medium">{title}</span>
          {t.notes && <span className="block truncate text-sm text-ink-muted">“{t.notes}”</span>}
          <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
            {t.kind == null ? (
              <span className="rounded-md bg-warn-soft px-1.5 py-0.5 text-xs font-medium text-warn">Needs a kind</span>
            ) : hasCategory(t.kind) ? (
              <>
                <CategoryChip info={info} state={state} animate={stamped} />
                {t.kind === "refund" && <span className="text-xs text-ink-muted">Refund</span>}
              </>
            ) : (
              <span className="text-xs font-medium text-ink-muted">{KIND_LABEL[t.kind]}</span>
            )}
            {shared.length > 0 && (
              <span className="rounded-md bg-surface-2 px-1.5 py-0.5 text-xs font-medium">
                Split with {shared.map((s) => s.person.display_name).join(", ")}
              </span>
            )}
            <span className="text-xs text-ink-muted">
              {t.account.name}, {timeLabel(t.ts)}
            </span>
          </span>
        </span>
        <span className="shrink-0 text-right">
          <span className={`block font-semibold ${debit ? "text-out" : "text-in"}`}>
            {debit ? "−" : "+"}
            {money(t.amount)}
          </span>
          {shared.length > 0 && <span className="block text-xs text-ink-muted">you {money(t.my_share)}</span>}
        </span>
      </button>
      {state === "pencil" && (
        <button
          type="button"
          onClick={() => onConfirm(t)}
          aria-label={`Confirm ${info?.label ?? "category"} for ${title}`}
          title="Confirm this tag"
          className="flex w-12 shrink-0 items-center justify-center border-l border-line text-lg text-stamp hover:bg-stamp-soft"
        >
          ✓
        </button>
      )}
    </li>
  );
}

export function TransactionList({
  items,
  byId,
  stampedIds,
  emptyText,
  onSelect,
  onConfirm,
}: {
  items: Transaction[];
  byId: Map<number, CatInfo>;
  stampedIds: Set<number>;
  emptyText: string;
  onSelect: (t: Transaction) => void;
  onConfirm: (t: Transaction) => void;
}) {
  if (items.length === 0) {
    return <p className="py-12 text-center text-sm text-ink-muted">{emptyText}</p>;
  }
  const groups = new Map<string, Transaction[]>();
  for (const t of items) {
    const k = dayKey(t.ts);
    groups.set(k, [...(groups.get(k) ?? []), t]);
  }
  return (
    <div className="space-y-4">
      {[...groups].map(([day, txns]) => {
        const out = txns.filter((t) => t.direction === "debit").reduce((s, t) => s + Number(t.amount), 0);
        return (
          <section key={day} aria-label={dayLabel(day)}>
            <h2 className="mb-1 flex justify-between px-1 text-sm font-semibold text-ink-muted">
              <span>{dayLabel(day)}</span>
              {out > 0 && <span className="font-medium">{money(out)} out</span>}
            </h2>
            <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
              {txns.map((t) => (
                <Row
                  key={t.id}
                  t={t}
                  info={t.category_id != null ? byId.get(t.category_id) : undefined}
                  stamped={stampedIds.has(t.id)}
                  onSelect={onSelect}
                  onConfirm={onConfirm}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
