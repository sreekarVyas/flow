import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Person, type Transaction } from "../api";
import { dayKey, dayLabel, money } from "../format";

const fieldClass =
  "rounded-lg border border-line bg-surface px-2.5 py-1.5 text-base placeholder:text-ink-muted focus:border-stamp focus:outline-none";
const linkClass = "text-sm font-medium text-stamp hover:underline disabled:opacity-50";

function shareStatus(outstanding: string) {
  const n = Number(outstanding);
  if (n === 0) return "settled";
  return n > 0 ? `${money(n)} owed` : `${money(-n)} overpaid`;
}

const shareTone = (outstanding: string) =>
  Number(outstanding) === 0 ? "text-in" : Number(outstanding) < 0 ? "text-warn" : "text-ink-muted";

function BalanceText({ net, big }: { net: string; big?: boolean }) {
  const n = Number(net);
  const size = big ? "text-2xl" : "text-base";
  if (n === 0) return <span className={`${size} font-semibold text-ink-muted`}>Settled</span>;
  return (
    <span className="text-right">
      <span className={`block ${size} font-semibold ${n > 0 ? "text-in" : "text-out"}`}>{money(Math.abs(n))}</span>
      <span className="block text-xs text-ink-muted">{n > 0 ? "owes you" : "you owe"}</span>
    </span>
  );
}

function AddPerson() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const add = useMutation({
    mutationFn: () => api.createPerson(name),
    onSuccess: () => {
      setName("");
      qc.invalidateQueries({ queryKey: ["people"] });
    },
  });
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) add.mutate();
      }}
    >
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Add a person"
        aria-label="New person's name"
        maxLength={100}
        className={`${fieldClass} min-w-0 flex-1`}
      />
      <button type="submit" disabled={!name.trim() || add.isPending} className="rounded-lg bg-ink px-4 text-sm font-medium text-paper disabled:opacity-50">
        Add
      </button>
      {add.error && <p className="text-sm text-out">{add.error.message}</p>}
    </form>
  );
}

