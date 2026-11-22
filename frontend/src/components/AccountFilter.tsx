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
            "rounded-full border px-3 py-1 text-sm font-medium transition-colors " +
            (value === o.value
              ? "border-ink bg-ink text-paper"
              : "border-line bg-surface text-ink hover:bg-surface-2")
          }
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
