import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  LoaderCircle,
  RefreshCw,
  TriangleAlert,
  UserRound,
} from "lucide-react";
import {
  useData,
  type City,
  type EvidenceLink,
  type ItemResult,
  type Page,
  type Purchase,
  type PurchaseDetail,
  type PurchaseItem,
  type RecordSource,
  type SupplierDetail,
} from "./api";
import { date, datetime, int, money } from "./format";
import { Pager } from "./Pager";

const quantity = (value: number | null) =>
  value === null ? "Não informado" : int(value);
const boolean = (value: boolean | null) =>
  value === null ? "Não informado" : value ? "Sim" : "Não";
const pretty = (value: string) => {
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
};

function RequestState({ loading, error }: { loading: boolean; error: string }) {
  if (error)
    return (
      <div className="notice danger" role="alert">
        <TriangleAlert size={18} />
        <span>{error}</span>
      </div>
    );
  if (loading)
    return (
      <div className="loading" role="status">
        <LoaderCircle size={20} className="spin" />
        Carregando vínculos…
      </div>
    );
  return null;
}

function Fields({ values }: { values: [string, ReactNode][] }) {
  return (
    <dl className="record-fields">
      {values.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value ?? "Não informado"}</dd>
        </div>
      ))}
    </dl>
  );
}

function Evidence({ label, value }: { label: string; value: EvidenceLink }) {
  const labels = {
    confirmed: "Confirmado",
    ambiguous: "Ambíguo",
    missing: "Não encontrado",
  };
  return (
    <details
      className={"relation " + value.status}
      open={value.status !== "confirmed"}
    >
      <summary>
        <span
          className={
            "badge " + (value.status === "confirmed" ? "finished" : "partial")
          }
        >
          {labels[value.status]}
        </span>{" "}
        Vínculo com {label}
      </summary>
      <p>
        {value.reason}
        {value.evidence.length > 0 && (
          <>
            {" "}
            Evidência: <code>{value.evidence.join(" + ")}</code>.
          </>
        )}
      </p>
    </details>
  );
}

function Source({ record }: { record: RecordSource }) {
  return (
    <details className="source-record">
      <summary>Ver registro e proveniência</summary>
      <p className="muted">
        Conteúdo original preservado; pode conter documentos de pessoa física.
      </p>
      <h4>Registro original</h4>
      <pre className="json">{pretty(record.payload_json)}</pre>
      <h4>Proveniência</h4>
      <pre className="json">{pretty(record.origin_json)}</pre>
    </details>
  );
}

type Scope = { base: string; purchaseKey: string; snapshot: string };

function Items({
  base,
  purchaseKey,
  snapshot,
  onResults,
}: Scope & { onResults: (item: PurchaseItem) => void }) {
  const [page, setPage] = useState(1);
  const result = useData<Page<PurchaseItem>>(
    `${base}/purchase-items?${new URLSearchParams({ snapshot, page: String(page), purchase_key: purchaseKey })}`,
  );
  return (
    <>
      <p className="exploration-note">
        Itens observados neste snapshot. Ausência de registros não comprova que
        a compra não tenha itens.
      </p>
      <RequestState loading={result.loading} error={result.error} />
      {result.data && (
        <>
          <div className="connected-records">
            {result.data.items.map((item) => (
              <article className="connected-card" key={item.id}>
                <div className="connected-card-head">
                  <div>
                    <span className="section-kicker">
                      ITEM {item.item_number ?? "SEM NÚMERO"}
                    </span>
                    <h3>{item.description || "Descrição não informada"}</h3>
                  </div>
                  {item.status && <span className="badge">{item.status}</span>}
                </div>
                <Fields
                  values={[
                    ["Catálogo", item.catalog_code],
                    [
                      "Tipo",
                      item.item_type === "M"
                        ? "Material"
                        : item.item_type === "S"
                          ? "Serviço"
                          : item.item_type,
                    ],
                    ["Unidade", item.unit],
                    ["Quantidade", quantity(item.quantity)],
                    [
                      "Estimado unitário",
                      money(item.estimated_unit_price, false),
                    ],
                    ["Resultados vinculados", int(item.confirmed_results)],
                  ]}
                />
                {item.identity_status === "unverified" && (
                  <p className="notice warning">
                    Sem identidade de negócio estável no snapshot; versões podem
                    aparecer como registros distintos.
                  </p>
                )}
                <Evidence label="a compra" value={item.purchase_link} />
                <button
                  className="button secondary"
                  disabled={item.purchase_link.status !== "confirmed"}
                  onClick={() => onResults(item)}
                >
                  Ver resultados do item {item.item_number ?? "sem número"}
                  <ArrowRight size={15} />
                </button>
                <Source record={item} />
              </article>
            ))}
          </div>
          {!result.data.total && (
            <div className="chart-empty">
              Nenhum item vinculado neste snapshot.
              <span>Verifique a cobertura ou consulte os dados de origem.</span>
            </div>
          )}
          <Pager
            page={page}
            total={result.data.total}
            size={20}
            setPage={setPage}
          />
        </>
      )}
    </>
  );
}

