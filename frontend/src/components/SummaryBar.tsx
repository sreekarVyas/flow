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

export function SummaryBar({ summary }: { summary: Summary }) {
  const { bank, credit_card: card } = summary;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Tile label="Bank debits" value={money(bank.debit_total)} sub={`${bank.debit_count} payments, ${money(bank.transfer_total)} transfers`} />
      <Tile label="Bank credits" value={money(bank.credit_total)} sub={`${bank.credit_count} payments`} />
      <Tile label="Card spend" value={money(card.debit_total)} sub={`${card.debit_count} payments`} />
      <Tile label="Card credits" value={money(card.credit_total)} sub={`${card.credit_count} payments`} />
    </div>
  );
}
