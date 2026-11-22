import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { api, type SettleCandidate, type SettlementRequest, type Transaction } from "../api";
import { money, payeeOf, shortDate } from "../format";
import { fromPaise, toPaise } from "../split";
import { NicknameField } from "./NicknameField";

export interface SettleDraft {
  nickname: string; // of this transaction's payment source; the nickname is the person
  links: Record<number, { amount: string; share: string }>; // by earlier payment id
  dirty: boolean;
}

export function draftFromSettlement(t: Transaction): SettleDraft {
  const links: SettleDraft["links"] = {};
  for (const l of t.links_out) links[l.split.transaction.id] = { amount: l.amount, share: "" };
  return { nickname: t.person?.display_name ?? "", links, dirty: false };
}

export function settleRequest(d: SettleDraft): SettlementRequest {
  return {
    nickname: d.nickname.trim(),
    links: Object.entries(d.links).map(([id, l]) => ({
      transaction_id: Number(id),
      amount: l.amount,
      ...(l.share.trim() ? { share: l.share } : {}),
    })),
  };
}

/** Returns a message when the draft cannot be saved, else null. */
export function settleProblem(t: Transaction, d: SettleDraft): string | null {
  if (!d.nickname.trim()) return "Give this payment source a nickname.";
  const amounts = Object.values(d.links).map((l) => toPaise(l.amount || "0"));
  if (amounts.some((a) => !(a > 0))) return "Enter an amount for each tagged payment.";
  if (amounts.reduce((a, b) => a + b, 0) > toPaise(t.amount)) return "Tagged amounts add up to more than this repayment.";
  return null;
}

/** What the share looks like after this link, in words. */
function outcome(t: Transaction, c: SettleCandidate, amountPaise: number, sharePaise: number | null, who: string): string {
  const credit = t.direction === "credit";
  if (!c.share) {
    if (!credit) return `${who} has no share on this payment.`;
    if (sharePaise == null || sharePaise === amountPaise) {
      return amountPaise === toPaise(c.transaction.my_share)
        ? "Cancels out the whole payment."
        : `Makes ${money(fromPaise(amountPaise))} of it ${who}'s share, settled.`;
    }
    const left = sharePaise - amountPaise;
    return left > 0 ? `${who}'s share ${money(fromPaise(sharePaise))}, ${money(fromPaise(left))} still owed.` : `Cancels out ${who}'s share.`;
  }
  // The share's outstanding already includes this repayment's current link; take it out first.
  const linked = toPaise(c.linked_amount);
  const base = toPaise(c.share.outstanding) + (credit ? linked : -linked);
  const after = credit ? base - amountPaise : base + amountPaise;
  if (after === 0) return credit ? `Cancels out ${who}'s share.` : "Balances out the overpayment.";
  if (after > 0) return `${money(fromPaise(after))} still owed.`;
  return `${money(fromPaise(-after))} more than ${who} owed.`;
}

