# API PNCP direto — contrato de coleta

> **Versão do contrato de coleta:** `v1-2026-10-26` · **Fonte:** `https://pncp.gov.br`
>
> Referência usada apenas para os GET públicos do PNCP, conforme
> [docs/PNCP_DIRECT_PLAN.md](PNCP_DIRECT_PLAN.md) (§2). Consultada por GET em
> 2026-10-26 a partir dos specs oficiais:
>
> - **API de consulta:** `https://pncp.gov.br/api/consulta/v3/api-docs`
> - **API PNCP (leitura e manutenção):** `https://pncp.gov.br/api/pncp/v3/api-docs`
>
> A segunda API também documenta escrita e administração. Este contrato cobre
> **somente** os GET públicos listados; nunca percorrer as demais operações,
> usar credenciais de publicação ou seguir links dos sistemas de origem.
>
> Diferença de nomes importante: `sync --source pncp` na CLI existente se refere
> ao módulo PNCP **dentro do Compras.gov.br** (`/modulo-contratacoes/..._PNCP_14133`).
> Esta fonte nova é `pncp_direct`, com hosts e rotas próprios.

## 1. Hosts e rotas permitidos

Host fixo HTTPS: `pncp.gov.br`, porta 443. Nenhum redirecionamento para outro
host é aceito; o cliente não segue redirects.

| Finalidade | Método e rota |
| --- | --- |
| Domínio de modalidades | `GET https://pncp.gov.br/api/pncp/v1/modalidades` |
| Compras por publicação | `GET https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao` |
| Detalhe de compra (quando necessário) | `GET https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}` |
| Itens da compra | `GET https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens` |
| Quantidade de itens (conferência) | `GET https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens/quantidade` |
| Resultados de um item | `GET https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens/{numeroItem}/resultados` |

## 2. Convenções

### 2.1 Paginação da listagem

| Parâmetro | Formato | Limites |
|---|---|---|
| `pagina` | número da página, base 1 | obrigatório |
| `tamanhoPagina` | registros por página | máximo documentado **50**, mínimo 10; **não** herdar o default 100 do cliente Compras.gov.br |
| `dataInicial` / `dataFinal` | `yyyyMMdd` (a interface da web continua em ISO e converte para o cliente) | janela da coleta |
| `codigoModalidadeContratacao` | código do domínio de modalidades | a listagem exige modalidade |
| `codigoMunicipioIbge` / `uf` | recorte territorial | filtro de coleta; não substitui validação do município retornado |

Envelope da listagem: contêiner `data` com `totalRegistros`, `totalPaginas`,
`numeroPagina`, `paginasRestantes`.

- **HTTP 204 é resposta válida sem conteúdo**, não JSON inválido.
- Página repetida antes do fim da paginação é erro terminal.
- Itens aceitam paginação; resultados listados **não documentam `pagina`**.
  Não enviar parâmetros inventados nem presumir paginação idêntica à listagem.

### 2.2 Filhos (itens e resultados)

Filhos retornam **arrays**, não o envelope da listagem:

- **Itens:** `numeroItem`, `descricao`, `temResultado`, valores, unidade,
  `orcamentoSigiloso`. Não pressupor `idCompra` ou `idCompraItem`.
- **Resultados:** `numeroControlePNCPCompra`, `numeroItem`,
  `sequencialResultado`, fornecedor, valores, cancelamento em `dataCancelamento`.
- **Detalhe de compra** é um objeto. O parsing é específico da operação para não
  descartar objetos válidos nem interpretar objeto de erro como compra.

### 2.3 Identidades e vínculos

| Entidade | Identidade/vínculo seguro |
| --- | --- |
| Compra | `numeroControlePNCP`, com coerência validada contra CNPJ/ano/sequencial retornados |
| Item | controle da compra + `numeroItem` |
| Resultado | controle da compra + `numeroItem` + `sequencialResultado` |
| Fornecedor observado | tipo (`PF`/`PJ`/`PE`) + documento completo compatível, quando disponível |

- `unidadeOrgao.codigoUnidade` **não é UASG**: não cruzar por igualdade textual
  com unidades do Compras.gov.br.
- `tipoPessoa` admite PF, PJ e PE. Documento estrangeiro não é CPF/CNPJ.
- Para filhos sem controle no corpo, a parentagem pode ser provada pelo caminho
  efetivamente requisitado (registrado na proveniência com seus parâmetros),
  marcada como evidência derivada do endpoint, não campo do payload.
- `numeroControlePNCP` tem o formato `cnpj-segmento-sequencial/ano`; incoerência
  com os campos da compra fica explícita (ambígua), sem vínculo por conveniência.

### 2.4 Autenticação

A consulta é pública. **Nunca** enviar `COMPRAS_GOV_TOKEN` ao PNCP, inclusive
após 401/403; não há retry com autenticação nesta fonte. 401/403 é erro terminal
da requisição, registrado na execução.

### 2.5 Comportamento e limites

- Timeout, retries limitados, `Retry-After`/cooldown e o limite global de
  **1 requisição/segundo** (contando ambas as fontes e retries) são compartilhados.
- Sigilo (`orcamentoSigiloso`), zero, ausência, cancelamento e cadastro ausente
  são preservados como estão; não fabricar IDs nem preencher datas.
- Página e avanço do checkpoint persistem na **mesma transação** do Bronze;
  replay da confirmação não duplica página; nova coleta pode guardar outra
  observação de conteúdo idêntico (o histórico não é deduplicado por hash).
- Namespaces de entidades/jobs: `pncp_direct_contratacao`,
  `pncp_direct_item_contratacao`, `pncp_direct_resultado_item`.
- A documentação confirma os contratos, mas não prova comportamento real de
  paginação, acesso público, sigilo e consistência entre páginas: esses pontos
  dependem de testes simulação e da verificação real autorizada (piloto).
