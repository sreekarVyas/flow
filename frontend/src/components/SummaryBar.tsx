import type { Summary } from "../api";
import { money } from "../format";

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-xl bg-white p-3 shadow-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
      <div className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
      <div className="text-xs text-slate-500 dark:text-slate-400">{sub}</div>
    </div>
  );
}

export function SummaryBar({ summary }: { summary: Summary }) {
  const { bank, credit_card: card } = summary;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Tile label="Bank debits" value={money(bank.debit_total)} sub={`${bank.debit_count} txns · ${money(bank.transfer_total)} transfers`} />
      <Tile label="Bank credits" value={money(bank.credit_total)} sub={`${bank.credit_count} txns`} />
      <Tile label="Card spend" value={money(card.debit_total)} sub={`${card.debit_count} txns`} />
      <Tile label="Card credits" value={money(card.credit_total)} sub={`${card.credit_count} txns`} />
    </div>
  );
}
