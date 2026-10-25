# UL-01 — proposta de contrato lógico de armazenamento

**Estado: proposta documental não implementada; especificação não executada.**
Ciclo `evo-b42e05820fce`, base de evidência
`ef8a7fff9cb5f22ac6d0f4f9f2e9b0ed979a23e3`, `permissions=[]`.

Este documento separa o armazenamento atual de uma possível **base lógica única**
para CLI, web e MCP. Os contextos atuais não constituem essa base integrada:
selecionar caminhos coincidentes não unifica identidade, populações, precedência
ou protocolo de publicação. Base lógica compartilhada não implica arquivo físico
único. Nenhum descritor, catálogo, adaptador, backend ou camada é criado aqui.
Parquet e um DuckDB único são alternativas, não decisões aprovadas neste ciclo.

Convenções: **[Fato]** é leitura estática verificável na base acima; **[Inferência]**
é consequência possível sem reprodução; **[Proposta]** é requisito ou alternativa
pendente, nunca comportamento implementado. Os caminhos são ilustrações textuais:
nenhum `/tmp/sintetico` foi aberto/criado; nenhuma base existente foi acessada.

## 1. Mapa atual: argumentos → persistência → leitura

Todas as referências `src/compras_crawler/...:linha` abaixo foram conferidas na
lane. Não são evidência de execução ou de conteúdo de uma base real.

| Fluxo | Entrada e resolução atuais [Fato] | Persistência/consumo atuais [Fato] |
| --- | --- | --- |
| CLI `sync` | `--db-path` é prefixo, com overrides `--bronze-db-path` e `--ops-db-path` (`src/compras_crawler/cli.py:44-52`); `main` os repassa a `SyncConfig` (`src/compras_crawler/cli.py:253-289`). `SyncConfig` deriva os omitidos (`src/compras_crawler/sync.py:54-57`). | `build_runner` escolhe sync/async (`src/compras_crawler/sync.py:536-539`), chamado em `src/compras_crawler/cli.py:297-299`. `SyncRunner` usa `DuckWarehouse` e `SqliteOpsStore` (`src/compras_crawler/sync.py:144-157`); o alias é Bronze-only (`src/compras_crawler/storage.py:105`). Página Bronze primeiro, checkpoint SQLite depois (`src/compras_crawler/sync.py:289-303`); não há snapshot web automático nessa sequência. |
| CLI `full-city` | CLI tem prefixo padrão `dados_abertos_compras_full_city` e overrides Bronze/Ops (`src/compras_crawler/cli.py:84-90`); repassa-os a `FullCityConfig` e chama o crawler (`src/compras_crawler/cli.py:192-232`). A classe, quando usada diretamente, tem `DEFAULT_DB_PREFIX`, não aquele default específico da CLI (`src/compras_crawler/full_city.py:33-35,60-64`). | `FullCityCrawler` associa Bronze, `CrawlState` no mesmo DuckDB e Ops SQLite (`src/compras_crawler/full_city.py:115-132`). A chave de retomada inclui coleção (ou `cli`), URL, município/UF, datas, job, endpoint, parâmetros e paginação (`src/compras_crawler/full_city.py:460-469`). Confirma via `commit_page`, depois espelha checkpoint Ops (`src/compras_crawler/full_city.py:498-501`); a CLI relata o resultado, não chama `build_snapshot`. |
| Web gerenciada | `web --workspace` seleciona a raiz (`src/compras_crawler/cli.py:27-30,148-158`). `create_app` constrói `AppStore`/`Service`, inicializados no lifespan (`src/compras_crawler/web/app.py:23-40`); enqueue persiste config com cidade (`src/compras_crawler/web/app.py:115-119`). `Service.tick` reclama o run e lança worker (`src/compras_crawler/web/runtime.py:114-137`). | Controle em `<workspace>/app.sqlite`, com cidades, agendas, runs, eventos, gate e serviço (`src/compras_crawler/web/store.py:52-105`). `city_dir` é `<workspace>/cities/<IBGE>` (`src/compras_crawler/web/store.py:110-114`). Worker obtém `writer.lock`, passa Bronze/Ops explícitos, município/UF, datas e `collection_id` ao full-city e só depois constrói snapshot (`src/compras_crawler/web/worker.py:25-59`). Dados em `cities/<IBGE>/bronze.duckdb` e `cities/<IBGE>/ops.sqlite`; snapshots em `cities/<IBGE>/snapshots/<uuid>.duckdb` (`src/compras_crawler/web/analytics.py:102-115`). |
| Leituras web | Endpoints panorama/compras/entidades/registros delegam a analytics (`src/compras_crawler/web/app.py:157-177`). | Analytics abre o snapshot apontado em `cities.snapshot`, read-only (`src/compras_crawler/web/analytics.py:216-230`). Panorama e compras usam `purchases`; entidades e registros usam `records` (`src/compras_crawler/web/analytics.py:251-292`), não a população histórica completa do Bronze. |
| MCP, direto ou pela CLI | `mcp` delega antes do carregamento de dotenv da CLI (`src/compras_crawler/cli.py:141-146`). `add_arguments` recebe um **arquivo DuckDB existente**, default `compras.duckdb`, Ops opcional e project root; `run_from_args` passa esses argumentos ao servidor stdio (`src/compras_crawler/mcp_server.py:127-138`). | `create_server` constrói `ProjectAccess` (`src/compras_crawler/mcp_server.py:15-28`); entidades/registros e runs/checkpoints/erros delegam ao acesso (`src/compras_crawler/mcp_server.py:67-103`). DuckDB e Ops são lidos separadamente; não há resolução automática do workspace web nem do ponteiro de snapshot. Bronze/legado usam conexão read-only, Ops usa SQLite `mode=ro` (`src/compras_crawler/project_access.py:88-124`). |

