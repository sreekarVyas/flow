import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Transaction } from "./api";
import { hasCategory, useCategories } from "./categories";
import { AccountFilter, type Filter } from "./components/AccountFilter";
import { CategoryBreakdown, type CatFilter } from "./components/CategoryBreakdown";
import { ManageCategories } from "./components/ManageCategories";
import { PeopleScreen } from "./components/PeopleScreen";
import { SummaryBar } from "./components/SummaryBar";
import { TagSheet } from "./components/TagSheet";
import { needsReview, TransactionList } from "./components/TransactionList";
import { UnparsedList } from "./components/UnparsedList";
import { monthLabel, relative } from "./format";

// Phase 1 shows November 2026 only. Override with ?month=YYYY-MM.
const MONTH = new URLSearchParams(location.search).get("month") ?? "2026-11";
const STAMP_MS = 1200;

export default function App() {
  const qc = useQueryClient();
  const [view, setView] = useState<"list" | "manage" | "people">("list");
  const [filter, setFilter] = useState<Filter>("all");
  const [review, setReview] = useState(false);
  const [catFilter, setCatFilter] = useState<CatFilter>(null);
  const [showUnparsed, setShowUnparsed] = useState(false);
  const [selected, setSelected] = useState<Transaction | null>(null);
  const [stamped, setStamped] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState("");
  const timers = useRef<number[]>([]);

  const accountType = filter === "all" ? undefined : filter;
  const { byId } = useCategories();
  const txns = useQuery({
    queryKey: ["transactions", MONTH, filter],
    queryFn: () => api.transactions(MONTH, accountType),
  });
  const summary = useQuery({ queryKey: ["summary", MONTH], queryFn: () => api.summary(MONTH), refetchInterval: 60_000 });
  const catSummary = useQuery({
    queryKey: ["categorySummary", MONTH, filter],
    queryFn: () => api.categorySummary(MONTH, accountType),
  });
  const sync = useMutation({ mutationFn: api.sync, onSettled: () => qc.invalidateQueries() });

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const markStamped = useCallback((id: number) => {
    setStamped((s) => new Set(s).add(id));
    timers.current.push(
      window.setTimeout(
        () =>
          setStamped((s) => {
            const n = new Set(s);
            n.delete(id);
            return n;
          }),
        STAMP_MS,
      ),
    );
  }, []);

  const confirm = useMutation({
    mutationFn: (t: Transaction) => api.patchTransaction(t.id, {}),
    onSuccess: (r) => {
      markStamped(r.transaction.id);
      // Show the stamp in place before the row refreshes or leaves the review list.
      qc.setQueryData<Transaction[]>(["transactions", MONTH, filter], (old) =>
        old?.map((t) => (t.id === r.transaction.id ? r.transaction : t)),
      );
      qc.invalidateQueries({ queryKey: ["categorySummary"] });
    },
  });

  const all = useMemo(() => txns.data ?? [], [txns.data]);
  const reviewCount = useMemo(() => all.filter(needsReview).length, [all]);
  const visible = useMemo(
    () =>
      all.filter((t) => {
        if (review && !needsReview(t) && !stamped.has(t.id)) return false;
        if (catFilter?.type === "untagged") return hasCategory(t.kind) && t.category_id == null;
        if (catFilter?.type === "cat") {
          const info = t.category_id != null ? byId.get(t.category_id) : undefined;
          return info?.cat.id === catFilter.id || info?.parent?.id === catFilter.id;
        }
        return true;
      }),
    [all, review, stamped, catFilter, byId],
  );

  const onSaved = useCallback(
    (id: number, updatedSimilar: number, noteSaved: boolean) => {
      if (!noteSaved) markStamped(id);
      setNotice(noteSaved ? "Note saved." : updatedSimilar > 0 ? `Saved. Also tagged ${updatedSimilar} similar ${updatedSimilar === 1 ? "payment" : "payments"}.` : "Saved.");
      timers.current.push(window.setTimeout(() => setNotice(""), 3000));
    },
    [markStamped],
  );

  const closeSheet = useCallback(() => setSelected(null), []);

  const overlays = (
    <>
      <p role="status" aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-[max(1rem,env(safe-area-inset-bottom))] z-30 flex justify-center px-4">
        {notice && <span className="rounded-full bg-ink px-4 py-2 text-sm font-medium text-paper shadow-lg">{notice}</span>}
      </p>
      {selected && <TagSheet key={selected.id} txn={selected} onClose={closeSheet} onSaved={onSaved} />}
    </>
  );

  if (view !== "list") {
    return (
      <div className="mx-auto max-w-2xl px-4 pb-16 pt-[max(1rem,env(safe-area-inset-top))]">
        {view === "manage" ? (
          <ManageCategories onBack={() => setView("list")} />
        ) : (
          <PeopleScreen onBack={() => setView("list")} onOpenTxn={setSelected} />
        )}
        {overlays}
      </div>
    );
  }

  const s = summary.data;
  const filterLabel =
    catFilter?.type === "untagged" ? "untagged spending" : catFilter?.type === "cat" ? catFilter.label : null;
  const emptyText = review
    ? "Nothing to review. Every payment has a kind and a confirmed category."
    : filterLabel
      ? `No ${filterLabel} payments for this account filter.`
      : "No transactions for this filter yet.";

  return (
    <div className="mx-auto max-w-2xl space-y-4 px-4 pb-16 pt-[max(1rem,env(safe-area-inset-top))]">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{monthLabel(MONTH)}</h1>
          <p className="text-sm text-ink-muted">{s?.last_poll_at ? `Synced ${relative(s.last_poll_at)}` : "Not synced yet"}</p>
        </div>
        <button
          onClick={() => sync.mutate()}
          disabled={sync.isPending}
          className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-50"
        >
          {sync.isPending ? "Syncing…" : "Sync now"}
        </button>
      </header>

      {sync.error && <p className="rounded-lg bg-warn-soft p-3 text-sm text-out">{sync.error.message}</p>}
      {sync.data && (
        <p className="text-sm text-ink-muted">
          Sync found {sync.data.fetched} new emails: {sync.data.txn} transactions, {sync.data.ignored} ignored,{" "}
          {sync.data.unknown} unknown.
        </p>
      )}

      {s && <SummaryBar summary={s} onPeople={() => setView("people")} />}

      <div className="flex flex-wrap items-center gap-2">
        <AccountFilter value={filter} onChange={setFilter} />
        <button
          type="button"
          aria-pressed={review}
          onClick={() => setReview((v) => !v)}
          className={
            "rounded-full border px-3 py-1 text-sm font-medium transition-colors " +
            (review
              ? "border-stamp bg-stamp text-on-stamp"
              : "border-dashed border-stamp/70 bg-surface text-stamp hover:bg-stamp-soft")
          }
        >
          To review{txns.data ? ` (${reviewCount})` : ""}
        </button>
      </div>

      {catSummary.data && <CategoryBreakdown data={catSummary.data} filter={catFilter} onFilter={setCatFilter} />}

      {filterLabel && (
        <div className="flex items-center justify-between rounded-lg bg-stamp-soft px-3 py-2 text-sm">
          <span>
            Showing <span className="font-semibold">{filterLabel}</span>
          </span>
          <button type="button" onClick={() => setCatFilter(null)} className="font-medium text-stamp hover:underline">
            Show all
          </button>
        </div>
      )}

      {txns.isPending && <p className="py-12 text-center text-sm text-ink-muted">Loading…</p>}
      {txns.error && <p className="text-sm text-out">Could not load transactions: {txns.error.message}</p>}
      {confirm.error && <p className="text-sm text-out">Could not confirm: {confirm.error.message}</p>}
      {txns.data && (
        <TransactionList
          items={visible}
          byId={byId}
          stampedIds={stamped}
          emptyText={emptyText}
          onSelect={setSelected}
          onConfirm={(t) => confirm.mutate(t)}
        />
      )}

      {showUnparsed ? (
        <UnparsedList month={MONTH} onClose={() => setShowUnparsed(false)} />
      ) : (
        !!s?.unknown_emails && (
          <button onClick={() => setShowUnparsed(true)} className="w-full text-center text-sm text-warn hover:underline">
            {s.unknown_emails} email{s.unknown_emails === 1 ? "" : "s"} need a parser
          </button>
        )
      )}

      <footer className="flex justify-center gap-6 pt-2">
        <button type="button" onClick={() => setView("people")} className="text-sm font-medium text-stamp hover:underline">
          People
        </button>
        <button type="button" onClick={() => setView("manage")} className="text-sm font-medium text-stamp hover:underline">
          Categories & rules
        </button>
      </footer>

      {overlays}
    </div>
  );
}
