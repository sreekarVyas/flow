import type { Summary } from "../api";
import { money } from "../format";

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="text-sm font-medium text-ink-muted">{label}</div>
      <div className="mt-0.5 text-lg font-semibold">{value}</div>
      <div className="text-xs text-ink-muted">{sub}</div>
    </div>
  );
}

export function SummaryBar({ summary, onPeople }: { summary: Summary; onPeople: () => void }) {
  const { bank, credit_card: card, shared } = summary;
  const mySpend = Number(bank.my_share_total) + Number(card.my_share_total);
  const paid = Number(bank.expense_total) + Number(card.expense_total);
  const others = Number(shared.others_share);
  const owed = Number(shared.owed_to_me);

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-5 gap-2">
        <div className="col-span-3 rounded-xl bg-ink p-3 text-paper">
          <div className="text-sm font-medium opacity-80">My spend</div>
          <div className="mt-0.5 text-2xl font-bold">{money(mySpend)}</div>
          <div className="text-xs opacity-80">
            {others > 0 ? `${money(paid)} paid, ${money(others)} is friends' share` : "Your share of every expense"}
          </div>
        </div>
        <button
          type="button"
          onClick={onPeople}
          className="col-span-2 rounded-xl border border-line bg-surface p-3 text-left hover:border-stamp/60"
        >
          <span className="block text-sm font-medium text-ink-muted">Owed to you</span>
          <span className={`mt-0.5 block text-lg font-semibold ${owed > 0 ? "text-in" : ""}`}>{money(owed)}</span>
          <span className="block text-xs text-ink-muted">
            {shared.people_owing > 0
              ? `by ${shared.people_owing} ${shared.people_owing === 1 ? "person" : "people"}`
              : Number(shared.i_owe) > 0
                ? `you owe ${money(shared.i_owe)}`
                : "Nobody owes you"}
          </span>
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Tile label="Bank debits" value={money(bank.debit_total)} sub={`${bank.debit_count} payments, ${money(bank.transfer_total)} transfers`} />
        <Tile label="Bank credits" value={money(bank.credit_total)} sub={`${bank.credit_count} payments`} />
        <Tile label="Card spend" value={money(card.debit_total)} sub={`${card.debit_count} payments`} />
        <Tile label="Card credits" value={money(card.credit_total)} sub={`${card.credit_count} payments`} />
      </div>
    </div>
  );
}