### 1.1 Defaults distintos, não alterados

**[Fato]** `derive_bronze_db_path` e `derive_ops_db_path`
(`src/compras_crawler/storage.py:23-37`) transformam o prefixo ilustrativo
`/tmp/sintetico/base` em:

- Bronze sync: `/tmp/sintetico/base_bronze.duckdb`;
- Ops sync: `/tmp/sintetico/ops/base_ops.sqlite`.

Já `ProjectAccess(db_path=Bronze)` sem Ops deriva pelo **stem do arquivo recebido**
(`src/compras_crawler/project_access.py:73-84`):
`/tmp/sintetico/base_bronze_ops.sqlite`. Não é o Ops do sync.
Fornecer `ops_db_path=/tmp/sintetico/ops/base_ops.sqlite` ao acesso/MCP seleciona
o mesmo Ops explicitamente, sem mudar nenhum default e sem provar disponibilidade
ou compatibilidade do conteúdo. No MCP, `--db-path` deve ser o Bronze explícito,
não o prefixo do sync. O caso `caminhos-explicitos` abaixo apenas especifica essa
seleção; não instrui executar comandos de coleta ou abrir esses arquivos.

## 2. Populações e responsabilidades distintas

### 2.1 Bronze, Ops e controle web [Fato]

- **Página/resposta Bronze:** uma linha de `bronze_pages`, com run, job, entidade,
  número da página, parâmetros serializados, formato, status HTTP, payload
  serializado/textual, hash e instante (`src/compras_crawler/storage.py:50-100`).
  Uma página pode conter zero, um ou vários registros. Não confundir página com
  observação de registro ou com compra. O schema citado não contém endpoint ou
  método HTTP explícitos: referências de catálogo não comprovam uma requisição
  histórica ausente; tampouco se promete preservar os bytes originais do JSON.
- **Observação histórica de registro:** extração de um payload contido em uma
  página. `ProjectAccess` lê JSON ou CSV conforme formato e emite proveniência
  `run_id`, job, página, hashes e instante; sua chave é `rowid:índice`
  (`src/compras_crawler/project_access.py:56-69,106-115`). Não é chave portátil de
  observação nem identidade de negócio. `first_seen_at`/`last_seen_at` nesse ramo
  são o instante da própria observação, não uma agregação de toda a história.
