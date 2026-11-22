import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { api, type Transaction } from "../api";

const key = (s: string) => s.trim().replace(/\s+/g, " ").toLowerCase();

/**
 * The payment source of a transaction (bank-printed name + UPI ID) and its nickname.
 * The nickname is the person: the same nickname on two UPI IDs is one person (case does not matter).
 * Prefills from the known nickname, else the best guess, else the printed name. Calls onChange once
 * with the prefill (not marked as a change by the caller), then on every edit.
 */
export function NicknameField({
  txn,
  value,
  onChange,
  fallback,
}: {
  txn: Transaction;
  value: string;
  onChange: (nickname: string, edited: boolean) => void;
  fallback?: string; // used before the source's suggestion, e.g. the only person on a split
}) {
  const listId = useId();
  const source = useQuery({ queryKey: ["source", txn.id], queryFn: () => api.source(txn.id) });
  const [focused, setFocused] = useState(false);
  const filled = useRef(false);

  useEffect(() => {
    if (filled.current || !source.data) return;
    filled.current = true;
    if (!value) onChange(txn.person?.display_name ?? source.data.person?.display_name ?? fallback ?? source.data.suggestion, false);
  }, [source.data, value, onChange, txn.person, fallback]);

  const typed = value.trim();
  const people = useQuery({
    queryKey: ["people", key(typed)],
    queryFn: () => api.people(typed),
    enabled: typed.length > 0,
    staleTime: 10_000,
  });
  const exact = people.data?.find((p) => key(p.display_name) === key(typed));
  const others = (people.data ?? []).filter((p) => p !== exact).slice(0, 4);
  const src = source.data;
  const isKnown = !!src?.known && !!src.person && key(src.person.display_name) === key(typed);
  const isGuess = !!src && !src.known && !txn.person && !!src.person && key(src.person.display_name) === key(typed);

  let hint = "";
  if (!typed) hint = "Give this payment source a nickname.";
  else if (isKnown) hint = `This UPI ID is already ${src!.person!.display_name}.`;
  else if (isGuess) hint = `Guessed from the bank name: another UPI ID with this name is ${src!.person!.display_name}. Change it if this is someone else.`;
  else if (exact) hint = `Counts as ${exact.display_name}, the same person as their other UPI IDs.`;
  else hint = `New nickname. Payments from this UPI ID will count as ${typed}.`;

  return (
    <div className="space-y-2">
      <div className="rounded-lg border border-line bg-surface px-3 py-2">
        <div className="text-xs text-ink-muted">{txn.direction === "credit" ? "Paid by" : "Paid to"}</div>
        <div className="truncate font-medium">{src?.printed_name ?? txn.counterparty_name ?? "Unknown payee"}</div>
        {src?.vpa && <div className="truncate text-xs text-ink-muted">UPI ID {src.vpa}</div>}
      </div>
      <div className="relative">
        <label htmlFor={`${listId}-nick`} className="mb-1 block text-sm font-medium text-ink-muted">
          Nickname
        </label>
        <input
          id={`${listId}-nick`}
          type="text"
          value={value}
          maxLength={100}
          autoComplete="off"
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 150)}
          onChange={(e) => onChange(e.target.value, true)}
          aria-describedby={`${listId}-hint`}
          className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-base font-semibold focus:border-stamp focus:outline-none"
        />
        {focused && others.length > 0 && (
          <ul className="absolute inset-x-0 top-full z-10 mt-1 overflow-hidden rounded-lg border border-line bg-surface shadow-lg">
            {others.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    onChange(p.display_name, true);
                    setFocused(false);
                  }}
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-stamp-soft"
                >
                  {p.display_name}
                </button>
              </li>
            ))}
          </ul>
        )}
        <p id={`${listId}-hint`} className={`mt-1 text-sm ${isGuess ? "text-warn" : exact || isKnown ? "text-in" : "text-ink-muted"}`}>
          {source.isPending ? "Looking up this payment source…" : hint}
        </p>
      </div>
    </div>
  );
}
