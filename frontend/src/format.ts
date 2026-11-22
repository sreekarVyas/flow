export const TZ = "Asia/Kolkata";

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

export const money = (amount: string | number) => inr.format(Number(amount));

/** YYYY-MM-DD in IST, for grouping. */
export const dayKey = (ts: string) => new Date(ts).toLocaleDateString("en-CA", { timeZone: TZ });

export const dayLabel = (key: string) =>
  new Date(`${key}T00:00:00+05:30`).toLocaleDateString("en-IN", {
    timeZone: TZ,
    weekday: "short",
    day: "numeric",
    month: "short",
  });

export const timeLabel = (ts: string) =>
  new Date(ts).toLocaleTimeString("en-IN", { timeZone: TZ, hour: "numeric", minute: "2-digit" });

export const monthLabel = (month: string) =>
  new Date(`${month}-01T00:00:00+05:30`).toLocaleDateString("en-IN", { timeZone: TZ, month: "long", year: "numeric" });

export const relative = (ts: string) => {
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  return hrs < 24 ? `${hrs} h ago` : new Date(ts).toLocaleString("en-IN", { timeZone: TZ });
};

export const payeeOf = (t: { counterparty_name: string | null; vpa_or_merchant: string | null }) =>
  t.counterparty_name || t.vpa_or_merchant || "Unknown payee";

export const shortDate = (ts: string) =>
  new Date(ts).toLocaleDateString("en-IN", { timeZone: TZ, day: "numeric", month: "short" });