- **Ops do crawler:** `ops_runs`, `ops_checkpoints`, `ops_errors` vivem no SQLite
  separado (`src/compras_crawler/storage.py:171-208`). Guardam execução/progresso,
  não substituem o payload histórico. Full-city mantém ainda
  `bronze_crawl_jobs` no DuckDB (`src/compras_crawler/crawl_state.py:26-32`).
- **Controle web:** `app.sqlite` organiza fila/agendas/cidades/eventos e ponteiros
  de snapshot; não é o Ops SQLite municipal, nem Bronze ou coleção de compras
  (`src/compras_crawler/web/store.py:52-105,325-340`). O run de controle web e o
  run do crawler não devem ser presumidos iguais: o worker passa o primeiro como
  `collection_id` e o crawler inicia seu próprio run Ops
  (`src/compras_crawler/web/worker.py:41-50`,
  `src/compras_crawler/full_city.py:127-132`).

### 2.2 Última identidade e compras conciliadas [Fato]

`build_snapshot` extrai registros de páginas para uma tabela intermediária
`observations`, com origem contendo run, job, entidade, página, índice, parâmetros
e instante (`src/compras_crawler/web/analytics.py:120-150`). `normalize` escolhe
identidade por família: para `pncp_contratacao`, família `pncp`, usa `idCompra`
ou controle PNCP, e calcula `id` por família/identidade (fallback por conteúdo
quando não há identidade segura; `src/compras_crawler/web/analytics.py:19-27,55-80`).

A tabela **`records`** seleciona uma linha por esse `id`, por `fetched_at DESC`,
com desempates por atualização, entidade de detalhe e payload; descarta a tabela
intermediária, **não o Bronze** (`src/compras_crawler/web/analytics.py:153-157`).
É uma visão materializada de última identidade observada segundo essas regras,
não o histórico de observações. Os relógios de coleta e atualização da fonte não
são intercambiáveis.

**`purchase_candidates`/`purchases`** constituem outra população: conciliam
aliases PNCP apenas quando unívocos, identificam conflitos, resolvem município
explícito ou via UASG unívoca e exigem identidade segura, município correspondente
e data conhecida. A escolha por `purchase_key` prioriza PNCP, depois recência;
excluídos e candidatos com motivo de exclusão ficam fora de `purchases`
(`src/compras_crawler/web/analytics.py:159-185`). Logo, uma identidade em `records`
não implica uma compra conciliada. Não impor igualdade entre contagem de páginas,
observações, últimas identidades e compras; ausência/cobertura desconhecida não
significa zero compras no município.

### 2.3 Legado e camadas consolidadas

**[Fato]** `silver_records` é uma tabela **legada legível**, não uma negação da
existência de Silver no passado. `ProjectAccess._has_legacy_records` verifica a
**existência da tabela**, não se há linhas. Se ela existe, `list_entities`,
`search_records` e `get_record` consultam esse legado em precedência ao Bronze;
não há união nem fallback por entidade vazia
(`src/compras_crawler/project_access.py:100-103,191-199,210-255`). Sem essa tabela,
`list_entities` conta registros extraídos de todas as páginas; `search_records`
pagina observações históricas, não últimas identidades
(`src/compras_crawler/project_access.py:198-208,225-235`).

**[Proposta pendente]** Silver e Gold **consolidadas e compartilhadas** continuam
**a definir**: responsabilidades, esquema, identidade, qualidade, versionamento,
linhagem e população publicada. Silver poderia tratar normalização/identidade;
Gold poderia tratar conciliação/métricas, mas essa divisão é alternativa a revisar.
Nem o nome legado `silver_records` nem rebatizar `records`/`purchases` aprova essas
camadas. O `layer_status` do JSON refere-se às camadas consolidadas, sem apagar
o legado ou as projeções existentes.

### 2.4 Município: recorte de coleta ≠ pertencimento comprovado

**[Fato]** Full-city começa com filtros municipais PNCP, mas também consulta
UASGs da UF, filtrando o retorno para o fanout após receber as páginas
(`src/compras_crawler/full_city.py:221-254`). Persistência antecede o retorno dos
registros (`src/compras_crawler/full_city.py:498-514`): Bronze pode conter dados
auxiliares estaduais/nacionais. Pasta, nome de job e município solicitado
identificam o **recorte/intenção da coleta**, não são evidência territorial de
cada payload. Analytics usa campo municipal explícito ou vínculo UASG unívoco,
nunca o nome do arquivo (`src/compras_crawler/web/analytics.py:158-180`).

