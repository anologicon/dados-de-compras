export const int = (value: number) =>
  new Intl.NumberFormat("pt-BR").format(value);

export const money = (value: number | null, compact = true) =>
  value === null
    ? "Não informado"
    : new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
        notation: compact && Math.abs(value) >= 1e6 ? "compact" : "standard",
        maximumFractionDigits: 2,
      }).format(value);

export const date = (value: string) =>
  new Date(
    value.length === 10 ? value + "T12:00:00" : value,
  ).toLocaleDateString("pt-BR");

export const datetime = (value: string) =>
  new Date(value).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });

export const percent = (value: number, total: number) =>
  total
    ? new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(
        (value / total) * 100,
      ) + "%"
    : "—";