function Results({
  base,
  purchaseKey,
  snapshot,
  item,
  allResults,
}: Scope & {
  item: PurchaseItem | null;
  allResults: () => void;
}) {
  const [page, setPage] = useState(1);
  const [supplierResult, onSupplier] = useState<ItemResult | null>(null);
  const params = new URLSearchParams({
    snapshot,
    page: String(page),
    purchase_key: purchaseKey,
  });
  if (item) params.set("item_record_id", item.id);
  const result = useData<Page<ItemResult>>(
    `${base}/purchase-results?${params}`,
  );
  if (supplierResult)
    return (
      <Supplier
        key={supplierResult.id}
        base={base}
        purchaseKey={purchaseKey}
        snapshot={snapshot}
        result={supplierResult}
        back={() => onSupplier(null)}
      />
    );
  return (
    <>
      {item && (
        <div className="item-context">
          <span>
            Item {item.item_number ?? "sem número"} · {item.description}
          </span>
          <button className="text-button" onClick={allResults}>
            Todos os resultados da compra
          </button>
        </div>
      )}
      <p className="exploration-note">
        Registros de resultado não equivalem a pagamentos nem a todos os
        participantes da disputa. Cancelamentos e vínculos não confirmados
        permanecem explícitos.
      </p>
      <RequestState loading={result.loading} error={result.error} />
      {result.data && (
        <>
          <div className="connected-records">
            {result.data.items.map((row) => (
              <article className="connected-card result-card" key={row.id}>
                <div className="connected-card-head">
                  <div>
                    <span className="section-kicker">
                      RESULTADO {row.sequence ?? "SEM SEQUENCIAL"} · ITEM{" "}
                      {row.item_number ?? "SEM NÚMERO"}
                    </span>
                    {row.supplier.can_open ? (
                      <button
                        className="supplier-link"
                        onClick={() => onSupplier(row)}
                      >
                        <UserRound size={19} />
                        {row.supplier.name}
                        <ArrowRight size={16} />
                      </button>
                    ) : (
                      <h3>{row.supplier.name}</h3>
                    )}
                    <p className="muted">{row.supplier.identifier}</p>
                  </div>
                  {(row.status || row.cancelled) && (
                    <span
                      className={"badge " + (row.cancelled ? "partial" : "")}
                    >
                      {row.cancelled ? "Cancelado" : row.status}
                    </span>
                  )}
                </div>
                <Fields
                  values={[
                    ["Quantidade homologada", quantity(row.quantity)],
                    ["Homologado unitário", money(row.unit_price, false)],
                    ["Homologado do resultado", money(row.total, false)],
                  ]}
                />
                {row.identity_status === "unverified" && (
                  <p className="notice warning">
                    Sem identidade de negócio estável no snapshot; versões podem
                    aparecer como registros distintos.
                  </p>
                )}
                <Evidence label="a compra" value={row.purchase_link} />
                <Evidence label="o item" value={row.item_link} />
                {row.supplier.can_open ? (
                  <button
                    className="button secondary"
                    onClick={() => onSupplier(row)}
                  >
                    Ver fornecedor
                    <UserRound size={15} />
                  </button>
                ) : (
                  <p className="exploration-note">
                    Navegação cadastral indisponível: documento não conciliável
                    ou vínculo com a compra não confirmado. Não fazemos
                    associação por nome.
                  </p>
                )}
                <Source record={row} />
              </article>
            ))}
          </div>
          {!result.data.total && (
            <div className="chart-empty">
              Nenhum resultado vinculado neste snapshot.
              <span>
                Isso não significa que não exista fornecedor ou resultado na
                fonte.
              </span>
            </div>
          )}
          <Pager
            page={page}
            total={result.data.total}
            size={20}
            setPage={setPage}
          />
        </>
      )}
    </>
  );
}

