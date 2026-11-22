import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { api, type SplitMode, type SplitRequest, type Transaction } from "../api";
import { money } from "../format";
import { computeShares, fromPaise, toPaise } from "../split";

export interface DraftPerson {
  key: string; // React key: person id, or the typed name for a new person
  person_id?: number;
  name: string;
  value: string; // exact rupees or percent, as typed
}

export interface SplitDraft {
  mode: SplitMode;
  includeMe: boolean;
  people: DraftPerson[];
  dirty: boolean;
}

export function draftFromTxn(t: Transaction): SplitDraft {
  const mine = t.splits.filter((s) => s.paid_by === "me");
  return {
    // Existing splits open as exact amounts, so saving again changes nothing.
    mode: mine.length ? "exact" : "equal",
    includeMe: true,
    people: mine.map((s) => ({ key: `p${s.person.id}`, person_id: s.person.id, name: s.person.display_name, value: s.share_amount })),
    dirty: false,
  };
}

export function draftRequest(d: SplitDraft): SplitRequest {
  return {
    mode: d.mode,
    include_me: d.includeMe,
    people: d.people.map((p) => ({
      ...(p.person_id != null ? { person_id: p.person_id } : { name: p.name }),
      ...(d.mode !== "equal" ? { value: p.value } : {}),
    })),
  };
}

export function draftShares(amount: string, d: SplitDraft) {
  const amountPaise = toPaise(amount);
  const values = d.people.map((p) => (p.value.trim() === "" ? null : Number(p.value)));
  const r = computeShares(amountPaise, d.mode, values, d.includeMe);
  const others = r.error ? 0 : r.shares.reduce((a, b) => a + b, 0);
  return { ...r, myShare: amountPaise - others };
}

const MODES: { value: SplitMode; label: string }[] = [
  { value: "equal", label: "Equal" },
  { value: "exact", label: "Exact ₹" },
  { value: "percent", label: "%" },
];

const fieldClass =
  "rounded-lg border border-line bg-surface px-2.5 py-1.5 text-base placeholder:text-ink-muted focus:border-stamp focus:outline-none";

