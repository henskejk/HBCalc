// Number formatting helpers. The brewing maths is all on the server; these only format.

/** Like Python's "%g": drops trailing zeros (1.50 -> "1.5"). */
export const g = (x) => (x == null || Number.isNaN(x) ? "" : String(Number(Number(x).toFixed(6))));

/** Fixed decimals, or an en dash when there is no value. */
export const fixed = (x, digits) => (x == null || Number.isNaN(x) ? "–" : Number(x).toFixed(digits));

/** Signed difference text like "+1.2" / "-3". */
export const signed = (x, digits) => (x >= 0 ? "+" : "-") + Math.abs(x).toFixed(digits);

/**
 * How a value sits against a style's [low, high] range: the range as text ("5.5–7.5") and a tone.
 * "good" = inside the range; "warn" = outside by up to 20% of the range width; "bad" = further out.
 */
export function rangeStatus(value, bounds, digits) {
  if (!bounds) return { text: "", tone: "" };
  const [lo, hi] = bounds;
  const text = digits == null ? `${g(lo)}–${g(hi)}` : `${lo.toFixed(digits)}–${hi.toFixed(digits)}`;
  if (value >= lo && value <= hi) return { text, tone: "good" };
  const width = hi - lo || Math.abs(hi) * 0.1 || 1;
  const off = (value < lo ? lo - value : value - hi) / width;
  return { text, tone: off <= 0.2 ? "warn" : "bad" };
}

export const todayISO = () => {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
