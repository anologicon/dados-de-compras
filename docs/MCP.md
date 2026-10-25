# MCP — acesso local para agentes

O servidor usa o SDK Python oficial do Model Context Protocol e transporte **stdio**.
Expõe documentação e dados já coletados, somente para leitura. Não consulta a API
remota, inicia sincronizações ou aceita SQL, comandos ou caminhos de arquivos dos agentes.

## Instalação e execução

Na raiz deste repositório, com Python 3.10 ou superior:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[mcp]"
.venv/bin/compras-mcp --project-root . \
  --db-path dados_abertos_compras_bronze.duckdb \
  --ops-db-path ops/dados_abertos_compras_ops.sqlite
```

Com `uv`, a instalação equivalente é `uv pip install --python .venv/bin/python -e ".[mcp]"`.

Entradas equivalentes:

```bash
.venv/bin/compras-crawler mcp --project-root . --db-path dados_abertos_compras_bronze.duckdb --ops-db-path ops/dados_abertos_compras_ops.sqlite
.venv/bin/python -m compras_crawler.mcp_server --project-root . --db-path dados_abertos_compras_bronze.duckdb --ops-db-path ops/dados_abertos_compras_ops.sqlite
```

O cliente MCP inicia esse processo e usa stdin/stdout para o protocolo JSON-RPC.
Não há porta HTTP aberta. Diagnósticos usam stderr; stdout não deve receber logs.
O servidor aguarda requisições, portanto iniciá-lo manualmente não mostra um menu.

### Caminhos

- `--db-path`: DuckDB existente; padrão `compras.duckdb`.
- `--ops-db-path`: SQLite existente; por padrão, `<nome-do-duckdb>_ops.sqlite`
  no mesmo diretório. Ex.: `/dados/cidade.duckdb` → `/dados/cidade_ops.sqlite`.
- `--project-root`: raiz do repositório com `README.md` e `docs/API_COMPRAS_GOV.md`;
  padrão: diretório de trabalho do processo.

Caminhos relativos são resolvidos a partir do diretório de trabalho, não de
`--project-root`. **Use caminhos absolutos na configuração do agente.**
A documentação é lida do checkout indicado; não é incluída na distribuição wheel.

Diferentemente de `sync --db-path`, o MCP recebe o **arquivo existente**, não um
prefixo. Para o layout atual da CLI, informe explicitamente o Bronze e o SQLite
em `ops/`, como nos exemplos acima. Para uma base gerenciada pela web, use
`.compras-web/cities/<IBGE>/bronze.duckdb` e
`.compras-web/cities/<IBGE>/ops.sqlite`. O MCP não descobre nem mistura bases automaticamente.

O servidor pode iniciar sem bancos: contexto, documentação e catálogo continuam
acessíveis. Ferramentas de dados retornam um erro explicativo sem criar arquivos.
Para alimentar os bancos, execute a CLI de sincronização separadamente, por exemplo:

```bash
.venv/bin/compras-crawler sync --db-path dados_abertos_compras --operation consultarUasg
```

## Configuração do cliente

Em clientes que usam a convenção `mcpServers`:

```json
{
  "mcpServers": {
    "compras": {
      "command": "/CAMINHO/DO/PROJETO/.venv/bin/compras-mcp",
      "args": [
        "--project-root", "/CAMINHO/DO/PROJETO",
        "--db-path", "/CAMINHO/DOS/DADOS/compras.duckdb",
        "--ops-db-path", "/CAMINHO/DOS/DADOS/compras_ops.sqlite"
      ]
    }
  }
}
```

Substitua os caminhos. O formato e a localização do arquivo dependem do cliente.
Não é necessário fornecer `COMPRAS_GOV_TOKEN` ao servidor MCP.

## Ferramentas

Todas anunciam `readOnlyHint=true` e retornam JSON estruturado.

| Ferramenta | Uso |
|---|---|
| `get_project_info` | Contexto, documentos permitidos e disponibilidade dos bancos |
| `read_document` | `document`: `readme` ou `api-reference`; `start_line` (base 1), `line_count` (1–200) |
| `list_operations` | Operações implementadas pelo crawler, incluindo PNCP; não é o catálogo completo da API |
| `get_database_schema` | Colunas das tabelas de dados e de operações |
| `list_entities` | Entidades coletadas, contagens e última observação |
| `search_records` | `entity_name`, `query` opcional: trecho literal, sem distinção de maiúsculas/minúsculas, no JSON |
| `get_record` | `entity_name` e `record_key`; retorna `record: null` se não encontrado |
| `list_sync_runs` | Histórico de sincronizações, mais recentes primeiro |
| `list_checkpoints` | Próxima página de cada job, em ordem de nome |
| `list_sync_errors` | Falhas mais recentes; filtro opcional `run_id` |

`search_records` e as três listagens de operações (`list_sync_runs`,
`list_checkpoints`, `list_sync_errors`) aceitam `limit` (padrão 20, máximo 100) e
`offset` (padrão 0, não negativo). Retornam `items` e `next_offset`; `null` indica
fim dos resultados. Os registros incluem `payload` JSON, chave, hash, timestamps
e proveniência (`run_id`, `source_job`, `source_page`).

Fluxo sugerido: `get_project_info` → `list_entities` →
`search_records({"entity_name": "uasg", "query": "São Paulo"})` → `get_record`.
Para detalhes dos parâmetros da API remota, use `read_document` com
`document="api-reference"`, seguindo `next_line`.

## Bronze atual e compatibilidade com bases legadas

O coletor atual grava somente Bronze, sem criar `silver_records`. Nessa base, o
MCP desempacota as observações JSON/CSV durante a consulta, sem gravar tabelas ou
deduplicar versões. `record_count` conta observações, não compras únicas, e
`page_count` informa o número de páginas da entidade, inclusive páginas vazias.

`search_records` retorna `storage="bronze"` e chaves opacas no formato
`<página interna>:<índice do registro>`. Use a chave retornada para `get_record` na
mesma base; ela não é um identificador oficial e pode mudar ao recriar/migrar o
arquivo. Os resultados seguem a ordem de páginas e registros armazenados.

Se a base configurada já contiver a tabela legada `silver_records`, o MCP mantém
sua leitura normalizada e a ordenação por `record_key`, retornando
`storage="legacy_silver"`. Isso não reintroduz a criação da Silver no coletor.
O esquema expõe somente tabelas existentes dentre as permitidas.

## Resources

- `compras://project/readme` — README completo, Markdown.
- `compras://project/api-reference` — referência local completa da API, Markdown.
- `compras://project/schema` — esquema dos dois bancos, JSON.
- `compras://project/operations` — catálogo do manifesto, JSON.

