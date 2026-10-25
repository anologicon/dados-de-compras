import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Building2,
  CalendarClock,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Database,
  FileJson,
  Filter,
  Globe2,
  LayoutDashboard,
  ListFilter,
  LoaderCircle,
  MapPin,
  Pause,
  Play,
  Plus,
  Search,
  ShieldCheck,
  Square,
  Table2,
  TriangleAlert,
  X,
} from "lucide-react";
import {
  api,
  useData,
  useDebounce,
  type City,
  type Coverage,
  type LogEvent,
  type Overview,
  type Page,
  type Purchase,
  type RawRecord,
  type Run,
  type Schedule,
  type ServiceStatus,
} from "./api";

import { MunicipalityForm } from "./MunicipalityForm";

type Tab = "overview" | "purchases" | "raw" | "runs" | "schedules";
const titles: Record<Tab, string> = {
  overview: "Visão geral",
  purchases: "Compras",
  raw: "Dados de origem",
  runs: "Coletas",
  schedules: "Agendas",
};
const statuses: Record<string, string> = {
  queued: "Na fila",
  running: "Coletando",
  stopping: "Parando",
  stopped: "Parada",
  interrupted: "Interrompida",
  projecting: "Publicando dados",
  partial: "Parcial",
  finished: "Concluída",
  failed: "Falhou",
};
const int = (v: number) => new Intl.NumberFormat("pt-BR").format(v);
const money = (v: number | null) =>
  v === null
    ? "Não informado"
    : new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
        notation: Math.abs(v) >= 1e6 ? "compact" : "standard",
        maximumFractionDigits: 2,
      }).format(v);
const date = (v: string) =>
  new Date(v.length === 10 ? v + "T12:00:00" : v).toLocaleDateString("pt-BR");
const datetime = (v: string) =>
  new Date(v).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });

