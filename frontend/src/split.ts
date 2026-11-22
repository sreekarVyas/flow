import type { SplitMode } from "./api";

/** Mirror of backend app/ledger.py compute_shares, in whole paise. Keep the two in step. */
export function computeShares(
  amountPaise: number,
  mode: SplitMode,
  values: (number | null)[],
  includeMe: boolean,
): { shares: number[]; error: string | null } {
  const n = values.length;
  if (n === 0) return { shares: [], error: null };
  const down = (x: number) => Math.floor(x + 1e-9);
  let shares: number[];
  if (mode === "equal") {
    const per = down(amountPaise / (n + (includeMe ? 1 : 0)));
    shares = Array(n).fill(per);
    if (!includeMe) shares[0] += amountPaise - per * n;
  } else {
    if (values.some((v) => v == null || !(v > 0))) {
      return { shares: [], error: mode === "exact" ? "Enter an amount for each person." : "Enter a percentage for each person." };
    }
    const vs = values as number[];
    if (mode === "percent" && vs.reduce((a, b) => a + b, 0) > 100) {
      return { shares: [], error: "Percentages add up to more than 100." };
    }
    shares = vs.map((v) => (mode === "exact" ? down(v * 100) : down((amountPaise * v) / 100)));
  }
  if (shares.some((s) => s <= 0)) return { shares, error: "A share rounds to zero. Use fewer people or exact amounts." };
  const total = shares.reduce((a, b) => a + b, 0);
  if (total > amountPaise) return { shares, error: "Shares add up to more than the payment." };
  return { shares, error: null };
}

export const toPaise = (rupees: string | number) => Math.round(Number(rupees) * 100);
export const fromPaise = (p: number) => (p / 100).toFixed(2);