function Supplier({
  base,
  purchaseKey,
  snapshot,
  result,
  back,
}: Scope & { result: ItemResult; back: () => void }) {
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({
    purchase_key: purchaseKey,
    snapshot,
    result_id: result.id,
    page: String(page),
  });
  const detail = useData<SupplierDetail>(`${base}/supplier-detail?${params}`);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  const statuses = {
    confirmed: "Cadastro vinculado",
    ambiguous: "Cadastro ambíguo",
    missing: "Sem cadastro neste snapshot",
  };
  return (
    <section className="supplier-profile" aria-label="Perfil do fornecedor">
      <button className="text-button" onClick={back}>
        <ArrowLeft size={16} />
        Voltar aos resultados
      </button>
      <h3 ref={heading} tabIndex={-1}>
        Perfil do fornecedor
      </h3>
      <h4 className="supplier-name">{result.supplier.name}</h4>
      <p>
        {result.supplier.kind?.toUpperCase()} informado:{" "}
        {result.supplier.identifier}
      </p>
      <p className="exploration-note">
        Nome observado no resultado desta compra. O cadastro abaixo é uma
        referência local e pode ter outro nome ou endereço; não prova
        localização nem situação atual do fornecedor.
      </p>
      <RequestState loading={detail.loading} error={detail.error} />
      {detail.data && (
        <>
          <div
            className={
              "notice " +
              (detail.data.registration_status === "confirmed"
                ? "info"
                : "warning")
            }
          >
            <div>
              <strong>{statuses[detail.data.registration_status]}</strong>
              <span>
                {detail.data.registration_status === "missing"
                  ? "O documento identifica o fornecedor no resultado, mas não há cadastro correspondente neste snapshot."
                  : detail.data.registration_status === "ambiguous"
                    ? "Há múltiplos cadastros ou documentos conflitantes. Nenhum cadastro foi escolhido automaticamente."
                    : "Documento completo e tipo compatíveis. Não houve consulta externa nem associação por nome."}
              </span>
            </div>
          </div>
          {detail.data.registrations.items.map((record) => (
            <article
              className="connected-card registration-card"
              key={record.id}
            >
              <h4>Nome no cadastro: {record.name ?? "Não informado"}</h4>
              <Fields
                values={[
                  ["Atividade (CNAE)", record.cnae],
                  ["Porte", record.size],
                  ["Município do cadastro", record.municipality],
                  ["UF do cadastro", record.uf],
                  ["Ativo no cadastro", boolean(record.active)],
                  [
                    "Habilitado a licitar no cadastro",
                    boolean(record.eligible),
                  ],
                  ["Observado em", datetime(record.fetched_at)],
                ]}
              />
              {record.identity_conflict && (
                <p className="notice warning">
                  Cadastro com documentos conflitantes; vínculo não confirmado.
                </p>
              )}
              <Source record={record} />
            </article>
          ))}
          {detail.data.registrations.total > 0 && (
            <Pager
              page={page}
              total={detail.data.registrations.total}
              size={10}
              setPage={setPage}
            />
          )}
          <h4 className="source-heading">Evidência no resultado</h4>
          <Source record={detail.data.result} />
        </>
      )}
    </section>
  );
}