function PersonPage({
  id,
  onBack,
  onOpenTxn,
  onOpen,
}: {
  id: number;
  onBack: () => void;
  onOpenTxn: (t: Transaction) => void;
  onOpen: (id: number) => void;
}) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["person", id], queryFn: () => api.person(id) });
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState("");
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["people"] });
    qc.invalidateQueries({ queryKey: ["person", id] });
    qc.invalidateQueries({ queryKey: ["transactions"] });
  };
  const [mergeInto, setMergeInto] = useState<Person | null>(null);
  const rename = useMutation({
    mutationFn: () => api.renamePerson(id, name),
    onSuccess: () => {
      invalidate();
      setRenaming(false);
    },
    // The nickname is taken: that is the same person under another nickname. Offer to merge.
    onError: async () => {
      const key = name.trim().replace(/\s+/g, " ").toLowerCase();
      const found = (await api.people(name.trim())).find((x) => x.display_name.toLowerCase() === key && x.id !== id);
      setMergeInto(found ?? null);
    },
  });
  const merge = useMutation({
    mutationFn: (into: Person) => api.mergePeople(id, into.id),
    onSuccess: (merged) => {
      qc.invalidateQueries();
      onOpen(merged.id);
    },
  });
  const forget = useMutation({ mutationFn: api.forgetSource, onSuccess: invalidate });
  const del = useMutation({
    mutationFn: () => api.deletePerson(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["people"] });
      onBack();
    },
  });
  const p = q.data;

  return (
    <div className="space-y-4">
      <button type="button" onClick={onBack} className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium">
        All people
      </button>
      {q.isPending && <p className="text-sm text-ink-muted">Loading…</p>}
      {q.error && <p className="text-sm text-out">Could not load this person: {q.error.message}</p>}
      {p && (
        <>
          <header className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              {renaming ? (
                <form
                  className="flex flex-wrap items-center gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (name.trim()) rename.mutate();
                  }}
                >
                  <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Name" maxLength={100} className={`${fieldClass} min-w-0`} autoFocus />
                  <button type="submit" className={linkClass} disabled={rename.isPending || !name.trim()}>
                    Save
                  </button>
                  <button type="button" className="text-sm text-ink-muted hover:underline" onClick={() => setRenaming(false)}>
                    Cancel
                  </button>
                  {mergeInto ? (
                    <div className="w-full space-y-2 rounded-lg bg-warn-soft px-3 py-2 text-sm">
                      <p>
                        {mergeInto.display_name} already exists. If they are the same person, merge {p.display_name} into{" "}
                        {mergeInto.display_name}: shares, repayments and UPI IDs move over.
                      </p>
                      <button
                        type="button"
                        onClick={() => merge.mutate(mergeInto)}
                        disabled={merge.isPending}
                        className="rounded-lg bg-ink px-3 py-1.5 font-medium text-paper disabled:opacity-50"
                      >
                        Merge into {mergeInto.display_name}
                      </button>
                      {merge.error && <p className="text-out">{merge.error.message}</p>}
                    </div>
                  ) : (
                    rename.error && <p className="w-full text-sm text-out">{rename.error.message}</p>
                  )}
                </form>
              ) : (
                <>
                  <h1 className="truncate text-2xl font-bold">{p.display_name}</h1>
                  <button
                    type="button"
                    className={linkClass}
                    onClick={() => {
                      setName(p.display_name);
                      setMergeInto(null);
                      setRenaming(true);
                    }}
                  >
                    Rename
                  </button>
                </>
              )}
            </div>
            <BalanceText net={p.net} big />
          </header>

          <section aria-labelledby="shares-heading" className="rounded-xl border border-line bg-surface">
            <h2 id="shares-heading" className="border-b border-line px-4 py-2.5 font-semibold">
              Shared payments
            </h2>
            {p.history.length ? (
              <ul className="divide-y divide-line">
                {p.history.map((h) => {
                  const t = h.transaction;
                  return (
                    <li key={h.split_id}>
                      <button
                        type="button"
                        onClick={() => onOpenTxn(t)}
                        className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left hover:bg-surface-2/60"
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-medium">{t.counterparty_name || t.vpa_or_merchant || "Unknown payee"}</span>
                          <span className="block text-xs text-ink-muted">
                            {dayLabel(dayKey(t.ts))}, total {money(t.amount)}
                          </span>
                        </span>
                        <span className="shrink-0 text-right">
                          <span className="block font-semibold">{money(h.share_amount)}</span>
                          <span className={`block text-xs ${shareTone(h.outstanding)}`}>{shareStatus(h.outstanding)}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <div className="space-y-2 px-4 py-3 text-sm text-ink-muted">
                <p>No shared payments yet. Open a payment and add {p.display_name} under Split with people.</p>
                <button type="button" className="font-medium text-out hover:underline" onClick={() => del.mutate()} disabled={del.isPending}>
                  Delete {p.display_name}
                </button>
                {del.error && <p className="text-out">{del.error.message}</p>}
              </div>
            )}
          </section>

          {p.sources.length > 0 && (
            <section aria-labelledby="sources-heading" className="rounded-xl border border-line bg-surface">
              <h2 id="sources-heading" className="border-b border-line px-4 py-2.5 font-semibold">
                UPI IDs nicknamed {p.display_name}
              </h2>
              <ul className="divide-y divide-line">
                {p.sources.map((src) => (
                  <li key={src.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{src.printed_name ?? "No name"}</span>
                      {src.vpa && <span className="block truncate text-xs text-ink-muted">{src.vpa}</span>}
                    </span>
                    <button
                      type="button"
                      onClick={() => forget.mutate(src.id)}
                      disabled={forget.isPending}
                      className="shrink-0 font-medium text-stamp hover:underline"
                    >
                      Forget
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section aria-labelledby="repays-heading" className="rounded-xl border border-line bg-surface">
            <h2 id="repays-heading" className="border-b border-line px-4 py-2.5 font-semibold">
              Repayments
            </h2>
            {p.repayments.length ? (
              <ul className="divide-y divide-line">
                {p.repayments.map((t) => (
                  <li key={t.id}>
                    <button
                      type="button"
                      onClick={() => onOpenTxn(t)}
                      className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left hover:bg-surface-2/60"
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium">{t.counterparty_name || t.vpa_or_merchant || "Unknown payee"}</span>
                        <span className="block text-xs text-ink-muted">
                          {dayLabel(dayKey(t.ts))}
                          {Number(t.unapplied) > 0
                            ? `, ${money(t.unapplied)} not tagged to a payment`
                            : `, tagged to ${t.links_out.length} ${t.links_out.length === 1 ? "payment" : "payments"}`}
                        </span>
                      </span>
                      <span className={`shrink-0 font-semibold ${t.direction === "credit" ? "text-in" : "text-out"}`}>
                        {t.direction === "credit" ? "+" : "−"}
                        {money(t.amount)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-4 py-3 text-sm text-ink-muted">
                None yet. Open money you received, choose Settlement, give the sender the nickname {p.display_name}, and tag the payments it covers.
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}

export function PeopleScreen({ onBack, onOpenTxn }: { onBack: () => void; onOpenTxn: (t: Transaction) => void }) {
  const [openId, setOpenId] = useState<number | null>(null);
  const q = useQuery({ queryKey: ["people", ""], queryFn: () => api.people() });

  if (openId != null)
    return <PersonPage key={openId} id={openId} onBack={() => setOpenId(null)} onOpenTxn={onOpenTxn} onOpen={setOpenId} />;

  const people: Person[] = q.data ?? [];
  const owedToMe = people.reduce((s, p) => s + Math.max(0, Number(p.net)), 0);
  const owing = people.filter((p) => Number(p.net) > 0).length;

  return (
    <div className="space-y-4">
      <header className="flex items-center gap-3">
        <button type="button" onClick={onBack} className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium">
          Back
        </button>
        <h1 className="text-2xl font-bold">People</h1>
      </header>

      {people.length > 0 && (
        <p className="flex items-baseline justify-between rounded-xl border border-line bg-surface px-4 py-3">
          <span className="text-ink-muted">
            Owed to you by {owing} {owing === 1 ? "person" : "people"}
          </span>
          <span className="text-xl font-semibold text-in">{money(owedToMe)}</span>
        </p>
      )}

      {q.isPending && <p className="text-sm text-ink-muted">Loading…</p>}
      {q.error && <p className="text-sm text-out">Could not load people: {q.error.message}</p>}
      {q.data && people.length === 0 && (
        <p className="py-6 text-center text-sm text-ink-muted">
          No people yet. Open a payment and use Split with people, or add someone below.
        </p>
      )}
      {people.length > 0 && (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
          {people.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => setOpenId(p.id)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-surface-2/60"
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">{p.display_name}</span>
                  <span className="block text-xs text-ink-muted">
                    {p.shares} shared {p.shares === 1 ? "payment" : "payments"}
                  </span>
                </span>
                <BalanceText net={p.net} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <AddPerson />
    </div>
  );
}
