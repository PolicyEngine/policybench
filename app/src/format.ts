export function formatDollars(value: number): string {
  const rounded = Math.round(value);

  if (Object.is(rounded, -0) || rounded === 0) {
    return "$0";
  }

  const abs = Math.abs(rounded).toLocaleString();
  return rounded < 0 ? `-$${abs}` : `$${abs}`;
}
