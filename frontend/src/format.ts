function plain(n: number): string {
  if (Number.isInteger(n)) return n.toLocaleString("en-IN");
  return n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function rupees(paise: number | null): string {
  if (paise === null) return "not listed";
  return `₹${plain(paise / 100)}`;
}

export function rupeesInr(inr: number | null): string {
  if (inr === null) return "not listed";
  return `₹${plain(inr)}`;
}

export function etaText(low: number | null, high: number | null): string {
  if (low === null && high === null) return "not listed";
  if (low === null || high === null || low === high) return `${low ?? high} min`;
  return `${low}–${high} min`;
}

export function ratingText(rating: number | null, count: number | null): string {
  if (rating === null) return "no rating listed";
  const base = `★ ${rating.toFixed(1)}`;
  if (count === null) return base;
  return `${base} · ${count.toLocaleString("en-IN")} ratings`;
}

export function ms(n: number): string {
  return `${n < 10 ? n.toFixed(1) : Math.round(n)} ms`;
}

export function titleCase(s: string): string {
  return s
    .split(/(\s+)/)
    .map((part) => (part.length > 0 ? part.charAt(0).toUpperCase() + part.slice(1).toLowerCase() : part))
    .join("");
}
