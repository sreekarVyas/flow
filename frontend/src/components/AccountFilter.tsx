import type { AccountType } from "../api";

export type Filter = "all" | AccountType;

const OPTIONS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "bank", label: "Bank" },
  { value: "credit_card", label: "Credit card" },
];

export function AccountFilter({ value, onChange }: { value: Filter; onChange: (f: Filter) => void }) {
  return (
    <div className="flex gap-2" role="radiogroup" aria-label="Account type">
      {OPTIONS.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={
            "rounded-full px-3 py-1 text-sm font-medium ring-1 transition " +
            (value === o.value
              ? "bg-slate-900 text-white ring-slate-900 dark:bg-slate-100 dark:text-slate-900 dark:ring-slate-100"
              : "bg-white text-slate-700 ring-slate-300 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700 dark:hover:bg-slate-800")
          }
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
