export type AccountType = "bank" | "credit_card";
export type Kind = "expense" | "transfer" | "settlement" | "income" | "refund";

export interface Account {
  id: number;
  name: string;
  type: AccountType;
  institution: string;
  last4: string;
}

export interface Transaction {
  id: number;
  ts: string;
  amount: string; // decimal string, e.g. "336.00"
  direction: "debit" | "credit";
  kind: Kind | null;
  counterparty_name: string | null;
  vpa_or_merchant: string | null;
  ref_no: string | null;
  parse_confidence: string | null;
  category_id: number | null;
  category_source: "rule" | "llm" | "manual" | null;
  confirmed: boolean;
  notes: string | null;
  account: Account;
}

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
  icon: string | null;
  sort_order: number;
  archived: boolean;
  children: Category[];
}

export interface TransactionPatch {
  kind?: Kind | null;
  category_id?: number | null;
  notes?: string | null;
  apply_to_similar?: boolean;
}

export interface Rule {
  id: number;
  match_field: "payee" | "name_contains" | "vpa_contains";
  match_value: string;
  direction: "debit" | "credit" | null;
  category_id: number | null;
  kind: Kind | null;
  source: "seed" | "learned";
  created_at: string;
}

export interface PatchResult {
  transaction: Transaction;
  updated_similar: number;
  rule: Rule | null;
}

export interface Similar {
  payee: string | null;
  count: number;
  learns_rule: boolean;
}

export interface CategorySpend {
  id: number;
  name: string;
  icon: string | null;
  total: string;
  count: number;
}

export interface ParentSpend extends CategorySpend {
  own_total: string;
  children: CategorySpend[];
}

export interface CategorySummary {
  month: string;
  total: string;
  untagged_total: string;
  untagged_count: number;
  parents: ParentSpend[];
}

export interface TypeTotals {
  debit_total: string;
  debit_count: number;
  credit_total: string;
  credit_count: number;
  expense_total: string;
  transfer_total: string;
}

export interface PollResult {
  fetched: number;
  txn: number;
  ignored: number;
  unknown: number;
}

export interface Summary {
  month: string;
  bank: TypeTotals;
  credit_card: TypeTotals;
  unknown_emails: number;
  last_poll_at: string | null;
  last_poll_result: PollResult | null;
}

export interface RawEmail {
  id: number;
  sender: string;
  subject: string;
  received_at: string;
  parse_status: string;
  parser_name: string | null;
  parse_error: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  transactions: (month: string, accountType?: AccountType) => {
    const q = new URLSearchParams({ month });
    if (accountType) q.set("account_type", accountType);
    return request<Transaction[]>(`/api/transactions?${q}`);
  },
  summary: (month: string) => request<Summary>(`/api/summary?month=${month}`),
  unknownEmails: (month: string) => request<RawEmail[]>(`/api/raw-emails?status=unknown&month=${month}`),
  sync: () => request<PollResult>("/api/sync", { method: "POST" }),

  categories: () => request<Category[]>("/api/categories"),
  createCategory: (body: { name: string; parent_id?: number | null; icon?: string | null }) =>
    request<Category>("/api/categories", json("POST", body)),
  updateCategory: (id: number, body: { name?: string; icon?: string | null; archived?: boolean }) =>
    request<Category>(`/api/categories/${id}`, json("PATCH", body)),
  categorySummary: (month: string, accountType?: AccountType) => {
    const q = new URLSearchParams({ month });
    if (accountType) q.set("account_type", accountType);
    return request<CategorySummary>(`/api/categories/summary?${q}`);
  },

  patchTransaction: (id: number, body: TransactionPatch) =>
    request<PatchResult>(`/api/transactions/${id}`, json("PATCH", body)),
  similar: (id: number) => request<Similar>(`/api/transactions/${id}/similar`),

  rules: () => request<Rule[]>("/api/rules"),
  deleteRule: (id: number) => request<void>(`/api/rules/${id}`, { method: "DELETE" }),
};