**[Proposta]** Um contrato compartilhado deve expor separadamente escopo solicitado,
proveniência da observação e evidência de pertencimento (explícita, derivada,
conflitante ou ausente). Não preencher município do registro pela pasta de coleta.

## 3. Invariantes propostas e limites de cobertura atual

Cada linha é **[Proposta]**, com cobertura **[Fato]** delimitada por fluxo, não uma
garantia global implementada ou validada neste ciclo.

| Invariante proposta | Evidência atual e limite |
| --- | --- |
| Preservar ocorrências históricas; não deduplicar Bronze por hash do payload. | `land_page` insere novas páginas (`src/compras_crawler/storage.py:70-100`); `CrawlState` também insere, sem apagar histórico (`src/compras_crawler/crawl_state.py:77-85`). Hash descreve conteúdo, não unicidade de evento. Full-city usa hashes para detectar página repetida na paginação do job (`src/compras_crawler/full_city.py:474-490`), não para definir identidade portátil ou eliminar globalmente novas coletas legítimas. |
| Diferenciar replay da mesma confirmação de uma nova observação, mesmo com payload idêntico. | Full-city protege replay de página já confirmada na mesma chave/geração com o guard de próxima página e transação (`src/compras_crawler/crawl_state.py:60-88`); `open_job` retoma ou gera nova geração (`src/compras_crawler/crawl_state.py:35-47`). Isso não estabelece idempotência universal para sync, importação ou futuros backends. Identidade do evento e política de replay ainda precisam decisão. |
| Progresso durável não pode pular página não confirmada. | Full-city confirma página e `bronze_crawl_jobs` na mesma transação; checkpoint SQLite é posterior (`src/compras_crawler/crawl_state.py:64-88`, `src/compras_crawler/full_city.py:498-501`). Sync grava página e depois checkpoint por chamadas distintas (`src/compras_crawler/sync.py:289-303`); não atribuir-lhe a atomicidade do full-city. |
| Proveniência e reconstrução devem ser preservadas, com lacunas explícitas. | Bronze/ProjectAccess mantêm metadados da observação; snapshot mantém origem selecionada (`src/compras_crawler/storage.py:50-100`, `src/compras_crawler/project_access.py:63-69`, `src/compras_crawler/web/analytics.py:143-145`). Endpoint/método ausentes não se tornam fatos históricos por inferência. Chave `rowid:índice` não é portátil entre cópias/reorganizações. |
| Publicar somente versão consistente e identificável, preservando a anterior até a troca. | Web constrói outro arquivo e publica após fechar conexões (`src/compras_crawler/web/analytics.py:109-115,191-197`); `AppStore.publish` troca ponteiros em transação e verifica lease quando fornecido (`src/compras_crawler/web/store.py:325-340`); worker fornece lease (`src/compras_crawler/web/worker.py:55-59`). Essa cobertura é da projeção web, não de toda escrita Bronze ou todo consumidor. |
| Coordenação e leitura segura devem ser explícitas por recurso físico. | Há lock de serviço e lock municipal (`src/compras_crawler/web/runtime.py:93-95`, `src/compras_crawler/web/worker.py:32-38`), claim por cidade (`src/compras_crawler/web/store.py:168-186`) e leitura de snapshot. `ProjectAccess` sinaliza erro de leitura e orienta parar escrita/usar snapshot (`src/compras_crawler/project_access.py:88-98`). Esses mecanismos não coordenam todos os escritores CLI/MCP de um único DuckDB físico. |

## 4. Registro de decisões abertas — nenhuma alternativa aprovada

**[Proposta]** Todas as cinco decisões abaixo permanecem `pendente`. A aprovação
deste ciclo é de especificação, não de arquitetura ou execução futura.