export function PersonPicker({
  exclude,
  onPick,
  label = "Add by nickname",
}: {
  exclude: Set<string>;
  onPick: (p: { id?: number; name: string }) => void;
  label?: string;
}) {
  const [q, setQ] = useState("");
  const listId = useId();
  const typed = q.trim().replace(/\s+/g, " ");
  const found = useQuery({
    queryKey: ["people", typed.toLowerCase()],
    queryFn: () => api.people(typed),
    enabled: typed.length > 0,
    staleTime: 10_000,
  });
  const matches = (found.data ?? []).filter((p) => !exclude.has(p.display_name.toLowerCase())).slice(0, 5);
  const exact = (found.data ?? []).some((p) => p.display_name.toLowerCase() === typed.toLowerCase());
  const options = [
    ...matches.map((p) => ({ id: p.id as number | undefined, name: p.display_name, isNew: false })),
    ...(typed && !exact && !exclude.has(typed.toLowerCase()) ? [{ id: undefined, name: typed, isNew: true }] : []),
  ];
  const pick = (o: { id?: number; name: string }) => {
    onPick(o);
    setQ("");
  };

  return (
    <div className="relative">
      <input
        type="text"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && options.length) {
            e.preventDefault();
            pick(options[0]);
          }
        }}
        placeholder={label}
        aria-label={label === "Add by nickname" ? "Add a person to the split" : label}
        aria-controls={listId}
        aria-expanded={options.length > 0}
        autoComplete="off"
        maxLength={100}
        className={`${fieldClass} w-full`}
      />
      {options.length > 0 && (
        <ul id={listId} className="absolute inset-x-0 top-full z-10 mt-1 overflow-hidden rounded-lg border border-line bg-surface shadow-lg">
          {options.map((o) => (
            <li key={`${o.id ?? "new"}-${o.name}`}>
              <button
                type="button"
                onClick={() => pick(o)}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-stamp-soft focus-visible:bg-stamp-soft"
              >
                {o.isNew ? (
                  <>
                    Add <span className="font-semibold">{o.name}</span> as a new person
                  </>
                ) : (
                  o.name
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SplitEditor({ amount, draft, onChange }: { amount: string; draft: SplitDraft; onChange: (d: SplitDraft) => void }) {
  const set = (patch: Partial<SplitDraft>) => onChange({ ...draft, ...patch, dirty: true });
  const { shares, error, myShare } = draftShares(amount, draft);
  const exclude = new Set(draft.people.map((p) => p.name.toLowerCase()));
  const has = draft.people.length > 0;

  return (
    <section aria-labelledby="split-heading" className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <h3 id="split-heading" className="text-sm font-medium text-ink-muted">
          Split with people
        </h3>
        {has && (
          <div className="flex rounded-lg border border-line bg-surface p-0.5" role="radiogroup" aria-label="How to split">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                role="radio"
                aria-checked={draft.mode === m.value}
                onClick={() => set({ mode: m.value })}
                className={
                  "rounded-md px-2.5 py-1 text-sm font-medium " +
                  (draft.mode === m.value ? "bg-ink text-paper" : "text-ink-muted hover:text-ink")
                }
              >
                {m.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {has && (
        <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
          {draft.people.map((p, i) => (
            <li key={p.key} className="flex items-center gap-2 px-3 py-2">
              <span className="min-w-0 flex-1 truncate font-medium">
                {p.name}
                {p.person_id == null && <span className="ml-1.5 text-xs font-normal text-ink-muted">new</span>}
              </span>
              {draft.mode !== "equal" && (
                <input
                  type="number"
                  inputMode="decimal"
                  min="0"
                  step={draft.mode === "exact" ? "0.01" : "0.1"}
                  value={p.value}
                  onChange={(e) =>
                    set({ people: draft.people.map((x) => (x.key === p.key ? { ...x, value: e.target.value } : x)) })
                  }
                  aria-label={draft.mode === "exact" ? `${p.name}'s share in rupees` : `${p.name}'s share in percent`}
                  placeholder={draft.mode === "exact" ? "₹" : "%"}
                  className={`${fieldClass} w-24 py-1 text-right`}
                />
              )}
              {draft.mode !== "exact" && (
                <span className="w-24 shrink-0 text-right text-sm">{!error && shares[i] != null ? money(fromPaise(shares[i])) : ""}</span>
              )}
              <button
                type="button"
                onClick={() => set({ people: draft.people.filter((x) => x.key !== p.key) })}
                aria-label={`Remove ${p.name} from the split`}
                className="shrink-0 px-1 text-lg leading-none text-ink-muted hover:text-out"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <PersonPicker
        exclude={exclude}
        onPick={(o) =>
          set({
            people: [...draft.people, { key: o.id != null ? `p${o.id}` : `n${o.name.toLowerCase()}`, person_id: o.id, name: o.name, value: "" }],
          })
        }
      />

      {has && draft.mode === "equal" && (
        <label className="flex cursor-pointer items-center justify-between gap-3 text-sm">
          <span>I take an equal share too</span>
          <input
            type="checkbox"
            role="switch"
            checked={draft.includeMe}
            onChange={(e) => set({ includeMe: e.target.checked })}
            className="peer sr-only"
          />
          <span
            aria-hidden
            className="relative h-6 w-10 shrink-0 rounded-full bg-line transition-colors peer-checked:bg-stamp peer-focus-visible:outline-2 peer-focus-visible:outline-stamp after:absolute after:left-0.5 after:top-0.5 after:h-5 after:w-5 after:rounded-full after:bg-surface after:shadow after:transition-transform peer-checked:after:translate-x-4"
          />
        </label>
      )}

      {has ? (
        error ? (
          <p className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">{error}</p>
        ) : (
          <p className="flex items-baseline justify-between rounded-lg bg-stamp-soft px-3 py-2 text-sm">
            <span>Your share, counted as your spending</span>
            <span className="text-base font-semibold">{money(fromPaise(myShare))}</span>
          </p>
        )
      ) : (
        <p className="text-sm text-ink-muted">Paid for friends too? Add them by nickname. Their shares are not counted as your spending.</p>
      )}
    </section>
  );
}
