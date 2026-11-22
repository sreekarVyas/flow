import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Split, type Transaction } from "../api";
import { money, payeeOf, shortDate } from "../format";
import { fromPaise, toPaise } from "../split";
import { NicknameField } from "./NicknameField";

function status(s: Split): { text: string; tone: string } {
  const out = Number(s.outstanding);
  if (out === 0) return { text: "Settled", tone: "text-in" };
  if (out > 0) return { text: `${money(out)} still owed`, tone: "text-ink" };
  return { text: `${money(-out)} overpaid, to return`, tone: "text-warn" };
}

const fieldClass =
  "rounded-lg border border-line bg-surface px-2 py-1 text-right text-base focus:border-stamp focus:outline-none";

function TagForm({ expense, repay, onDone }: { expense: Transaction; repay: Transaction; onDone: (t: Transaction) => void }) {
  const shared = expense.splits.filter((s) => s.paid_by === "me");
  const [nickname, setNickname] = useState(repay.person?.display_name ?? "");
  const [amountEdited, setAmountEdited] = useState(false);
  const nick = nickname.trim().replace(/\s+/g, " ").toLowerCase();
  const share = shared.find((s) => s.person.display_name.toLowerCase() === nick);
  const room = repay.kind === "settlement" ? toPaise(repay.unapplied) : toPaise(repay.amount);
  const target = share ? Math.max(0, toPaise(share.outstanding)) : toPaise(expense.my_share);
  const suggested = fromPaise(Math.min(room, target || room));
  const [amountText, setAmount] = useState("");
  const amount = amountEdited ? amountText : suggested;
  const [shareText, setShareText] = useState("");
  const qc = useQueryClient();

  const tag = useMutation({
    mutationFn: () =>
      api.addRepayment(expense.id, {
        settlement_txn_id: repay.id,
        amount,
        nickname: nickname.trim(),
        ...(!share && shareText.trim() ? { share: shareText } : {}),
      }),
    onSuccess: (t) => {
      qc.invalidateQueries();
      onDone(t);
    },
  });

  return (
    <div className="space-y-2 rounded-lg border border-stamp bg-surface p-3">
      <p className="text-sm">
        <span className="font-semibold">{money(repay.amount)}</span> from {payeeOf(repay)}, {shortDate(repay.ts)}
      </p>
      <NicknameField
        txn={repay}
        value={nickname}
        onChange={(v) => setNickname(v)}
        fallback={shared.length === 1 ? shared[0].person.display_name : undefined}
      />
      {nickname.trim() && (
        <p className="text-sm text-ink-muted">
          {share
            ? `Pays back ${share.person.display_name}'s share (${money(share.outstanding)} owed).`
            : `${nickname.trim()} has no share on this payment yet. Tagging makes the amount their share.`}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2">
          <span className="text-ink-muted">Amount</span>
          <input type="number" inputMode="decimal" min="0" step="0.01" value={amount} onChange={(e) => {
              setAmountEdited(true);
              setAmount(e.target.value);
            }} className={`${fieldClass} w-28`} />
        </label>
        {nickname.trim() && !share && (
          <label className="flex items-center gap-2">
            <span className="text-ink-muted">{nickname.trim()}'s share</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={shareText}
              placeholder="same"
              onChange={(e) => setShareText(e.target.value)}
              className={`${fieldClass} w-28`}
            />
          </label>
        )}
      </div>
      {tag.error && <p className="text-sm text-out">{tag.error.message}</p>}
      <div className="flex gap-3">
        <button
          type="button"
          disabled={!nickname.trim() || !(Number(amount) > 0) || tag.isPending}
          onClick={() => tag.mutate()}
          className="rounded-lg bg-stamp px-4 py-1.5 text-sm font-semibold text-on-stamp disabled:opacity-50"
        >
          {tag.isPending ? "Tagging…" : "Tag repayment"}
        </button>
        <button type="button" className="text-sm text-ink-muted hover:underline" onClick={() => onDone(expense)}>
          Cancel
        </button>
      </div>
    </div>
  );
}

export function RepaymentsSection({ expense, onUpdated }: { expense: Transaction; onUpdated: (t: Transaction) => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<Transaction | null>(null);
  const shared = expense.splits.filter((s) => s.paid_by === "me");

  const cands = useQuery({
    queryKey: ["repaymentCandidates", expense.id, q.trim()],
    queryFn: () => api.repaymentCandidates(expense.id, q.trim() || undefined),
    enabled: open,
  });

  const remove = useMutation({
    mutationFn: async (linkId: number) => {
      await api.deleteLink(linkId);
      return api.transaction(expense.id);
    },
    onSuccess: (t) => {
      qc.invalidateQueries();
      onUpdated(t);
    },
  });

  const done = (t: Transaction) => {
    setPicked(null);
    setOpen(false);
    setQ("");
    onUpdated(t);
  };

  return (
    <section aria-labelledby="repay-heading" className="space-y-2">
      <h3 id="repay-heading" className="text-sm font-medium text-ink-muted">
        Paid back
      </h3>

      {shared.length > 0 && (
        <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
          {shared.map((s) => {
            const st = status(s);
            return (
              <li key={s.id} className="px-3 py-2 text-sm">
                <div className="flex items-baseline justify-between gap-3">
                  <span>
                    <span className="font-semibold">{s.person.display_name}</span>
                    <span className="text-ink-muted"> owes {money(s.share_amount)}</span>
                  </span>
                  <span className={`font-semibold ${st.tone}`}>{st.text}</span>
                </div>
                {s.links.map((l) => (
                  <div key={l.id} className="mt-1 flex items-center justify-between gap-3 text-ink-muted">
                    <span className="min-w-0 truncate">
                      {l.settles ? "+" : "−"}
                      {money(l.amount)} {l.settles ? "from" : "returned to"} {payeeOf(l.settlement)}, {shortDate(l.settlement.ts)}
                    </span>
                    <button
                      type="button"
                      onClick={() => remove.mutate(l.id)}
                      disabled={remove.isPending}
                      className="shrink-0 font-medium text-stamp hover:underline"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </li>
            );
          })}
        </ul>
      )}
      {remove.error && <p className="text-sm text-out">{remove.error.message}</p>}

      {picked ? (
        <TagForm expense={expense} repay={picked} onDone={done} />
      ) : open ? (
        <div className="space-y-2">
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search money you received"
            aria-label="Search repayments"
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-base placeholder:text-ink-muted focus:border-stamp focus:outline-none"
          />
          {cands.isPending && <p className="text-sm text-ink-muted">Loading…</p>}
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {cands.data?.items
              .filter((c) => Number(c.linked_amount) === 0)
              .map(({ transaction: r }) => (
                <li key={r.id}>
                  <button type="button" onClick={() => setPicked(r)} className="flex w-full items-start justify-between gap-3 px-3 py-2 text-left hover:bg-stamp-soft">
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{payeeOf(r)}</span>
                      <span className="block text-xs text-ink-muted">
                        {shortDate(r.ts)}
                        {r.kind === "settlement" && r.person
                          ? `, repayment from ${r.person.display_name}, ${money(r.unapplied)} not tagged`
                          : ""}
                      </span>
                    </span>
                    <span className={`shrink-0 font-semibold ${r.direction === "credit" ? "text-in" : "text-out"}`}>
                      {r.direction === "credit" ? "+" : "−"}
                      {money(r.amount)}
                    </span>
                  </button>
                </li>
              ))}
          </ul>
          {cands.data && cands.data.items.every((c) => Number(c.linked_amount) > 0) && (
            <p className="text-sm text-ink-muted">No money received around this date. Search by name to find it.</p>
          )}
          <button type="button" className="text-sm text-ink-muted hover:underline" onClick={() => setOpen(false)}>
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="w-full rounded-lg border border-dashed border-stamp/70 py-2 text-sm font-medium text-stamp hover:bg-stamp-soft"
        >
          Tag a repayment
        </button>
      )}
    </section>
  );
}