function ErrorNotice({ error }: { error: string }) {
  return error ? (
    <div className="notice danger" role="alert">
      <TriangleAlert size={18} />
      <span>{error}</span>
    </div>
  ) : null;
}
function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty">
      <Database size={32} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={22} /> Carregando dados…
    </div>
  );
}
function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status}>{statuses[status] || status}</span>
  );
}
function CoverageNotice({ coverage }: { coverage: Coverage }) {
  return (
    <div
      className={
        "notice " + (coverage.status === "complete" ? "info" : "warning")
      }
    >
      {coverage.status === "complete" ? (
        <ShieldCheck size={20} />
      ) : (
        <TriangleAlert size={20} />
      )}
      <div>
        <strong>
          {coverage.status === "complete"
            ? "Recorte coletado"
            : coverage.status === "partial"
              ? "Cobertura parcial"
              : "Cobertura não verificada"}
        </strong>
        <span>
          {coverage.message}{" "}
          {coverage.unreconciled > 0 &&
            `${int(coverage.unreconciled)} registros sem conciliação segura estão fora dos indicadores.`}
        </span>
      </div>
    </div>
  );
}
function Modal({
  title,
  children,
  close,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={wide ? "wide" : ""}
      onCancel={close}
      aria-label={title}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <button className="icon-button" onClick={close} aria-label="Fechar">
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
function Detail({
  title,
  payload,
  origin,
  close,
}: {
  title: string;
  payload: string;
  origin: string;
  close: () => void;
}) {
  const [part, setPart] = useState("record");
  return (
    <Modal title={title} close={close} wide>
      <div className="detail-tabs">
        <button
          className={part === "record" ? "active" : ""}
          onClick={() => setPart("record")}
        >
          Registro original
        </button>
        <button
          className={part === "origin" ? "active" : ""}
          onClick={() => setPart("origin")}
        >
          Rastreabilidade
        </button>
      </div>
      <pre className="json">
        {JSON.stringify(
          JSON.parse(part === "record" ? payload : origin),
          null,
          2,
        )}
      </pre>
      <p className="muted modal-note">
        Dados de origem preservados. Campos ausentes não são convertidos em
        zero.
      </p>
    </Modal>
  );
}
function Pager({
  page,
  total,
  size,
  setPage,
}: {
  page: number;
  total: number;
  size: number;
  setPage: (n: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {total
          ? `${int((page - 1) * size + 1)}–${int(Math.min(page * size, total))} de ${int(total)}`
          : "Nenhum registro"}
      </span>
      <div>
        <button
          className="icon-button"
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
          aria-label="Página anterior"
        >
          <ChevronLeft size={18} />
        </button>
        <span>Página {page}</span>
        <button
          className="icon-button"
          disabled={page * size >= total}
          onClick={() => setPage(page + 1)}
          aria-label="Próxima página"
        >
          <ChevronRight size={18} />
        </button>
      </div>
    </div>
  );
}

function Dashboard({
  data,
  openPurchases,
}: {
  data: Overview;
  openPurchases: () => void;
}) {
  const m = data.metrics;
  const max = Math.max(1, ...data.monthly.map((x) => x.purchases));
  return (
    <>
      <div className="metrics">
        <Metric
          label="Compras publicadas"
          value={int(m.purchases)}
          note="Registros únicos no recorte"
          icon={<Table2 size={19} />}
        />
        <Metric
          label="Valor estimado"
          value={money(m.estimated)}
          note={`${int(m.estimated_known)} compras com valor informado`}
          icon={<ListFilter size={19} />}
        />
        <Metric
          label="Valor homologado"
          value={money(m.awarded)}
          note={`${int(m.awarded_known)} compras com valor informado`}
          icon={<Check size={19} />}
          accent
        />
        <Metric
          label="Órgãos compradores"
          value={int(m.organizations)}
          note="Unidades localizadas no município"
          icon={<Building2 size={19} />}
        />
      </div>
      <div className="charts">
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Compras ao longo do tempo</h2>
              <p>Quantidade por mês de publicação</p>
            </div>
            <span className="legend">
              <i /> Compras
            </span>
          </div>
          {data.monthly.length ? (
            <div
              className="chart"
              role="img"
              aria-label="Gráfico de compras publicadas por mês"
            >
              {data.monthly.map((x) => (
                <div className="bar-column" key={x.month}>
                  <span className="bar-value">{int(x.purchases)}</span>
                  <div className="bar-space">
                    <div
                      className="bar"
                      style={{
                        height: `${Math.max(2, (x.purchases / max) * 100)}%`,
                      }}
                      title={`${x.month}: ${int(x.purchases)} compras`}
                    />
                  </div>
                  <span className="bar-label">
                    {new Date(x.month + "-15T12:00:00")
                      .toLocaleDateString("pt-BR", { month: "short" })
                      .replace(".", "")}
                    <small>{x.month.slice(0, 4)}</small>
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="Sem compras neste recorte">
              Ajuste os filtros ou confira a cobertura da coleta.
            </Empty>
          )}
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Principais órgãos</h2>
              <p>Por quantidade de compras publicadas</p>
            </div>
            <Building2 size={18} className="muted" />
          </div>
          <div className="org-list">
            {data.organizations.length ? (
              data.organizations.slice(0, 6).map((o, i) => (
                <div className="org-row" key={o.org_name}>
                  <span className="org-rank">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <div className="org-label">
                      <span title={o.org_name}>{o.org_name}</span>
                      <strong>{int(o.purchases)}</strong>
                    </div>
                    <div className="track">
                      <i
                        style={{
                          width: `${(o.purchases / data.organizations[0].purchases) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <p className="muted">Nenhum órgão no recorte.</p>
            )}
          </div>
          <button className="panel-link" onClick={openPurchases}>
            Explorar as compras <ArrowRight size={16} />
          </button>
        </section>
      </div>
      <div className="method-note">
        <CircleHelp size={18} />
        <p>
          <strong>Como ler este panorama</strong> · O recorte é territorial, não
          apenas da prefeitura. Estimado e homologado são medidas distintas: não
          devem ser somados e não representam valores efetivamente pagos.
        </p>
      </div>
    </>
  );
}
function Metric({
  label,
  value,
  note,
  icon,
  accent,
}: {
  label: string;
  value: string;
  note: string;
  icon: ReactNode;
  accent?: boolean;
}) {
  return (
    <section className={"metric " + (accent ? "accent" : "")}>
      <div className="metric-label">
        {label}
        <span>{icon}</span>
      </div>
      <strong>{value}</strong>
      <p>{note}</p>
    </section>
  );
}

function PurchaseList({ city, query }: { city: City; query: string }) {
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<Purchase | null>(null);
  useEffect(() => setPage(1), [query, city.id]);
  const { data, loading, error } = useData<Page<Purchase>>(
    `/cities/${city.id}/purchases?${query}&page=${page}`,
  );
  return (
    <>
      <div className="section-toolbar">
        <div>
          <h2>Compras no recorte</h2>
          <p>
            Conciliação por identificadores explícitos, com prioridade ao PNCP.
          </p>
        </div>
        <div className="actions">
          <a
            className="button secondary"
            href={`/api/cities/${city.id}/export?${query}&format=csv`}
          >
            <ArrowDownToLine size={16} />
            CSV
          </a>
          <a
            className="button secondary"
            href={`/api/cities/${city.id}/export?${query}&format=json`}
          >
            <FileJson size={16} />
            JSON
          </a>
        </div>
      </div>
      <ErrorNotice error={error} />
      {loading ? (
        <Loading />
      ) : (
        data && (
          <section className="panel table-panel">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Objeto da compra</th>
                    <th>Órgão / modalidade</th>
                    <th>Publicação</th>
                    <th className="numeric">Estimado</th>
                    <th className="numeric">Homologado</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((row) => (
                    <tr key={row.purchase_key}>
                      <td>
                        <button
                          className="object-link"
                          onClick={() => setDetail(row)}
                        >
                          {row.description || "Objeto não informado"}
                        </button>
                        <small className="record-id">
                          {row.purchase_key}{" "}
                          <span className="source-tag">
                            {row.family === "pncp" ? "PNCP" : "Legado"}
                          </span>
                        </small>
                      </td>
                      <td>
                        <span className="cell-clamp" title={row.org_name}>
                          {row.org_name}
                        </span>
                        <small>{row.modality}</small>
                      </td>
                      <td className="nowrap">{date(row.published_on)}</td>
                      <td className="numeric nowrap">{money(row.estimated)}</td>
                      <td className="numeric nowrap">{money(row.awarded)}</td>
                      <td>
                        <button
                          className="icon-button"
                          onClick={() => setDetail(row)}
                          aria-label={`Abrir compra ${row.purchase_key}`}
                        >
                          <ArrowUpRight size={17} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!data.items.length && (
              <Empty title="Nenhuma compra encontrada">
                Tente outro período ou termo de busca.
              </Empty>
            )}
            <Pager page={page} total={data.total} size={25} setPage={setPage} />
          </section>
        )
      )}
      {detail && (
        <Detail
          title="Detalhes da compra"
          payload={detail.payload_json}
          origin={detail.origin_json}
          close={() => setDetail(null)}
        />
      )}
    </>
  );
}

function RawExplorer({ city }: { city: City }) {
  const entities = useData<{ entity: string; records: number }[]>(
    `/cities/${city.id}/entities`,
  );
  const [chosen, setChosen] = useState("");
  const [q, setQ] = useState("");
  const search = useDebounce(q);
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<RawRecord | null>(null);
  const entity =
    chosen ||
    (entities.data?.some((x) => x.entity === "pncp_contratacao")
      ? "pncp_contratacao"
      : entities.data?.[0]?.entity || "");
  useEffect(() => setPage(1), [entity, search]);
  const result = useData<Page<RawRecord>>(
    entity
      ? `/cities/${city.id}/records?${new URLSearchParams({ entity, q: search, page: String(page) })}`
      : null,
  );
  return (
    <>
      <p className="intro-note">
        Última versão observada por identidade. Todas as páginas e versões
        originais continuam preservadas no Bronze, inclusive referências de
        outros municípios.
      </p>
      <ErrorNotice error={entities.error || result.error} />
      <div className="explorer">
        <aside className="entity-list">
          <h3>
            Entidades <span>{entities.data?.length || 0}</span>
          </h3>
          {entities.data?.map((e) => (
            <button
              key={e.entity}
              className={entity === e.entity ? "selected" : ""}
              onClick={() => {
                setChosen(e.entity);
                setQ("");
              }}
            >
              <span>{e.entity}</span>
              <small>{int(e.records)}</small>
            </button>
          ))}
        </aside>
        <section className="panel raw-panel">
          <div className="panel-head">
            <div>
              <h2>{entity || "Selecione uma entidade"}</h2>
              <p>{int(result.data?.total || 0)} registros</p>
            </div>
            <label className="search">
              <Search size={17} />
              <input
                aria-label="Buscar no JSON"
                placeholder="Buscar no JSON…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </label>
          </div>
          {result.loading ? (
            <Loading />
          ) : (
            <div className="raw-list">
              {result.data?.items.map((row) => {
                const payload = JSON.parse(row.payload_json);
                return (
                  <button
                    className="raw-item"
                    key={row.id}
                    onClick={() => setDetail(row)}
                  >
                    <FileJson size={20} />
                    <div>
                      <strong>
                        {String(
                          payload.objetoCompra ||
                            payload.nomeRazaoSocialFornecedor ||
                            payload.descricaoResumida ||
                            payload.nomeUasg ||
                            payload.idCompra ||
                            Object.values(payload).find(
                              (v) => typeof v === "string",
                            ) ||
                            "Registro",
                        )}
                      </strong>
                      <code>{JSON.stringify(payload).slice(0, 200)}</code>
                    </div>
                    <ArrowUpRight size={17} />
                  </button>
                );
              })}
              {!result.data?.items.length && (
                <Empty title="Sem registros">
                  A entidade pode não ter retornado dados ou o filtro está muito
                  restritivo.
                </Empty>
              )}
            </div>
          )}
          {result.data && (
            <Pager
              page={page}
              total={result.data.total}
              size={20}
              setPage={setPage}
            />
          )}
        </section>
      </div>
      {detail && (
        <Detail
          title={detail.entity}
          payload={detail.payload_json}
          origin={detail.origin_json}
          close={() => setDetail(null)}
        />
      )}
    </>
  );
}

function RunLogs({ run, close }: { run: Run; close: () => void }) {
  const events = useData<LogEvent[]>(`/runs/${run.id}/events`, 0, 2000);
  return (
    <Modal title={`Coleta · ${run.city_name}`} close={close} wide>
      <div className="modal-note">
        <Badge status={run.status} />
        <span className="muted">
          {" "}
          {date(run.config.start_date)} — {date(run.config.end_date)}
        </span>
      </div>
      <div className="log" aria-label="Eventos da coleta">
        {events.data?.map((e) => (
          <div key={e.id}>
            <time>{new Date(e.created_at).toLocaleTimeString("pt-BR")}</time>
            <span>{e.message}</span>
          </div>
        ))}
        {!events.data?.length && <p>Aguardando eventos da execução.</p>}
      </div>
      <ErrorNotice error={events.error || run.error || ""} />
      {run.result !== null && (
        <details className="modal-note">
          <summary>Resultado técnico</summary>
          <pre className="json">{JSON.stringify(run.result, null, 2)}</pre>
        </details>
      )}
    </Modal>
  );
}
function Runs({
  revision,
  refresh,
  newRun,
}: {
  revision: number;
  refresh: () => void;
  newRun: () => void;
}) {
  const { data, error, loading } = useData<Run[]>("/runs", revision, 2500);
  const [chosen, setChosen] = useState<Run | null>(null);
  const [actionError, setActionError] = useState("");
  const action = async (id: string, operation: string) => {
    try {
      await api(`/runs/${id}/${operation}`, "POST");
      refresh();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };
  const active =
    data?.filter((r) =>
      ["running", "projecting", "stopping"].includes(r.status),
    ).length || 0;
  return (
    <>
      <div className="operation-summary">
        <div>
          <Activity size={22} />
          <span>
            <strong>{active} de 2</strong> municípios em execução
          </span>
        </div>
        <span>Pacing compartilhado: 1 requisição por segundo</span>
      </div>
      <ErrorNotice error={error || actionError} />
      {loading ? (
        <Loading />
      ) : data?.length ? (
        <section className="panel table-panel">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Município / execução</th>
                  <th>Período solicitado</th>
                  <th>Estado</th>
                  <th>Criada em</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {data.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <button
                        className="object-link"
                        onClick={() => setChosen(run)}
                      >
                        {run.city_name} / {run.uf}
                      </button>
                      <small>{run.id.slice(0, 8)}</small>
                    </td>
                    <td>
                      {date(run.config.start_date)} —{" "}
                      {date(run.config.end_date)}
                    </td>
                    <td>
                      <Badge status={run.status} />
                    </td>
                    <td>{datetime(run.created_at)}</td>
                    <td>
                      <div className="actions">
                        <button
                          className="text-button"
                          onClick={() => setChosen(run)}
                        >
                          Eventos <ArrowUpRight size={14} />
                        </button>
                        {["running", "queued"].includes(run.status) && (
                          <button
                            className="icon-button"
                            onClick={() => void action(run.id, "stop")}
                            aria-label="Parar coleta"
                          >
                            <Square size={15} />
                          </button>
                        )}
                        {[
                          "stopped",
                          "failed",
                          "partial",
                          "interrupted",
                        ].includes(run.status) && (
                          <button
                            className="icon-button"
                            onClick={() => void action(run.id, "resume")}
                            aria-label="Retomar coleta"
                          >
                            <Play size={16} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <section className="panel">
          <Empty title="Sua próxima coleta começa aqui">
            Configure um município e período. Você pode fechar a aba: a coleta
            continua enquanto o serviço estiver rodando.
          </Empty>
          <div className="empty-action">
            <button className="button primary" onClick={newRun}>
              <Plus size={16} /> Nova coleta
            </button>
          </div>
        </section>
      )}
      {chosen && (
        <RunLogs
          run={data?.find((r) => r.id === chosen.id) || chosen}
          close={() => setChosen(null)}
        />
      )}
    </>
  );
}
function Schedules({
  revision,
  refresh,
  add,
}: {
  revision: number;
  refresh: () => void;
  add: () => void;
}) {
  const { data, error, loading } = useData<Schedule[]>(
    "/schedules",
    revision,
    10000,
  );
  const [actionError, setActionError] = useState("");
  const toggle = async (s: Schedule) => {
    try {
      await api(`/schedules/${s.id}`, "PATCH", { enabled: !s.enabled });
      refresh();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };
  return (
    <>
      <div className="notice info">
        <CalendarClock size={20} />
        <div>
          <strong>A agenda acompanha o serviço local</strong>
          <span>
            Horários só executam enquanto o serviço estiver rodando. Ao
            reiniciar, horários perdidos são agrupados. A janela móvel não
            atualiza o histórico anterior.
          </span>
        </div>
      </div>
      <div className="section-toolbar">
        <div>
          <h2>Rotinas de atualização</h2>
          <p>
            Pontuais, diárias ou semanais. Sem sobreposição no mesmo município.
          </p>
        </div>
        <button className="button primary" onClick={add}>
          <Plus size={17} /> Nova agenda
        </button>
      </div>
      <ErrorNotice error={error || actionError} />
      {loading ? (
        <Loading />
      ) : data?.length ? (
        <div className="schedule-grid">
          {data.map((s) => (
            <section className="panel schedule-card" key={s.id}>
              <div className="schedule-top">
                <span className="schedule-icon">
                  <CalendarClock size={22} />
                </span>
                <span
                  className={"badge " + (s.enabled ? "finished" : "stopped")}
                >
                  {s.frequency === "once" && s.executed
                    ? "Disparada"
                    : s.enabled
                      ? "Ativa"
                      : "Pausada"}
                </span>
              </div>
              <h3>{s.name}</h3>
              <p>{s.city_name}</p>
              <dl>
                <div>
                  <dt>Frequência</dt>
                  <dd>
                    {s.frequency === "once"
                      ? "Pontual"
                      : s.frequency === "daily"
                        ? "Diária"
                        : "Semanal"}
                    {s.frequency !== "once" ? ` · ${s.local_time}` : ""}
                  </dd>
                </div>
                <div>
                  <dt>Janela móvel</dt>
                  <dd>{s.window_days} dias</dd>
                </div>
                <div>
                  <dt>Fuso</dt>
                  <dd>{s.timezone}</dd>
                </div>
                <div>
                  <dt>
                    {s.frequency === "once" && s.executed
                      ? "Horário agendado"
                      : "Próximo horário"}
                  </dt>
                  <dd>{datetime(s.next_due)}</dd>
                </div>
              </dl>
              {s.frequency === "once" && s.executed ? (
                <p className="muted">Execução única enviada à fila.</p>
              ) : (
                <button
                  className="button secondary"
                  onClick={() => void toggle(s)}
                >
                  {s.enabled ? <Pause size={15} /> : <Play size={15} />}
                  {s.enabled ? "Pausar agenda" : "Ativar agenda"}
                </button>
              )}
            </section>
          ))}
        </div>
      ) : (
        <section className="panel">
          <Empty title="Nenhuma rotina configurada">
            Mantenha o panorama atualizado com coletas recorrentes por
            município.
          </Empty>
        </section>
      )}
    </>
  );
}

function NewCity({
  close,
  done,
}: {
  close: () => void;
  done: (id: string) => void;
}) {
  return (
    <Modal title="Cadastrar município" close={close}>
      <MunicipalityForm close={close} done={done} />
    </Modal>
  );
}
function RunForm({
  cities,
  selected,
  close,
  done,
}: {
  cities: City[];
  selected: string;
  close: () => void;
  done: () => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    const values = Object.fromEntries(new FormData(e.currentTarget));
    try {
      await api("/runs", "POST", values);
      done();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Nova coleta municipal" close={close}>
      <form onSubmit={submit} className="form">
        <p className="muted">
          Fluxo completo de coleta pública: PNCP, legado, contratos,
          fornecedores, catálogos e preços. A execução pode ser longa; falhas e
          limites ficam explícitos.
        </p>
        <label>
          Município
          <select
            name="city_id"
            defaultValue={selected || cities[0]?.id}
            required
          >
            {cities.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name} / {c.uf} · {c.id}
              </option>
            ))}
          </select>
        </label>
        <div className="form-grid">
          <label>
            Publicação a partir de
            <input
              name="start_date"
              type="date"
              required
              defaultValue="2026-01-01"
            />
          </label>
          <label>
            Até
            <input
              name="end_date"
              type="date"
              required
              defaultValue="2026-01-31"
            />
          </label>
        </div>
        <div className="notice info">
          <ShieldCheck size={19} />
          <span>
            Base isolada por município. Reconsultas preservam o Bronze e não
            devem duplicar os indicadores.
          </span>
        </div>
        <ErrorNotice error={error} />
        <div className="form-actions">
          <button type="button" className="button secondary" onClick={close}>
            Cancelar
          </button>
          <button className="button primary" disabled={busy || !cities.length}>
            {busy ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <Play size={16} />
            )}
            Adicionar à fila
          </button>
        </div>
      </form>
    </Modal>
  );
}
function ScheduleForm({
  cities,
  selected,
  close,
  done,
}: {
  cities: City[];
  selected: string;
  close: () => void;
  done: () => void;
}) {
  const [frequency, setFrequency] = useState("daily");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    const f = new FormData(e.currentTarget);
    const values: Record<string, unknown> = Object.fromEntries(f);
    values.window_days = Number(f.get("window_days"));
    if (frequency === "weekly") values.weekday = Number(f.get("weekday"));
    if (frequency === "once") {
      values.due_at = new Date(String(f.get("due_at"))).toISOString();
      values.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    }
    try {
      await api("/schedules", "POST", values);
      done();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Nova agenda" close={close}>
      <form className="form" onSubmit={submit}>
        <label>
          Nome da rotina
          <input
            name="name"
            required
            minLength={2}
            maxLength={100}
            placeholder="Ex.: Atualização de Brusque"
          />
        </label>
        <label>
          Município
          <select name="city_id" defaultValue={selected || cities[0]?.id}>
            {cities.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} / {c.uf}
              </option>
            ))}
          </select>
        </label>
        <div className="form-grid">
          <label>
            Frequência
            <select
              name="frequency"
              value={frequency}
              onChange={(e) => setFrequency(e.target.value)}
            >
              <option value="once">Pontual</option>
              <option value="daily">Diária</option>
              <option value="weekly">Semanal</option>
            </select>
          </label>
          <label>
            Janela recente (dias)
            <input
              name="window_days"
              type="number"
              min={1}
              max={3650}
              defaultValue={90}
              required
            />
          </label>
        </div>
        {frequency === "once" ? (
          <label>
            Data e hora (no fuso do navegador)
            <input name="due_at" type="datetime-local" required />
          </label>
        ) : (
          <>
            <div className="form-grid">
              <label>
                Horário
                <input
                  name="local_time"
                  type="time"
                  defaultValue="02:00"
                  required
                />
              </label>
              {frequency === "weekly" && (
                <label>
                  Dia da semana
                  <select name="weekday">
                    {[
                      "Segunda",
                      "Terça",
                      "Quarta",
                      "Quinta",
                      "Sexta",
                      "Sábado",
                      "Domingo",
                    ].map((d, i) => (
                      <option key={d} value={i}>
                        {d}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
            <label>
              Fuso horário
              <input
                name="timezone"
                defaultValue={Intl.DateTimeFormat().resolvedOptions().timeZone}
                required
              />
            </label>
          </>
        )}
        <p className="muted">
          Alterações anteriores à janela não serão reconsultadas
          automaticamente. Agendas dependem do serviço local ativo.
        </p>
        <ErrorNotice error={error} />
        <div className="form-actions">
          <button type="button" className="button secondary" onClick={close}>
            Cancelar
          </button>
          <button className="button primary" disabled={busy || !cities.length}>
            {busy && <LoaderCircle size={16} className="spin" />}Criar agenda
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [cityId, setCityId] = useState("");
  const [revision, setRevision] = useState(0);
  const refresh = () => setRevision((r) => r + 1);
  const cities = useData<City[]>("/cities", revision, 10000);
  const service = useData<ServiceStatus>("/status", 0, 10000);
  const city = cities.data?.find((c) => c.id === cityId) || cities.data?.[0];
  const [dialog, setDialog] = useState<"city" | "run" | "schedule" | null>(
    null,
  );
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [q, setQ] = useState("");
  const [modality, setModality] = useState("");
  const [org, setOrg] = useState("");
  const [more, setMore] = useState(false);
  const search = useDebounce(q);
  const query = new URLSearchParams(
    Object.fromEntries(
      Object.entries({
        start_date: start,
        end_date: end,
        q: search,
        modality,
        org_name: org,
      }).filter(([, v]) => v),
    ),
  ).toString();
  const overview = useData<Overview>(
    city?.has_snapshot ? `/cities/${city.id}/overview?${query}` : null,
    revision + (city?.snapshot_at ? new Date(city.snapshot_at).getTime() : 0),
  );
  const changeCity = (id: string) => {
    setCityId(id);
    setStart("");
    setEnd("");
    setQ("");
    setModality("");
    setOrg("");
  };
  const navigate = (target: Tab) => setTab(target);
  const analyzing = ["overview", "purchases", "raw"].includes(tab);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("overview");
          }}
        >
          <span className="brand-mark">
            <Building2 size={25} />
          </span>
          <span>
            compras<span className="brand-sub">OBSERVATÓRIO LOCAL</span>
          </span>
        </a>
        <div className="workspace-label">
          <span className="workspace-dot" /> Ambiente pessoal{" "}
          <ShieldCheck size={14} />
        </div>
        <nav aria-label="Navegação principal">
          <p>EXPLORAR</p>
          {(
            [
              { id: "overview", icon: LayoutDashboard },
              { id: "purchases", icon: Table2 },
              { id: "raw", icon: Database },
            ] as const
          ).map((n) => (
            <button
              key={n.id}
              className={tab === n.id ? "active" : ""}
              aria-current={tab === n.id ? "page" : undefined}
              onClick={() => navigate(n.id)}
            >
              <n.icon size={19} />
              {titles[n.id]}
              {tab === n.id && <span className="nav-dot" />}
            </button>
          ))}
          <p>OPERAÇÃO</p>
          {(
            [
              { id: "runs", icon: Activity },
              { id: "schedules", icon: CalendarClock },
            ] as const
          ).map((n) => (
            <button
              key={n.id}
              className={tab === n.id ? "active" : ""}
              aria-current={tab === n.id ? "page" : undefined}
              onClick={() => navigate(n.id)}
            >
              <n.icon size={19} />
              {titles[n.id]}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-status">
            <span
              className={
                service.error || service.data?.error
                  ? "status-dot warn"
                  : "status-dot"
              }
            />
            <span>
              {service.error ? "Serviço indisponível" : "Serviço local ativo"}
            </span>
          </div>
          <p>
            Seus dados ficam nesta máquina.
            <br />
            Nenhum servidor externo de análise.
          </p>
          <span className="version">
            COMPRAS.GOV.BR <ArrowUpRight size={12} />
          </span>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Observatório <ChevronRight size={14} />
            <strong>{titles[tab]}</strong>
          </div>
          <div className="topbar-right">
            <span className="local-pill">
              <ShieldCheck size={14} /> Uso local
            </span>
            <span className="avatar">EU</span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <span className="eyebrow">DADOS PÚBLICOS, CONTEXTO CLARO</span>
              <h1>
                {titles[tab]}
                <span className="title-dot">.</span>
              </h1>
              <p>
                {tab === "overview"
                  ? "Entenda as compras públicas do seu município."
                  : tab === "purchases"
                    ? "Do panorama ao registro original, sem perder a origem."
                    : tab === "raw"
                      ? "Inspecione entidades, campos e a origem de cada registro."
                      : tab === "runs"
                        ? "Acompanhe o que está sendo coletado e o que precisa de atenção."
                        : "Organize a próxima atualização dos seus dados."}
              </p>
            </div>
            <button
              className="button primary"
              onClick={() => setDialog(cities.data?.length ? "run" : "city")}
            >
              <Plus size={18} />
              {cities.data?.length ? "Nova coleta" : "Cadastrar município"}
            </button>
          </div>
          <ErrorNotice
            error={cities.error || service.error || service.data?.error || ""}
          />
          <div className="context-bar">
            <div className="city-selector">
              <MapPin size={19} />
              <label>
                <span>Município</span>
                <select
                  aria-label="Município selecionado"
                  value={city?.id || ""}
                  onChange={(e) => changeCity(e.target.value)}
                >
                  {!cities.data?.length && (
                    <option value="">Nenhum cadastrado</option>
                  )}
                  {cities.data?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} / {c.uf}
                    </option>
                  ))}
                </select>
              </label>
              <ChevronDown size={15} />
              <button
                className="icon-button"
                aria-label="Cadastrar município"
                onClick={() => setDialog("city")}
              >
                <Plus size={17} />
              </button>
            </div>
            <div className="snapshot-info">
              <Database size={15} />
              {city?.snapshot_at ? (
                <>
                  Projeção publicada em{" "}
                  <strong>{datetime(city.snapshot_at)}</strong>
                </>
              ) : (
                "Aguardando primeira coleta ou importação"
              )}
            </div>
          </div>
          {analyzing && city?.has_snapshot && (
            <>
              {tab !== "raw" && (
                <div className="filters">
                  <label className="search">
                    <Search size={17} />
                    <input
                      aria-label="Buscar compras"
                      placeholder="Busque por objeto, órgão ou identificador…"
                      value={q}
                      onChange={(e) => setQ(e.target.value)}
                    />
                  </label>
                  <div className="date-filters">
                    <input
                      type="date"
                      aria-label="Publicação inicial"
                      value={start}
                      onChange={(e) => setStart(e.target.value)}
                    />
                    <span>até</span>
                    <input
                      type="date"
                      aria-label="Publicação final"
                      value={end}
                      onChange={(e) => setEnd(e.target.value)}
                    />
                  </div>
                  <button
                    className={"button secondary " + (more ? "selected" : "")}
                    onClick={() => setMore(!more)}
                  >
                    <Filter size={16} />
                    Filtros
                  </button>
                  {(q || start || end || modality || org) && (
                    <button
                      className="text-button"
                      onClick={() => {
                        setQ("");
                        setStart("");
                        setEnd("");
                        setModality("");
                        setOrg("");
                      }}
                    >
                      Limpar
                    </button>
                  )}
                </div>
              )}
              {more && tab !== "raw" && (
                <div className="extra-filters">
                  <label>
                    Modalidade
                    <select
                      value={modality}
                      onChange={(e) => setModality(e.target.value)}
                    >
                      <option value="">Todas as modalidades</option>
                      {overview.data?.modalities.map((m) => (
                        <option key={m.modality}>{m.modality}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Órgão
                    <select
                      value={org}
                      onChange={(e) => setOrg(e.target.value)}
                    >
                      <option value="">Todos os órgãos</option>
                      {overview.data?.orgs.map((o) => (
                        <option key={o.org_name}>{o.org_name}</option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
              {overview.data && (
                <CoverageNotice coverage={overview.data.coverage} />
              )}
              <ErrorNotice error={overview.error} />
            </>
          )}
          {cities.loading ? (
            <Loading />
          ) : analyzing ? (
            !city?.has_snapshot ? (
              <section className="panel">
                <Empty title="Pronto para receber seus dados">
                  Cadastre um município e inicie uma coleta. Para usar dados
                  existentes, importe o Bronze com o comando compras-crawler
                  web-import.
                </Empty>
              </section>
            ) : tab === "overview" ? (
              overview.loading ? (
                <Loading />
              ) : (
                overview.data && (
                  <Dashboard
                    data={overview.data}
                    openPurchases={() => navigate("purchases")}
                  />
                )
              )
            ) : tab === "purchases" ? (
              <PurchaseList city={city} query={query} />
            ) : (
              <RawExplorer key={city.id + city.snapshot_at} city={city} />
            )
          ) : tab === "runs" ? (
            <Runs
              revision={revision}
              refresh={refresh}
              newRun={() => setDialog(cities.data?.length ? "run" : "city")}
            />
          ) : (
            <Schedules
              revision={revision}
              refresh={refresh}
              add={() => setDialog(cities.data?.length ? "schedule" : "city")}
            />
          )}
          <footer className="page-footer">
            <span>
              <Globe2 size={14} /> Fonte: dados abertos do Compras.gov.br
            </span>
            <span>Origem preservada. Cobertura explícita.</span>
          </footer>
        </main>
      </div>
      {dialog === "city" && (
        <NewCity
          close={() => setDialog(null)}
          done={(id) => {
            refresh();
            changeCity(id);
            setDialog(null);
          }}
        />
      )}
      {dialog === "run" && (
        <RunForm
          cities={cities.data || []}
          selected={city?.id || ""}
          close={() => setDialog(null)}
          done={() => {
            setDialog(null);
            refresh();
            navigate("runs");
          }}
        />
      )}
      {dialog === "schedule" && (
        <ScheduleForm
          cities={cities.data || []}
          selected={city?.id || ""}
          close={() => setDialog(null)}
          done={() => {
            setDialog(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}
