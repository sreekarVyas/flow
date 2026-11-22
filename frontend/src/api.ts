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
  splits: Split[];
  my_share: string; // amount minus other people's shares
  person: PersonRef | null; // settlements: who it is from / to
  links_out: LinkToShare[]; // settlements: the shares it pays
  unapplied: string; // settlements: part not tagged to any payment
}

export interface TxnBrief {
  id: number;
  ts: string;
  amount: string;
  direction: "debit" | "credit";
  counterparty_name: string | null;
  vpa_or_merchant: string | null;
}

export interface LinkToShare {
  id: number;
  amount: string;
  settles: boolean;
  split: { id: number; share_amount: string; outstanding: string; transaction: TxnBrief };
}

export interface LinkFromSettlement {
  id: number;
  amount: string;
  settles: boolean; // false = money returned to them
  settlement: TxnBrief;
}

export interface SettleCandidate {
  transaction: Transaction;
  share: { id: number; share_amount: string; outstanding: string } | null;
  linked_amount: string;
}

export interface Source {
  printed_name: string | null;
  vpa: string | null;
  person: PersonRef | null; // the nickname, known or guessed
  known: boolean; // this exact name + UPI ID already has this nickname
  suggestion: string;
}

export interface SettlementRequest {
  nickname: string;
  links: { transaction_id: number; amount: string; share?: string }[];
}

export interface PersonRef {
  id: number;
  display_name: string;
}

export interface Split {
  id: number;
  person: PersonRef;
  share_amount: string;
  paid_by: "me" | "person";
  origin: "manual" | "link";
  settled: string;
  outstanding: string; // negative = overpaid
  links: LinkFromSettlement[];
}

export type SplitMode = "equal" | "exact" | "percent";

export interface SplitRequest {
  mode: SplitMode;
  include_me: boolean;
  people: { person_id?: number; name?: string; value?: string }[];
}

export interface Person {
  id: number;
  display_name: string;
  owed_to_me: string;
  i_owe: string;
  received: string;
  paid: string;
  net: string; // + they owe me, - I owe them
  shares: number;
}

export interface PersonDetail extends Person {
  match_names: string[];
  history: {
    split_id: number;
    share_amount: string;
    settled: string;
    outstanding: string;
    paid_by: "me" | "person";
    transaction: Transaction;
  }[];
  repayments: Transaction[];
  sources: { id: number; printed_name: string | null; vpa: string }[];
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
  my_share_total: string;
}

export interface SharedTotals {
  others_share: string;
  recovered: string;
  owed_to_me: string;
  i_owe: string;
  people_owing: number;
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
  shared: SharedTotals;
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

  putSplits: (id: number, body: SplitRequest) => request<Transaction>(`/api/transactions/${id}/splits`, json("PUT", body)),

  people: (q?: string) => request<Person[]>(`/api/people${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  person: (id: number) => request<PersonDetail>(`/api/people/${id}`),
  createPerson: (name: string) => request<Person>("/api/people", json("POST", { name })),
  renamePerson: (id: number, display_name: string) => request<Person>(`/api/people/${id}`, json("PATCH", { display_name })),
  deletePerson: (id: number) => request<void>(`/api/people/${id}`, { method: "DELETE" }),
  mergePeople: (id: number, intoId: number) => request<Person>(`/api/people/${id}/merge`, json("POST", { into_id: intoId })),
  forgetSource: (id: number) => request<void>(`/api/payment-sources/${id}`, { method: "DELETE" }),

  transaction: (id: number) => request<Transaction>(`/api/transactions/${id}`),
  putSettlement: (id: number, body: SettlementRequest) =>
    request<Transaction>(`/api/transactions/${id}/settlement`, json("PUT", body)),
  source: (id: number) => request<Source>(`/api/transactions/${id}/source`),
  settleCandidates: (id: number, nickname?: string, q?: string) => {
    const p = new URLSearchParams();
    if (nickname) p.set("nickname", nickname);
    if (q) p.set("q", q);
    return request<{ suggested_person: PersonRef | null; items: SettleCandidate[] }>(
      `/api/transactions/${id}/settle-candidates?${p}`,
    );
  },
  repaymentCandidates: (id: number, q?: string) =>
    request<{ items: { transaction: Transaction; linked_amount: string }[] }>(
      `/api/transactions/${id}/repayment-candidates${q ? `?q=${encodeURIComponent(q)}` : ""}`,
    ),
  addRepayment: (
    expenseId: number,
    body: { settlement_txn_id: number; amount: string; nickname: string; share?: string },
  ) => request<Transaction>(`/api/transactions/${expenseId}/repayments`, json("POST", body)),
  deleteLink: (id: number) => request<void>(`/api/settlement-links/${id}`, { method: "DELETE" }),

  rules: () => request<Rule[]>("/api/rules"),
  deleteRule: (id: number) => request<void>(`/api/rules/${id}`, { method: "DELETE" }),
};