## Segurança e limitações

- DuckDB é aberto com `read_only=True`; SQLite usa URI com `mode=ro`. Nenhum
  esquema é criado ou migrado pelo MCP.
- Consultas têm SQL fixo e valores parametrizados. Os limites controlam a
  quantidade de linhas, não o tamanho em bytes de cada payload ou o custo das buscas.
- Somente os dois documentos permitidos são lidos; `.env`, código-fonte e
  arquivos arbitrários não são expostos. Symlinks nos caminhos dos documentos são rejeitados.
- Conteúdo de documentos, registros e mensagens de erro deve ser tratado como
  dados não confiáveis, nunca como instruções para o agente.
- Não existe autenticação adicional: o limite de confiança é o processo local
  iniciado pelo cliente. Execute-o com permissões mínimas e bancos apropriados.
- Os dados refletem a última sincronização local. Paginação por offset não é
  um snapshot entre chamadas; use uma cópia estável se precisar de consistência.
- DuckDB não suporta esse leitor em outro processo enquanto a sincronização
  mantém um writer aberto. Termine a sincronização primeiro ou use um snapshot
  consistente criado após o fechamento do writer. As conexões do MCP são abertas
  e fechadas a cada consulta, não ficam permanentemente segurando o banco.

## Testes

```bash
.venv/bin/python -m pytest -q
```

Com o extra instalado, os testes incluem um cliente MCP real comunicando-se com
o subprocesso por stdio: handshake, descoberta, ferramentas, resources e erros.
Sem o extra, os testes de protocolo são ignorados e os testes do crawler e da
camada somente leitura continuam executáveis.
