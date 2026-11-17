import type { ReactNode } from "react";
import type { Kind, Transaction } from "../api";
import { dayKey, dayLabel, money, timeLabel } from "../format";

const KIND_STYLE: Record<Kind, string> = {
  expense: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  transfer: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
  settlement: "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300",
  income: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  refund: "bg-teal-100 text-teal-800 dark:bg-teal-900/40 dark:text-teal-300",
};

function Badge({ className, children }: { className: string; children: ReactNode }) {
  return <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${className}`}>{children}</span>;
}

function Row({ t }: { t: Transaction }) {
  const debit = t.direction === "debit";
  const title = t.counterparty_name || t.vpa_or_merchant || "Unknown";
  return (
    <li className="flex items-start justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <div className="truncate font-medium">{title}</div>
        {t.vpa_or_merchant && t.vpa_or_merchant !== title && (
          <div className="truncate text-xs text-slate-500 dark:text-slate-400">{t.vpa_or_merchant}</div>
        )}
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <Badge className="bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">{t.account.name}</Badge>
          {t.kind ? (
            <Badge className={KIND_STYLE[t.kind]}>{t.kind}</Badge>
          ) : (
            <Badge className="bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300">to review</Badge>
          )}
          <span className="text-xs text-slate-400">{timeLabel(t.ts)}</span>
        </div>
      </div>
      <div
        className={`shrink-0 font-semibold tabular-nums ${
          debit ? "text-rose-600 dark:text-rose-400" : "text-emerald-600 dark:text-emerald-400"
        }`}
      >
        {debit ? "−" : "+"}
        {money(t.amount)}
      </div>
    </li>
  );
}

export function TransactionList({ items }: { items: Transaction[] }) {
  if (items.length === 0) {
    return <p className="py-12 text-center text-sm text-slate-500">No transactions for this filter yet.</p>;
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
          <section key={day}>
            <h2 className="mb-1 flex justify-between px-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              <span>{dayLabel(day)}</span>
              {out > 0 && <span className="tabular-nums">out {money(out)}</span>}
            </h2>
            <ul className="divide-y divide-slate-100 overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-200 dark:divide-slate-800 dark:bg-slate-900 dark:ring-slate-800">
              {txns.map((t) => (
                <Row key={t.id} t={t} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
