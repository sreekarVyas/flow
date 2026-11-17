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
  confirmed: boolean;
  account: Account;
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
  return res.json() as Promise<T>;
}

export const api = {
  transactions: (month: string, accountType?: AccountType) => {
    const q = new URLSearchParams({ month });
    if (accountType) q.set("account_type", accountType);
    return request<Transaction[]>(`/api/transactions?${q}`);
  },
  summary: (month: string) => request<Summary>(`/api/summary?month=${month}`),
  unknownEmails: (month: string) => request<RawEmail[]>(`/api/raw-emails?status=unknown&month=${month}`),
  sync: () => request<PollResult>("/api/sync", { method: "POST" }),
};