| Chave / estado | Alternativas a avaliar | Consequências e dependências |
| --- | --- | --- |
| `physical_layout` / pendente | Contrato lógico sobre arquivos separados por contexto/município; catálogo lógico compartilhado mantendo arquivos separados; arquivo físico comum. | Base lógica não exige fusão física. Exige definir descoberta de contexto, isolamento, cobertura e versionamento. Arquivo comum exigiria protocolo de concorrência antes de qualquer mudança. Nenhum catálogo é implementado. |
| `backend` / pendente | Manter DuckDB Bronze + SQLite Ops/controle; Parquet com registro de publicação; DuckDB único como alternativa de armazenamento. | Manter reduz transição, mas preserva fronteiras transacionais; Parquet exige manifesto, compatibilidade, replay e publicação; DuckDB único exige avaliar leitores/escritores de processos distintos e blast radius. Não escolher backend por conveniência nominal. |
| `stable_observation_id` / pendente | Identificador opaco persistido na ingestão; composição de fonte/coleção/geração/página/índice com regras portáveis. | Definir como preservar o mesmo evento no replay/cópia e distinguir nova coleta. Identidade de negócio agrupa ocorrências; hash de conteúdo não identifica evento. Portabilidade e ordenação em empates exigem contrato antes de adaptadores/migração. |
| `default_views` / pendente | Preservar histórico no MCP e última identidade/compras na web com nomes explícitos; oferecer seleção explícita dessas populações em cada interface; alinhar defaults só após decisão de compatibilidade. | Cada resposta precisaria indicar população, cobertura, versão e proveniência. Não igualar contagens nem mudar defaults silenciosamente; mesma identidade de negócio não implica mesma visão. |
| `legacy_precedence` / pendente | Preservar precedência por existência; seleção explícita de fonte/visão; eventual visão combinada com política de conflito. | Compatibilidade do MCP e risco de esconder Bronze/duplicar contagens. União exigiria regras de identidade, conflito e linhagem; não misturar silenciosamente `legacy_silver` e observações Bronze. |

**Compatibilidade adicional pendente [Proposta]:** documentar/resolver seleção
explícita de caminhos primeiro; só um futuro pacote poderia mudar defaults,
namespaces e checkpoints com regras de retomada/versionamento. Não reutilizar
checkpoint de outro escopo por supor que nomes coincidentes identificam a mesma
coleta; preservar a diferença atual entre sync e full-city.

**Contexto de plano [Fato]:** `docs/WEB_PLAN.md:5,9-14,37,65,75` registra intenção
de Parquet, camadas derivadas fora daquela revisão, armazenamento hoje em
DuckDB/SQLite, migração ainda não implementada e isolamento municipal anterior.
É entrada revisável, não implementação ou autorização deste pacote. Nenhuma
contagem real ou resultado de teste relatado naquele plano serve de prova aqui.

## 5. Três casos pedagógicos — somente especificações não executadas

Não são fixtures, configuração de runtime ou instruções para rodar software.
Os passos abaixo são raciocínio sobre entradas hipotéticas; os caminhos e payloads
existem apenas neste documento. Não foram criados arquivos nem invocados crawler,
ProjectAccess, MCP, serviços ou testes.

### 5.1 `duas-observacoes`

**Especificação não executada.** Universo fechado sem `silver_records`, duas
páginas JSON hipotéticas, cada uma com lista contendo um único payload da entidade
`pncp_contratacao`. Ambas representam a identidade de negócio `sintetica-1`, com
`payload.idCompra=sintetica-1`. Runs sintéticos `a` e `b`, páginas 1 e índice 0,
parâmetros e instantes UTC determinísticos explícitos no JSON. O campo `identity`
é rótulo pedagógico de negócio, não coluna nova nem ID portátil aprovado; a
proveniência descreve a página/execução, não uma API efetivamente chamada.

Raciocínio: considerar duas novas observações, extraí-las sem destruir Bronze e
aplicar a seleção atual de última identidade do snapshot. Payloads diferem no
objeto e `b` tem instante posterior; portanto esperar **duas observações Bronze**
e **uma linha em `records`**, origem selecionada **run `b`**. A contagem de páginas
seria duas apenas porque este universo estipula uma observação por página.