export function SettlementEditor({ txn, draft, onChange }: { txn: Transaction; draft: SettleDraft; onChange: (d: SettleDraft) => void }) {
  const [q, setQ] = useState("");
  const credit = txn.direction === "credit";
  const nick = useDeferredValue(draft.nickname.trim());
  const cands = useQuery({
    queryKey: ["settleCandidates", txn.id, nick.toLowerCase(), q.trim()],
    queryFn: () => api.settleCandidates(txn.id, nick || undefined, q.trim() || undefined),
    enabled: nick.length > 0,
  });

  const set = (patch: Partial<SettleDraft>) => onChange({ ...draft, ...patch, dirty: true });
  const who = draft.nickname.trim() || "they";
  const totalPaise = toPaise(txn.amount);
  const taggedPaise = Object.values(draft.links).reduce((s, l) => s + toPaise(l.amount || "0"), 0);

  const toggle = (c: SettleCandidate) => {
    const id = c.transaction.id;
    const next = { ...draft.links };
    if (next[id]) {
      delete next[id];
    } else {
      const remaining = Math.max(0, totalPaise - taggedPaise);
      let want = remaining;
      if (c.share) {
        const linked = toPaise(c.linked_amount);
        const base = toPaise(c.share.outstanding) + (credit ? linked : -linked);
        if (credit && base > 0) want = Math.min(remaining, base);
        if (!credit && base < 0) want = Math.min(remaining, -base);
      } else {
        want = Math.min(remaining, toPaise(c.transaction.my_share));
      }
      next[id] = { amount: fromPaise(want), share: "" };
    }
    set({ links: next });
  };

  const setLink = (id: number, patch: Partial<{ amount: string; share: string }>) =>
    set({ links: { ...draft.links, [id]: { ...draft.links[id], ...patch } } });

  return (
    <div className="space-y-4">
      <NicknameField
        txn={txn}
        value={draft.nickname}
        onChange={(nickname, edited) => onChange({ ...draft, nickname, dirty: draft.dirty || edited })}
      />

      {draft.nickname.trim() && (
        <section aria-labelledby="settle-links" className="space-y-2">
          <div className="flex items-baseline justify-between gap-2">
            <h3 id="settle-links" className="text-sm font-medium text-ink-muted">
              Tag to earlier payments
            </h3>
            <span className="text-sm">
              {money(fromPaise(taggedPaise))} of {money(txn.amount)}
            </span>
          </div>
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search older payments"
            aria-label="Search payments to tag"
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-base placeholder:text-ink-muted focus:border-stamp focus:outline-none"
          />
          {cands.isPending && <p className="text-sm text-ink-muted">Loading payments…</p>}
          {cands.error && <p className="text-sm text-out">Could not load payments: {cands.error.message}</p>}
          <ul className="space-y-1.5">
            {cands.data?.items.map((c) => {
              const e = c.transaction;
              const sel = draft.links[e.id];
              const amountPaise = sel ? toPaise(sel.amount || "0") : 0;
              const sharePaise = sel?.share.trim() ? toPaise(sel.share) : null;
              return (
                <li
                  key={e.id}
                  className={`rounded-lg border px-3 py-2 ${sel ? "border-stamp bg-surface" : "border-line bg-surface"}`}
                >
                  <button type="button" onClick={() => toggle(c)} aria-pressed={!!sel} className="flex w-full items-start gap-3 text-left">
                    <span
                      aria-hidden
                      className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border text-xs ${
                        sel ? "border-stamp bg-stamp text-on-stamp" : "border-line"
                      }`}
                    >
                      {sel ? "✓" : ""}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{payeeOf(e)}</span>
                      <span className="block text-xs text-ink-muted">
                        {shortDate(e.ts)}
                        {c.share
                          ? `, ${who}'s share ${money(c.share.share_amount)}, ${
                              Number(c.share.outstanding) > 0
                                ? `${money(c.share.outstanding)} owed`
                                : Number(c.share.outstanding) < 0
                                  ? `${money(-Number(c.share.outstanding))} overpaid`
                                  : "settled"
                            }`
                          : e.splits.length
                            ? `, split, your share ${money(e.my_share)}`
                            : ", not split"}
                      </span>
                    </span>
                    <span className="shrink-0 font-semibold">{money(e.amount)}</span>
                  </button>
                  {sel && (
                    <div className="mt-2 space-y-1.5 border-t border-line pt-2">
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <label className="flex items-center gap-2">
                          <span className="text-ink-muted">Amount</span>
                          <input
                            type="number"
                            inputMode="decimal"
                            min="0"
                            step="0.01"
                            value={sel.amount}
                            onChange={(ev) => setLink(e.id, { amount: ev.target.value })}
                            className="w-28 rounded-lg border border-line bg-surface px-2 py-1 text-right text-base focus:border-stamp focus:outline-none"
                          />
                        </label>
                        {!c.share && credit && (
                          <label className="flex items-center gap-2">
                            <span className="text-ink-muted">{who}'s share</span>
                            <input
                              type="number"
                              inputMode="decimal"
                              min="0"
                              step="0.01"
                              value={sel.share}
                              placeholder="same"
                              onChange={(ev) => setLink(e.id, { share: ev.target.value })}
                              className="w-28 rounded-lg border border-line bg-surface px-2 py-1 text-right text-base focus:border-stamp focus:outline-none"
                            />
                          </label>
                        )}
                      </div>
                      <p className="text-sm font-medium text-stamp">{outcome(txn, c, amountPaise, sharePaise, who)}</p>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {cands.data && cands.data.items.length === 0 && (
            <p className="text-sm text-ink-muted">No expenses found. Search by payee name to find older ones.</p>
          )}
          {taggedPaise < totalPaise && (
            <p className="text-sm text-ink-muted">
              {money(fromPaise(totalPaise - taggedPaise))} is not tagged to a payment. It still counts in {who}'s balance.
            </p>
          )}
        </section>
      )}
    </div>
  );
}
