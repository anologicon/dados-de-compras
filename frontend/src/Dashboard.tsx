import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Building2,
  Check,
  CircleHelp,
  FileJson,
  ListFilter,
  Table2,
  TriangleAlert,
} from "lucide-react";
import {
  hasExpandedOverview,
  type Amounts,
  type Overview,
  type OverviewResponse,
} from "./api";
import { date, int, money, percent } from "./format";

type Measure = "purchases" | "estimated" | "awarded";
const measures: { id: Measure; label: string }[] = [
  { id: "purchases", label: "Compras" },
  { id: "estimated", label: "Estimado" },
  { id: "awarded", label: "Homologado" },
];
const colors = [
  "#205b54",
  "#d07950",
  "#839c9a",
  "#b9a27c",
  "#6a758f",
  "#d4d4cb",
];
const valueLabel = (value: number | null, measure: Measure, compact = true) =>
  measure === "purchases" ? int(value ?? 0) : money(value, compact);
const knownCount = (row: Amounts, measure: Measure) =>
  measure === "estimated"
    ? row.estimated_known
    : measure === "awarded"
      ? row.awarded_known
      : row.purchases;
const monthLabel = (month: string, short = false) =>
  new Date(month + "-15T12:00:00").toLocaleDateString("pt-BR", {
    month: short ? "short" : "long",
    year: "numeric",
  });

function ChartEmpty() {
  return (
    <div className="chart-empty">
      Nenhuma compra neste recorte.
      <span>Ajuste os filtros para explorar os dados disponíveis.</span>
    </div>
  );
}

function Metric({
  label,
  value,
  note,
  icon,
  accent = false,
}: {
  label: string;
  value: string;
  note: string;
  icon: ReactNode;
  accent?: boolean;
}) {
  return (
    <section className={"metric" + (accent ? " accent" : "")}>
      <div className="metric-label">
        {label}
        <span>{icon}</span>
      </div>
      <strong>{value}</strong>
      <p>{note}</p>
    </section>
  );
}