Isso **não** especifica uma compra conciliada: os payloads não trazem evidência
municipal nem data de publicação. `purchases` depende de evidências adicionais,
conflitos, exclusão e conciliação; não herda `snapshot_records=1` como expectativa
de contagem. A seleção usa identidade/família e recência, não elimina histórico
por hash. Reconfirmar a mesma página/geração seria replay, não a segunda coleta;
uma nova coleta com conteúdo até idêntico ainda pode ser nova observação. Essa
política é invariante proposta com cobertura parcial atual da seção 3, não uma
nova garantia universal implementada.

### 5.2 `caminhos-explicitos`

**Especificação não executada.** Raciocinar com prefixo sync
`/tmp/sintetico/base`, seu Bronze derivado e Ops derivado. Para ProjectAccess/MCP,
selecionar esse Bronze e passar Ops explicitamente. Esperar a seleção textual
`/tmp/sintetico/ops/base_ops.sqlite`, com defaults preservados. Sem o argumento,
o default continuaria `/tmp/sintetico/base_bronze_ops.sqlite` (seção 1.1).
Nenhum arquivo precisa existir para descrever a resolução; o caso não afirma
que leitura ou acesso real tenha funcionado.

### 5.3 `contexto-ausente`

**Especificação não executada.** Precondição hipotética: Bronze em
`/tmp/sintetico/ausente_bronze.duckdb` inexistente; não criar o diretório nem o
arquivo para verificá-la. Considerar especificamente
`ProjectAccess(...).list_entities()`: entra em `_duck_connection`, verifica
`is_file()` e lança **`FileNotFoundError` antes de abrir DuckDB**, sem criar
arquivos (`src/compras_crawler/project_access.py:73-98,191-192`).

Não generalizar para `get_project_info`: no MCP esse tool chama `project_info`,
que apenas informa caminhos/disponibilidade com `exists`, sem abrir a base
(`src/compras_crawler/mcp_server.py:45-48`,
`src/compras_crawler/project_access.py:142-151`). Esse comportamento é distinto
do erro específico de `list_entities`; o caso não executa nem valida transporte
MCP ou tratamento de erro da UI.

### 5.4 Bloco pedagógico único

O JSON abaixo é a especificação estruturada dos três casos; não deve ser lido pelo
produto. `layer_status` trata de camadas consolidadas, como delimitado na seção 2.3.

```json
{
  "status": "especificacao-nao-executada",
  "permissions": [],
  "current_paths": {
    "sync_bronze": "/tmp/sintetico/base_bronze.duckdb",
    "sync_ops": "/tmp/sintetico/ops/base_ops.sqlite",
    "mcp_ops_default": "/tmp/sintetico/base_bronze_ops.sqlite",
    "mcp_ops_explicit": "/tmp/sintetico/ops/base_ops.sqlite",
    "web_bronze": "cities/<IBGE>/bronze.duckdb",
    "web_ops": "cities/<IBGE>/ops.sqlite",
    "web_control": "app.sqlite"
  },
  "layer_status": {
    "Bronze": "atual",
    "Silver": "a-definir",
    "Gold": "a-definir"
  },
  "decisions": {
    "physical_layout": "pendente",
    "backend": "pendente",
    "stable_observation_id": "pendente",
    "default_views": "pendente",
    "legacy_precedence": "pendente"
  },
  "cases": {
    "duas-observacoes": {
      "status": "especificacao-nao-executada",
      "observations": [
        {
          "entity": "pncp_contratacao",
          "identity": "sintetica-1",
          "run": "a",
          "fetched_at": "2026-01-01T00:00:00Z",
          "payload": {
            "idCompra": "sintetica-1",
            "objetoCompra": "Objeto sintético inicial"
          },
          "provenance": {
            "run_id": "a",
            "job": "pncp_contratacoes_sinteticas",
            "entity": "pncp_contratacao",
            "page": 1,
            "record_index": 0,
            "request_params": {"pagina": 1},
            "response_format": "json",
            "http_status": 200,
            "fetched_at": "2026-01-01T00:00:00Z"
          }
        },
        {
          "entity": "pncp_contratacao",
          "identity": "sintetica-1",
          "run": "b",
          "fetched_at": "2026-01-02T00:00:00Z",
          "payload": {
            "idCompra": "sintetica-1",
            "objetoCompra": "Objeto sintético revisado"
          },
          "provenance": {
            "run_id": "b",
            "job": "pncp_contratacoes_sinteticas",
            "entity": "pncp_contratacao",
            "page": 1,
            "record_index": 0,
            "request_params": {"pagina": 1},
            "response_format": "json",
            "http_status": 200,
            "fetched_at": "2026-01-02T00:00:00Z"
          }
        }
      ],
      "expected": {
        "bronze_observations": 2,
        "snapshot_records": 1,
        "selected_run": "b"
      }
    },
    "caminhos-explicitos": {
      "status": "especificacao-nao-executada",
      "sync_prefix": "/tmp/sintetico/base",
      "access_db_path": "/tmp/sintetico/base_bronze.duckdb",
      "access_ops_db_path": "/tmp/sintetico/ops/base_ops.sqlite",
      "expected": {
        "ops": "/tmp/sintetico/ops/base_ops.sqlite",
        "preserves_defaults": true
      }
    },
    "contexto-ausente": {
      "status": "especificacao-nao-executada",
      "operation": "ProjectAccess.list_entities",
      "bronze_path": "/tmp/sintetico/ausente_bronze.duckdb",
      "bronze_exists": false,
      "expected": {
        "exception": "FileNotFoundError",
        "creates_files": false
      }
    }
  }
}
```

