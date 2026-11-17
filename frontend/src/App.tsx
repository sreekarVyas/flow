import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "./api";
import { AccountFilter, type Filter } from "./components/AccountFilter";
import { SummaryBar } from "./components/SummaryBar";
import { TransactionList } from "./components/TransactionList";
import { UnparsedList } from "./components/UnparsedList";
import { monthLabel, relative } from "./format";

// Phase 1 shows November 2026 only. Override with ?month=YYYY-MM.
const MONTH = new URLSearchParams(location.search).get("month") ?? "2026-11";

export default function App() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>("all");
  const [showUnparsed, setShowUnparsed] = useState(false);

  const txns = useQuery({
    queryKey: ["transactions", MONTH, filter],
    queryFn: () => api.transactions(MONTH, filter === "all" ? undefined : filter),
  });
  const summary = useQuery({ queryKey: ["summary", MONTH], queryFn: () => api.summary(MONTH), refetchInterval: 60_000 });
  const sync = useMutation({ mutationFn: api.sync, onSettled: () => qc.invalidateQueries() });

  const s = summary.data;
  return (
    <div className="mx-auto max-w-2xl space-y-4 px-4 pb-16 pt-[max(1rem,env(safe-area-inset-top))]">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{monthLabel(MONTH)}</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {s?.last_poll_at ? `Synced ${relative(s.last_poll_at)}` : "Not synced yet"}
          </p>
        </div>
        <button
          onClick={() => sync.mutate()}
          disabled={sync.isPending}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
        >
          {sync.isPending ? "Syncing…" : "Sync now"}
        </button>
      </header>

      {sync.error && <p className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">{sync.error.message}</p>}
      {sync.data && (
        <p className="text-xs text-slate-500">
          Sync: {sync.data.fetched} new emails · {sync.data.txn} transactions · {sync.data.ignored} ignored · {sync.data.unknown} unknown
        </p>
      )}

      {s && <SummaryBar summary={s} />}
      <AccountFilter value={filter} onChange={setFilter} />

      {txns.isPending && <p className="py-12 text-center text-sm text-slate-500">Loading…</p>}
      {txns.error && <p className="text-sm text-rose-600">Could not load transactions: {txns.error.message}</p>}
      {txns.data && <TransactionList items={txns.data} />}

      {showUnparsed ? (
        <UnparsedList month={MONTH} onClose={() => setShowUnparsed(false)} />
      ) : (
        !!s?.unknown_emails && (
          <button onClick={() => setShowUnparsed(true)} className="w-full text-center text-sm text-amber-700 hover:underline dark:text-amber-400">
            {s.unknown_emails} email{s.unknown_emails === 1 ? "" : "s"} need a parser →
          </button>
        )
      )}
    </div>
  );
}
