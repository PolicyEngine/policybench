export function formatCurrency(
  value: number,
  currencySymbol: "$" | "£" = "$"
): string {
  const rounded = Math.round(value);

  if (Object.is(rounded, -0) || rounded === 0) {
    return `${currencySymbol}0`;
  }

  const abs = Math.abs(rounded).toLocaleString();
  return rounded < 0 ? `-${currencySymbol}${abs}` : `${currencySymbol}${abs}`;
}

export function formatDollars(value: number): string {
  return formatCurrency(value, "$");
}