## 6. Candidatos posteriores, dependências e limites de evidência

Nada nesta lista autoriza iniciar outro ciclo, migrar ou implementar:

1. **Revisar semanticamente este contrato e decidir populações/precedência.**
   Depende dos critérios do pacote e de decisão humana sobre as alternativas da
   seção 4. Só então propor descritor lógico/visões e testes sintéticos em novo
   pacote, com identidade portátil e compatibilidade explícitas.
2. **Avaliar compatibilidade de defaults/checkpoints sync. [Inferência]**
   `sync.py` carrega e salva por `job.name`
   (`src/compras_crawler/sync.py:211-212,303,438-439`), com chave primária
   `job_name` (`src/compras_crawler/storage.py:190-195,256-269`). Possível colisão
   de escopos é hipótese de código, **não defeito reproduzido** nem observado em
   dados reais. Candidato exigiria reprodução sintética de jobs homônimos com
   escopos distintos e política de compatibilidade aprovada antes de correção.
3. **Avaliar paridade CSV das projeções. [Inferência]** ProjectAccess trata CSV
   (`src/compras_crawler/project_access.py:56-60`); snapshot usa
   `extract_records(json.loads(payload))` (`src/compras_crawler/web/analytics.py:140-145`),
   que aceita listas/dicionários, não strings (`src/compras_crawler/normalize.py:20-30`).
   Possível descarte na extração CSV é candidato a reprodução sintética posterior,
   **não falha executada neste ciclo**. Não confundir com perda do payload Bronze.
4. **Avaliar backend/layout e publicação sob falhas. [Proposta]** Depende das
   decisões anteriores, protocolo de concorrência/replay e novo pacote de checks
   sintéticos; não implica adoção de Parquet ou DuckDB único. Uso de dados reais,
   coleta, migração, dependências de produção, fonte nova ou publicação exigiriam
   aprovação explícita das respectivas permissões protegidas. Aqui permanecem
   proibidos, assim como rede, instalações e serviços.

**Validação deste ciclo:** somente inspeção estática de fontes e Git pelo escritor.
Os três checks documentais congelados (`ul01-conteudo-da-especificacao`,
`ul01-diff-documental-sem-erros`, `ul01-caminhos-exclusivos-do-ciclo`) ficam
reservados ao pai/controlador, no HEAD limpo e commitado. Nenhum foi executado pelo
escritor. Mesmo passando, conferem estrutura/diff, não comportamento de runtime,
segurança de concorrência, casos executados, validade de toda a narrativa ou
compras reais. Revisão semântica independente por critério, aceite humano e
integração local separadamente autorizada continuam necessários.
