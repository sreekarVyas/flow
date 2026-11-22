import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api, type Category, type Kind } from "./api";

export interface CatInfo {
  cat: Category;
  parent: Category | null; // null for a top-level category
  icon: string; // own icon, or the parent's
  label: string; // "Tea & coffee"
  path: string; // "Food & drinks › Tea & coffee"
}

export function useCategories() {
  const q = useQuery({ queryKey: ["categories"], queryFn: api.categories, staleTime: 5 * 60_000 });
  const byId = useMemo(() => {
    const m = new Map<number, CatInfo>();
    for (const p of q.data ?? []) {
      m.set(p.id, { cat: p, parent: null, icon: p.icon ?? "•", label: p.name, path: p.name });
      for (const c of p.children) {
        m.set(c.id, { cat: c, parent: p, icon: c.icon ?? p.icon ?? "•", label: c.name, path: `${p.name} › ${c.name}` });
      }
    }
    return m;
  }, [q.data]);
  return { tree: q.data ?? [], byId, query: q };
}

export const KIND_LABEL: Record<Kind, string> = {
  expense: "Expense",
  transfer: "Transfer",
  settlement: "Settlement",
  income: "Income",
  refund: "Refund",
};

/** Only these kinds carry a category. Matches CATEGORIZABLE_KINDS in the backend. */
export const hasCategory = (kind: Kind | null) => kind === "expense" || kind === "refund";

// ---- recent picks (per device; a convenience only) ----

const RECENT_KEY = "flow.recentCategories";

export function readRecent(): number[] {
  try {
    const v = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "number") : [];
  } catch {
    return [];
  }
}

export function pushRecent(id: number) {
  try {
    const next = [id, ...readRecent().filter((x) => x !== id)].slice(0, 6);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    /* storage blocked: recents are optional */
  }
}