function Timeline({ monthly }: { monthly: OverviewResponse["monthly"] }) {
  const [measure, setMeasure] = useState<Measure>("purchases");
  const [selected, setSelected] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Start at the most recent months, including on narrow screens. Scroll only
    // the plot, never the surrounding page; keyboard focus reveals other bars.
    const plot = scrollRef.current;
    if (plot) plot.scrollLeft = plot.scrollWidth;
  }, [monthly]);
  const active =
    monthly.find((row) => row.month === selected) || monthly.at(-1);
  const values = monthly
    .map((row) => row[measure])
    .filter((v): v is number => v !== null);
  const upper = Math.max(0, ...values);
  const lower = Math.min(0, ...values);
  const extent = upper - lower || 1;
  const baseline = (-lower / extent) * 100;
  return (
    <section className="panel timeline-panel" aria-labelledby="timeline-title">
      <div className="panel-head">
        <div>
          <span className="section-kicker">01 / NO TEMPO</span>
          <h2 id="timeline-title">O ritmo das publicações</h2>
          <p>Quantidade e valores por mês de publicação</p>
        </div>
        <div
          className="segmented"
          role="group"
          aria-label="Medida da evolução mensal"
        >
          {measures.map((item) => (
            <button
              key={item.id}
              aria-pressed={measure === item.id}
              onClick={() => setMeasure(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      {monthly.length ? (
        <>
          <div className="timeline-chart">
            <div className="chart-axis" aria-hidden="true">
              <span>{values.length ? valueLabel(upper, measure) : "—"}</span>
              <span>
                {values.length ? valueLabel((upper + lower) / 2, measure) : "—"}
              </span>
              <span>{values.length ? valueLabel(lower, measure) : "—"}</span>
            </div>
            <div className="chart-scroll" ref={scrollRef}>
              <div className={"chart measure-" + measure}>
                {monthly.map((row) => {
                  const value = row[measure];
                  const known =
                    measure === "estimated"
                      ? row.estimated_known
                      : row.awarded_known;
                  const completeness =
                    known === undefined
                      ? "; preenchimento mensal indisponível nesta versão do serviço"
                      : `; ${known} de ${row.purchases} compras com valor informado`;
                  const label = `${monthLabel(row.month)}: ${valueLabel(value, measure, false)}${measure !== "purchases" ? completeness : " compras"}`;
                  return (
                    <button
                      className={
                        "bar-column" +
                        (active?.month === row.month ? " is-active" : "")
                      }
                      key={row.month}
                      title={label}
                      aria-label={label}
                      aria-pressed={active?.month === row.month}
                      onClick={() => setSelected(row.month)}
                      onFocus={() => setSelected(row.month)}
                    >
                      <span className="bar-value">
                        {value === null ? "—" : valueLabel(value, measure)}
                      </span>
                      <span className="bar-space">
                        <span
                          className="zero-line"
                          style={{ bottom: `${baseline}%` }}
                        />
                        {value !== null && value !== 0 && (
                          <span
                            className="bar"
                            style={{
                              height: `${(Math.abs(value) / extent) * 100}%`,
                              bottom: `${value >= 0 ? baseline : baseline + (value / extent) * 100}%`,
                            }}
                          />
                        )}
                        {value === null && (
                          <span className="missing-mark">n/d</span>
                        )}
                        {value === 0 && (
                          <span
                            className="zero-mark"
                            style={{ bottom: `${baseline}%` }}
                          />
                        )}
                      </span>
                      <span className="bar-label">
                        {monthLabel(row.month, true)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
          {active && (
            <div className="chart-readout" aria-live="polite">
              <strong>{monthLabel(active.month)}</strong>
              <span>
                <i className="legend-dot" />
                {int(active.purchases)} compras
              </span>
              <span>
                Estimado <b>{money(active.estimated)}</b>
              </span>
              <span>
                Homologado <b>{money(active.awarded)}</b>
              </span>
            </div>
          )}
          <details className="chart-data">
            <summary>Ver dados mensais e valores exatos</summary>
            <div className="table-scroll">
              <table>
                <caption>
                  Valores por mês de publicação. n/d significa não informado.
                </caption>
                <thead>
                  <tr>
                    <th>Mês</th>
                    <th>Compras</th>
                    <th>Estimado</th>
                    <th>Com estimado</th>
                    <th>Homologado</th>
                    <th>Com homologado</th>
                  </tr>
                </thead>
                <tbody>
                  {monthly.map((row) => (
                    <tr key={row.month}>
                      <th scope="row">{monthLabel(row.month)}</th>
                      <td>{int(row.purchases)}</td>
                      <td>{money(row.estimated, false)}</td>
                      <td>
                        {row.estimated_known === undefined
                          ? "Indisponível nesta versão"
                          : `${row.estimated_known} / ${row.purchases}`}
                      </td>
                      <td>{money(row.awarded, false)}</td>
                      <td>
                        {row.awarded_known === undefined
                          ? "Indisponível nesta versão"
                          : `${row.awarded_known} / ${row.purchases}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          <p className="chart-footnote">
            Valores somam apenas campos informados, por mês de publicação — não
            de pagamento. Meses sem registros não são preenchidos com zero.
          </p>
        </>
      ) : (
        <ChartEmpty />
      )}
    </section>
  );
}

function Modalities({
  data,
  explore,
}: {
  data: Overview;
  explore: (filter?: { modality: string }) => void;
}) {
  const total = data.metrics.purchases;
  const groups = data.modality_breakdown.slice(0, 5).map((row) => ({
    label: row.modality,
    count: row.purchases,
    filter: row.modality,
  }));
  const remaining = data.modality_breakdown
    .slice(5)
    .reduce((sum, row) => sum + row.purchases, 0);
  if (remaining)
    groups.push({ label: "Outras modalidades", count: remaining, filter: "" });
  let offset = 0;
  return (
    <section className="panel modality-panel" aria-labelledby="modality-title">
      <div className="panel-head">
        <div>
          <span className="section-kicker">02 / DISTRIBUIÇÃO</span>
          <h2 id="modality-title">Como se compra</h2>
          <p>Participação das modalidades no recorte</p>
        </div>
      </div>
      {total ? (
        <div className="modality-content">
          <div className="donut-wrap">
            <svg
              className="donut"
              viewBox="0 0 160 160"
              role="img"
              aria-label={`Distribuição de ${int(total)} compras por modalidade; detalhes na lista ao lado`}
            >
              {groups.map((group, index) => {
                const share = (group.count / total) * 100;
                const start = offset;
                offset += share;
                return (
                  <circle
                    key={group.label}
                    cx="80"
                    cy="80"
                    r="64"
                    fill="none"
                    stroke={colors[index]}
                    strokeWidth="17"
                    pathLength="100"
                    strokeDasharray={`${share} ${100 - share}`}
                    strokeDashoffset={-start}
                    transform="rotate(-90 80 80)"
                  >
                    <title>
                      {group.label}: {int(group.count)} (
                      {percent(group.count, total)})
                    </title>
                  </circle>
                );
              })}
            </svg>
            <div className="donut-label" aria-hidden="true">
              <strong>{int(total)}</strong>
              <span>compras</span>
            </div>
          </div>
          <ul className="modality-list">
            {groups.map((group, index) => (
              <li key={group.label}>
                <span
                  className="legend-dot"
                  style={{ background: colors[index] }}
                />
                {group.filter ? (
                  <button
                    title={`Explorar ${group.label}`}
                    onClick={() => explore({ modality: group.filter })}
                  >
                    {group.label}
                  </button>
                ) : (
                  <span>{group.label}</span>
                )}
                <strong>
                  {percent(group.count, total)}
                  <small>{int(group.count)} compras</small>
                </strong>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <ChartEmpty />
      )}
      <div className="panel-bottom-note">
        Participação por quantidade, não por valor. Modalidades ausentes
        aparecem como “Não informada”.
      </div>
    </section>
  );
}

function Organizations({
  data,
  explore,
}: {
  data: Overview;
  explore: (filter?: { org_name: string }) => void;
}) {
  const [measure, setMeasure] = useState<Measure>("purchases");
  const sorted = [...data.organizations].sort((a, b) => {
    if (a[measure] === null)
      return b[measure] === null ? a.org_name.localeCompare(b.org_name) : 1;
    if (b[measure] === null) return -1;
    return (
      (b[measure] as number) - (a[measure] as number) ||
      a.org_name.localeCompare(b.org_name)
    );
  });
  const top = sorted.slice(0, 6);
  const max = Math.max(1, ...top.map((row) => Math.abs(row[measure] ?? 0)));
  return (
    <section className="panel organizations-panel" aria-labelledby="org-title">
      <div className="panel-head">
        <div>
          <span className="section-kicker">03 / QUEM COMPRA</span>
          <h2 id="org-title">Órgãos em destaque</h2>
          <p>Os seis maiores no recorte selecionado</p>
        </div>
        <label className="ranking-select">
          <span>Ordenar por</span>
          <select
            aria-label="Ordenar órgãos por"
            value={measure}
            onChange={(e) => setMeasure(e.target.value as Measure)}
          >
            {measures.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {top.length ? (
        <ol className="org-list">
          {top.map((row, index) => (
            <li key={row.org_name}>
              <button
                className="org-row"
                onClick={() => explore({ org_name: row.org_name })}
                title={`Explorar ${row.org_name}`}
              >
                <span className="org-rank">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="org-content">
                  <span className="org-label">
                    <span>{row.org_name}</span>
                    <strong>{valueLabel(row[measure], measure)}</strong>
                  </span>
                  <span className="track">
                    <i
                      style={{
                        width: `${(Math.abs(row[measure] ?? 0) / max) * 100}%`,
                      }}
                    />
                  </span>
                  <span className="org-meta">
                    {int(row.purchases)} compras
                    {measure !== "purchases" &&
                      ` · ${int(knownCount(row, measure))} com valor informado`}
                  </span>
                </span>
                <ArrowRight size={15} />
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <ChartEmpty />
      )}
      <button className="panel-link" onClick={() => explore()}>
        Explorar todas as compras <ArrowRight size={16} />
      </button>
    </section>
  );
}

function Quality({ data }: { data: Overview }) {
  const m = data.metrics;
  const fields = [
    { label: "Valor estimado", count: m.estimated_known },
    { label: "Valor homologado", count: m.awarded_known },
    { label: "Órgão identificado", count: m.organization_known },
    { label: "Modalidade informada", count: m.modality_known },
  ];
  return (
    <section className="panel quality-panel" aria-labelledby="quality-title">
      <div className="panel-head">
        <div>
          <span className="section-kicker">04 / CONTEXTO DOS DADOS</span>
          <h2 id="quality-title">O que os registros informam</h2>
          <p>Preenchimento de campos, não conclusão da coleta</p>
        </div>
      </div>
      <div className="quality-list">
        {fields.map((field) => (
          <div className="quality-row" key={field.label}>
            <div>
              <span>{field.label}</span>
              <strong>{percent(field.count, m.purchases)}</strong>
            </div>
            <div
              className="track"
              role="meter"
              aria-label={field.label}
              aria-valuemin={0}
              aria-valuemax={Math.max(1, m.purchases)}
              aria-valuenow={field.count}
              aria-valuetext={`${int(field.count)} de ${int(m.purchases)} compras${m.purchases ? "" : "; sem dados para avaliar"}`}
            >
              <i
                style={{
                  width: `${m.purchases ? (field.count / m.purchases) * 100 : 0}%`,
                }}
              />
            </div>
            <small>
              {int(field.count)} de {int(m.purchases)} compras
            </small>
          </div>
        ))}
      </div>
      <div className="sources-summary">
        <span className="section-kicker">ORIGEM DAS COMPRAS CONSOLIDADAS</span>
        <div>
          {data.sources.length ? (
            data.sources.map((source) => (
              <span className="source-summary" key={source.family}>
                <i className={"legend-dot " + source.family} />
                {source.family === "pncp" ? "PNCP" : "Legado"}
                <strong>{int(source.purchases)}</strong>
                <small>{percent(source.purchases, m.purchases)}</small>
              </span>
            ))
          ) : (
            <span className="muted">Sem compras no recorte.</span>
          )}
        </div>
        <p>
          Ausência de valor não significa zero. Preenchimento não comprova
          cobertura completa nem qualidade do conteúdo.
        </p>
      </div>
    </section>
  );
}

function CompatibleOrganizations({
  data,
  explore,
}: {
  data: OverviewResponse;
  explore: (filter?: { org_name?: string }) => void;
}) {
  const top = [...data.organizations]
    .sort(
      (a, b) =>
        b.purchases - a.purchases || a.org_name.localeCompare(b.org_name),
    )
    .slice(0, 6);
  const max = Math.max(1, ...top.map((row) => row.purchases));
  return (
    <section className="panel" aria-labelledby="compatible-org-title">
      <div className="panel-head">
        <div>
          <span className="section-kicker">QUEM COMPRA</span>
          <h2 id="compatible-org-title">Principais órgãos por quantidade</h2>
          <p>Ranking disponível na versão atual do serviço</p>
        </div>
      </div>
      {top.length ? (
        <ol className="org-list">
          {top.map((row, index) => (
            <li key={row.org_name}>
              <button
                className="org-row"
                onClick={() => explore({ org_name: row.org_name })}
              >
                <span className="org-rank">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="org-content">
                  <span className="org-label">
                    <span>{row.org_name}</span>
                    <strong>{int(row.purchases)}</strong>
                  </span>
                  <span className="track">
                    <i style={{ width: `${(row.purchases / max) * 100}%` }} />
                  </span>
                </span>
                <ArrowRight size={15} />
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <ChartEmpty />
      )}
      <button className="panel-link" onClick={() => explore()}>
        Explorar todas as compras <ArrowRight size={16} />
      </button>
    </section>
  );
}

export function Dashboard({
  data,
  exportUrl,
  openPurchases,
}: {
  data: OverviewResponse;
  exportUrl: string;
  openPurchases: (filter?: { org_name?: string; modality?: string }) => void;
}) {
  const m = data.metrics;
  const expanded = hasExpandedOverview(data);
  const range = expanded ? data.filtered_range : null;
  return (
    <div className="dashboard">
      {!expanded && (
        <div className="notice warning" role="status">
          <TriangleAlert size={20} />
          <div>
            <strong>Serviço em versão anterior</strong>
            <span>
              O panorama básico continua disponível. Para liberar as análises
              detalhadas, reinicie o serviço após concluir as coletas. Atualizar
              apenas a página não atualiza o backend.
            </span>
          </div>
        </div>
      )}
      <div className="overview-caption">
        <div>
          <span className="section-kicker">PANORAMA DO RECORTE</span>
          <p>
            {!range ? (
              "Totais do recorte selecionado · período detalhado indisponível nesta versão"
            ) : range.start_date && range.end_date ? (
              <>
                Publicações de <strong>{date(range.start_date)}</strong> a{" "}
                <strong>{date(range.end_date)}</strong>
              </>
            ) : (
              "Nenhuma publicação encontrada com estes filtros"
            )}
          </p>
        </div>
        <div className="actions">
          <a className="button secondary" href={exportUrl + "&format=csv"}>
            <ArrowDownToLine size={15} />
            CSV
          </a>
          <a className="button secondary" href={exportUrl + "&format=json"}>
            <FileJson size={15} />
            JSON
          </a>
        </div>
      </div>
      <div className="metrics">
        <Metric
          label="Compras publicadas"
          value={int(m.purchases)}
          note="Registros únicos no recorte"
          icon={<Table2 size={18} />}
        />
        <Metric
          label="Valor estimado"
          value={money(m.estimated)}
          note={`${int(m.estimated_known)} de ${int(m.purchases)} com valor informado`}
          icon={<ListFilter size={18} />}
        />
        <Metric
          label="Valor homologado"
          value={money(m.awarded)}
          note={`${int(m.awarded_known)} de ${int(m.purchases)} com valor informado`}
          icon={<Check size={18} />}
          accent
        />
        <Metric
          label="Órgãos compradores"
          value={int(m.organizations)}
          note={
            expanded
              ? "Órgãos identificados no município"
              : "Contagem publicada pelo serviço"
          }
          icon={<Building2 size={18} />}
        />
      </div>
      <Timeline monthly={data.monthly} />
      {expanded ? (
        <>
          <div className="charts">
            <Modalities data={data} explore={openPurchases} />
            <Organizations data={data} explore={openPurchases} />
          </div>
          <Quality data={data} />
        </>
      ) : (
        <CompatibleOrganizations data={data} explore={openPurchases} />
      )}
      <div className="method-note">
        <CircleHelp size={20} />
        <p>
          <strong>Dados abertos pedem contexto.</strong> O recorte é
          territorial, não apenas da prefeitura. Estimado e homologado são
          medidas distintas: não devem ser somados e não representam valores
          efetivamente pagos. Os indicadores usam apenas compras conciliadas; o
          aviso de cobertura se refere ao snapshot, não apenas aos filtros.
        </p>
      </div>
    </div>
  );
}
