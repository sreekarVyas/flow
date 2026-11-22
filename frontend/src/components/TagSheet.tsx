import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Category, type Kind, type Transaction } from "../api";
import { hasCategory, KIND_LABEL, pushRecent, readRecent, useCategories } from "../categories";
import { dayLabel, dayKey, money, timeLabel } from "../format";

const KINDS: Kind[] = ["expense", "transfer", "settlement", "income", "refund"];

function Pick({
  selected,
  onClick,
  children,
  strong,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
  strong?: boolean;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={
        "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm transition-colors " +
        (strong ? "font-semibold " : "") +
        (selected
          ? "border-stamp bg-stamp text-on-stamp"
          : "border-line bg-surface text-ink hover:border-stamp/60 hover:bg-stamp-soft")
      }
    >
      {children}
    </button>
  );
}

export function TagSheet({
  txn,
  onClose,
  onSaved,
}: {
  txn: Transaction;
  onClose: () => void;
  onSaved: (id: number, updatedSimilar: number) => void;
}) {
  const qc = useQueryClient();
  const { tree, byId } = useCategories();
  const [kind, setKind] = useState<Kind | null>(txn.kind ?? (txn.direction === "debit" ? "expense" : null));
  const [categoryId, setCategoryId] = useState<number | null>(txn.category_id);
  const [search, setSearch] = useState("");
  const [applySimilar, setApplySimilar] = useState(true);
  const sheetRef = useRef<HTMLDivElement>(null);

  const similar = useQuery({ queryKey: ["similar", txn.id], queryFn: () => api.similar(txn.id) });

  const save = useMutation({
    mutationFn: () =>
      api.patchTransaction(txn.id, {
        kind,
        category_id: hasCategory(kind) ? categoryId : null,
        apply_to_similar: applySimilar && (similar.data?.count ?? 0) > 0,
      }),
    onSuccess: (r) => {
      if (hasCategory(kind) && categoryId != null) pushRecent(categoryId);
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
      qc.invalidateQueries({ queryKey: ["categorySummary"] });
      qc.invalidateQueries({ queryKey: ["rules"] });
      onSaved(txn.id, r.updated_similar);
      onClose();
    },
  });

  // Esc closes; lock page scroll while open; move focus into the sheet.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sheetRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const visible = useMemo(
    () =>
      tree
        .filter((p) => !p.archived)
        .map((p) => ({ ...p, children: p.children.filter((c) => !c.archived) })),
    [tree],
  );

  const matches = useMemo(() => {
    const s = search.trim().toLowerCase();
    if (!s) return null;
    const out: Category[] = [];
    for (const p of visible) {
      if (p.name.toLowerCase().includes(s)) out.push(p);
      for (const c of p.children) if (c.name.toLowerCase().includes(s) || p.name.toLowerCase().includes(s)) out.push(c);
    }
    return out;
  }, [search, visible]);

  const recent = useMemo(
    () => readRecent().filter((id) => byId.has(id) && !byId.get(id)!.cat.archived),
    [byId], // recompute when categories load

  );

  const payee = txn.counterparty_name || txn.vpa_or_merchant || "Unknown payee";
  const debit = txn.direction === "debit";
  const needsCategory = hasCategory(kind);
  const sim = similar.data;
  const selected = categoryId != null ? byId.get(categoryId) : undefined;
  const canSave = kind != null && !save.isPending;

  const chip = (id: number) => {
    const info = byId.get(id);
    if (!info) return null;
    return (
      <Pick key={id} selected={categoryId === id} onClick={() => setCategoryId(id)}>
        <span aria-hidden>{info.icon}</span>
        {info.label}
      </Pick>
    );
  };

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center" role="presentation">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 bg-ink/40 backdrop-blur-[1px]"
        tabIndex={-1}
      />
      <div
        ref={sheetRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tag-sheet-title"
        className="animate-sheet relative flex h-[88dvh] w-full max-w-2xl flex-col rounded-t-2xl bg-paper shadow-2xl outline-none"
      >
        <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-line" aria-hidden />

        <header className="flex items-start justify-between gap-3 px-4 pb-3 pt-2">
          <div className="min-w-0">
            <h2 id="tag-sheet-title" className="truncate text-lg font-semibold">
              {payee}
            </h2>
            <p className="text-sm text-ink-muted">
              {txn.account.name}, {dayLabel(dayKey(txn.ts))} at {timeLabel(txn.ts)}
            </p>
          </div>
          <div className={`shrink-0 text-lg font-semibold ${debit ? "text-out" : "text-in"}`}>
            {debit ? "−" : "+"}
            {money(txn.amount)}
          </div>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto overscroll-contain px-4 pb-4">
          <fieldset>
            <legend className="mb-2 text-sm font-medium text-ink-muted">What is this?</legend>
            <div className="flex flex-wrap gap-1.5">
              {KINDS.map((k) => (
                <Pick key={k} selected={kind === k} onClick={() => setKind(k)}>
                  {KIND_LABEL[k]}
                </Pick>
              ))}
            </div>
            {!needsCategory && kind && (
              <p className="mt-2 text-sm text-ink-muted">
                {kind === "transfer" && "Moves money between your own accounts. Not counted as spending."}
                {kind === "settlement" && "Money paid back between you and a friend. Not counted as spending."}
                {kind === "income" && "Money you earned. Not counted as spending."}
              </p>
            )}
          </fieldset>

          {needsCategory && (
            <section aria-labelledby="cat-heading" className="space-y-4">
              <div className="flex items-baseline justify-between gap-2">
                <h3 id="cat-heading" className="text-sm font-medium text-ink-muted">
                  Category
                </h3>
                {selected && (
                  <button type="button" onClick={() => setCategoryId(null)} className="text-sm text-stamp hover:underline">
                    Clear
                  </button>
                )}
              </div>
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search categories"
                aria-label="Search categories"
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-base placeholder:text-ink-muted focus:border-stamp focus:outline-none"
              />

              {matches ? (
                matches.length ? (
                  <div className="flex flex-wrap gap-1.5">{matches.map((c) => chip(c.id))}</div>
                ) : (
                  <p className="text-sm text-ink-muted">No category matches “{search}”. Add one in Categories & rules.</p>
                )
              ) : (
                <>
                  {recent.length > 0 && (
                    <div>
                      <h4 className="mb-1.5 text-sm text-ink-muted">Recent</h4>
                      <div className="flex flex-wrap gap-1.5">{recent.map(chip)}</div>
                    </div>
                  )}
                  {visible.map((p) => (
                    <div key={p.id}>
                      <button
                        type="button"
                        aria-pressed={categoryId === p.id}
                        onClick={() => setCategoryId(p.id)}
                        className={
                          "mb-1.5 inline-flex items-center gap-1.5 rounded-md px-1 text-sm font-semibold " +
                          (categoryId === p.id ? "bg-stamp text-on-stamp" : "text-ink hover:text-stamp")
                        }
                      >
                        <span aria-hidden>{p.icon}</span>
                        {p.name}
                      </button>
                      {p.children.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">{p.children.map((c) => chip(c.id))}</div>
                      )}
                    </div>
                  ))}
                </>
              )}
            </section>
          )}
        </div>

        <footer className="space-y-3 border-t border-line bg-surface px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3">
          {sim && sim.count > 0 && (
            <label className="flex cursor-pointer items-center justify-between gap-3 text-sm">
              <span>
                Also tag {sim.count} other {sim.count === 1 ? "payment" : "payments"} {debit ? "to" : "from"}{" "}
                <span className="font-semibold">{sim.payee}</span>
              </span>
              <input
                type="checkbox"
                role="switch"
                checked={applySimilar}
                onChange={(e) => setApplySimilar(e.target.checked)}
                className="peer sr-only"
              />
              <span
                aria-hidden
                className="relative h-6 w-10 shrink-0 rounded-full bg-line transition-colors peer-checked:bg-stamp peer-focus-visible:outline-2 peer-focus-visible:outline-stamp after:absolute after:left-0.5 after:top-0.5 after:h-5 after:w-5 after:rounded-full after:bg-surface after:shadow after:transition-transform peer-checked:after:translate-x-4"
              />
            </label>
          )}
          {sim?.learns_rule && kind && (
            <p className="text-xs text-ink-muted">
              {needsCategory && selected
                ? `Future payments to ${sim.payee} get ${selected.icon} ${selected.label}.`
                : needsCategory
                  ? `Pick a category and future payments to ${sim.payee} get it too.`
                  : `Future payments to ${sim.payee} are marked ${KIND_LABEL[kind].toLowerCase()}.`}
            </p>
          )}
          {save.error && <p className="text-sm text-out">Could not save: {save.error.message}</p>}
          <button
            type="button"
            disabled={!canSave}
            onClick={() => save.mutate()}
            className="w-full rounded-xl bg-stamp py-3 text-base font-semibold text-on-stamp disabled:opacity-50"
          >
            {save.isPending
              ? "Saving…"
              : !kind
                ? "Choose what this is"
                : needsCategory && !selected
                  ? "Save without a category"
                  : "Save"}
          </button>
        </footer>
      </div>
    </div>
  );
}