type Part = "summary" | "items" | "results" | "original" | "origin";
export function PurchaseExplorer({
  city,
  purchase,
}: {
  city: City;
  purchase: Purchase;
}) {
  const [part, setPart] = useState<Part>("summary");
  const [revision, setRevision] = useState(0);
  const [item, setItem] = useState<PurchaseItem | null>(null);
  const base = `/cities/${city.id}`;
  const detail = useData<PurchaseDetail>(
    `${base}/purchase-detail?${new URLSearchParams({ purchase_key: purchase.purchase_key })}`,
    revision,
  );
  const record = detail.data?.purchase ?? purchase;
  const oldService = detail.error === "Not Found";
  const choose = (target: Part) => {
    setPart(target);
    setItem(null);
  };
  const summary = detail.data?.summary;
  const tabs: { id: Part; label: string; needsData?: boolean }[] = [
    { id: "summary", label: "Resumo" },
    {
      id: "items",
      label: `Itens${summary ? ` (${int(summary.item_records)})` : ""}`,
      needsData: true,
    },
    {
      id: "results",
      label: `Resultados${summary ? ` (${int(summary.result_records)})` : ""}`,
      needsData: true,
    },
    { id: "original", label: "Registro original" },
    { id: "origin", label: "Rastreabilidade" },
  ];
  return (
    <div className="purchase-explorer">
      <div className="exploration-context">
        <span>
          <Building2 size={15} />
          {city.name} / {city.uf}
        </span>
        <button
          className="text-button"
          onClick={() => {
            choose("summary");
            setRevision((r) => r + 1);
          }}
        >
          <RefreshCw size={14} />
          Atualizar ficha
        </button>
      </div>
      <div
        className="detail-tabs"
        role="group"
        aria-label="Seções da ficha de compra"
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={part === tab.id ? "active" : ""}
            aria-pressed={part === tab.id}
            disabled={tab.needsData && !detail.data}
            onClick={() => choose(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="purchase-explorer-body">
        {oldService ? (
          <div className="notice warning" role="status">
            <TriangleAlert size={18} />
            <div>
              <strong>Explorador indisponível nesta versão do serviço</strong>
              <span>
                Resumo e origem continuam disponíveis. Reinicie o backend após
                concluir as coletas para liberar os vínculos entre entidades.
              </span>
            </div>
          </div>
        ) : (
          <RequestState loading={detail.loading} error={detail.error} />
        )}
        {detail.data && (
          <p className="snapshot-caption">
            Snapshot de {datetime(detail.data.snapshot)} ·{" "}
            {detail.data.coverage.status === "complete"
              ? "Recorte coletado"
              : detail.data.coverage.status === "partial"
                ? "Cobertura parcial"
                : "Cobertura não verificada"}
            . {detail.data.coverage.message}
          </p>
        )}
        {part === "original" || part === "origin" ? (
          <>
            <pre className="json">
              {pretty(
                part === "original" ? record.payload_json : record.origin_json,
              )}
            </pre>
            <p className="exploration-note">
              Dados de origem preservados. Campos ausentes não são convertidos
              em zero.
            </p>
          </>
        ) : part === "summary" ? (
          <>
            <span className="section-kicker">
              ÓRGÃO → COMPRA → ITEM → RESULTADO → FORNECEDOR
            </span>
            <h3 className="purchase-object">
              {record.description || "Objeto não informado"}
            </h3>
            <p className="record-id">
              {record.purchase_key} ·{" "}
              {record.family === "pncp" ? "PNCP" : "Legado"}
            </p>
            <Fields
              values={[
                ["Órgão comprador", record.org_name],
                ["Modalidade", record.modality],
                ["Publicação", date(record.published_on)],
                ["Valor estimado", money(record.estimated, false)],
                ["Valor homologado", money(record.awarded, false)],
              ]}
            />
            {summary && (
              <>
                <div className="relationship-metrics">
                  <button onClick={() => choose("items")}>
                    <strong>{int(summary.confirmed_items)}</strong>
                    <span>itens com compra confirmada</span>
                  </button>
                  <button onClick={() => choose("results")}>
                    <strong>{int(summary.confirmed_results)}</strong>
                    <span>resultados com compra confirmada</span>
                  </button>
                  <div>
                    <strong>
                      {int(summary.ambiguous_items + summary.ambiguous_results)}
                    </strong>
                    <span>registros com vínculos ambíguos</span>
                  </div>
                </div>
                <p className="exploration-note">
                  {int(summary.results_without_item)} registros de resultado sem
                  item confirmado. As contagens representam registros
                  observados, não pagamentos nem garantia de cobertura completa.
                  Um resultado pode ter compra confirmada e item ambíguo.
                </p>
                <div className="actions">
                  <button
                    className="button primary"
                    onClick={() => choose("items")}
                  >
                    Explorar itens
                    <ArrowRight size={16} />
                  </button>
                  <button
                    className="button secondary"
                    onClick={() => choose("results")}
                  >
                    Ver todos os resultados
                  </button>
                </div>
              </>
            )}
            <p className="exploration-note">
              Este ciclo conecta itens e resultados PNCP por identificadores
              explícitos, sem inferir vínculos por descrição, órgão ou catálogo.
              Estimado e homologado não são valores pagos.
            </p>
          </>
        ) : detail.data && part === "items" ? (
          <Items
            key={detail.data.snapshot}
            base={base}
            purchaseKey={record.purchase_key}
            snapshot={detail.data.snapshot}
            onResults={(selected) => {
              setItem(selected);
              setPart("results");
            }}
          />
        ) : detail.data && part === "results" ? (
          <Results
            key={(item?.id ?? "all") + detail.data.snapshot}
            base={base}
            purchaseKey={record.purchase_key}
            snapshot={detail.data.snapshot}
            item={item}
            allResults={() => setItem(null)}
          />
        ) : null}
      </div>
    </div>
  );
}
