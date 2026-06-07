# API Compras.gov.br — Open API Reference

> **Version:** 1.0.0 · **OpenAPI:** 3.1.0 · **Base URL:** `https://dadosabertos.compras.gov.br`
>
> The **Compras.gov.br** data-access API exposes public procurement data for the
> Brazilian Federal Government. It covers catalogs, price research, price registers
> (ARP), contracts, bid/tender records (legacy and PNCP/Lei 14.133), OCDS releases,
> supplier data, ALICE analyses, and usage indicators.
>
> **OpenAPI Spec:** `https://dadosabertos.compras.gov.br/v3/api-docs`
>
> **Note:** All data is public-domain government information. This document is
> machine-readable reference for LLM consumption.

## 2. Conventions

### 2.1 Pagination

Most list endpoints accept two query parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `pagina` | `integer` | `1` | Page number (1-based) |
| `tamanhoPagina` | `integer` | — | Page size (server-defined maximum) |

### 2.2 Dates

All date parameters use **`YYYY-MM-DD`** format (ISO 8601).
Datetime fields in responses use **ISO 8601** with timezone offset when available.

### 2.3 CSV Endpoints

Many endpoints have a `_CSV` or `.1_` variant that returns `text/csv` instead of JSON.
These share the same parameters as their JSON counterpart.

### 2.4 Common Identifiers

| Code | Description |
|---|---|
| `codigoOrgao` | Government body (órgão) code |
| `codigoUasg` | UASG code (Unidade Administrativa de Serviços Gerais) |
| `cnpj` / `cpf` | Legal entity / individual taxpayer ID |
| `niFornecedor` | Supplier taxpayer ID (CNPJ or CPF) |
| `codigoItemCatalogo` | CATMAT / CATSER catalog item code |
| `codigoPdm` | PDM code (Produto/Dado/Material catalog) |
| `idCompra` | Internal purchase ID |
| `numeroControlePncpAta` | PNCP price-register (ATA) control number |
| `numeroControlePncpContrato` | PNCP contract control number |

## 3. Authentication

The API uses **HTTP Bearer (JWT)** authentication.

### 3.1 Obtain a Token

```
POST /autenticacao/login
Content-Type: application/json

{
  "login": "your-email",
  "senha": "your-password"
}
```

**Response:** a plain JWT string in the body.

### 3.2 Use the Token

```
Authorization: Bearer <JWT>
```

### 3.3 Which Endpoints Require Auth?

The spec only formally marks these as secured:

| Module | Endpoint | Method |
|---|---|---|
| USUARIOS | `/usuarios/criar` | `POST` |
| USUARIOS | `/usuarios/atualizar/{id}` | `PATCH` |
| USUARIOS | `/usuarios/resetSenha/{id}` | `PATCH` |
| USUARIOS | `/usuarios/consultar` | `GET` |
| ALICE | `/alice/tickets` | `GET` |
| ALICE | `/alice/compras` | `GET` |
| ALICE | `/alice/avisos-restritos` | `GET` |

All other endpoints have **no global or per-operation `security`** declaration
 in the spec. Some modules (CONTRATOS, ARP, OCDS, FORNECEDOR, LEGADO) may require
 authentication at runtime despite not being marked. Include the `Authorization`
 header when making requests to those modules if you receive `401`/`403` errors.

## 4. Module Index

| # | Module | Operations | Auth | Description |
|---|---|---|---|---|
| `98 - ALICE` | 3 | Yes | ALICE purchase analyses (tickets, purchases, restricted notices) |
| `02 - CATÁLOGO - SERVIÇO` | 8 | No | Service catalog: sections, divisions, groups, classes, items |
| `04 - PGC` | 6 | No | PGC (Programa de Gerenciamento de Compras): purchase program details |
| `AUTENTICACAO` | 1 | No | Authentication: login to obtain JWT token |
| `08 - ARP` | 8 | No | Ata de Registro de Preço (Price Register): records, items, units, commitments, adhesions |
| `07 - CONTRATAÇÕES` | 6 | No | PNCP contratações (Lei 14.133/21): procurement and items |
| `03 - PESQUISA DE PREÇO - PREÇOS PRATICADOS` | 8 | No | Price research: historical prices for materials and services |
| `99 - USUARIOS` | 4 | Yes | User management (create, update, password reset, query) |
| `05 - UASG` | 4 | No | UASG and Órgão lookup: administrative units and government bodies |
| `01 - CATÁLOGO - MATERIAL` | 7 | No | Material catalog: groups, classes, PDM, items, units, characteristics |
| `06 - LEGADO` | 13 | No | Legacy data (Lei 8.666/93): bids, pregões, dispensas, RDC |
| `97 - INDICADORES` | 2 | No | API usage KPIs (consolidated and per-period) |
| `09 - CONTRATOS` | 5 | No | Contracts: active and ended contracts and contract items |
| `10 - FORNECEDOR` | 1 | No | Supplier lookup by CNPJ/CPF |
| `11 - OCDS` | 1 | No | Open Contracting Data Standard releases |

## 5. Endpoints Reference

### 98 - ALICE

#### `GET /alice/tickets` 🔒

**operationId:** `tickets`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `tickets` | query | Yes | `array<string>` |  |

**Response `200`** (`*/*`): `array<AnaliseAliceComItensResponseDTO>`

#### `GET /alice/compras` 🔒

**operationId:** `compras`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `chavesCompra` | query | Yes | `array<string>` |  |

**Response `200`** (`*/*`): `array<AnaliseAliceSemItensResponseDTO>`

#### `GET /alice/avisos-restritos` 🔒

**operationId:** `avisosRestritos`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `dataInicioIntervalo` | query | Yes | `string` | DD/MM/YYYY HH:MM:SS |
| `dataFimIntervalo` | query | Yes | `string` | DD/MM/YYYY HH:MM:SS |

**Response `200`** (`*/*`): `array<AnaliseAliceSemItensResponseDTO>`

### 02 - CATÁLOGO - SERVIÇO

#### `GET /modulo-servico/8_consultarNaturezaDespesaServico`

**operationId:** `consultarNaturezaDespesaServico`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `codigoServico` | query | No | `integer (int64)` |  |
| `codigoNaturezaDespesa` | query | No | `string` |  |
| `statusNaturezaDespesa` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `DmServicoNaturezaDespesaAPIResponseDTO`

#### `GET /modulo-servico/7_consultarUndMedidaServico`

**operationId:** `consultarUndMedidaServico`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `codigoServico` | query | No | `integer (int64)` |  |
| `statusUnidadeMedida` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `DmServicoUndMedidaAPIResponseDTO`

#### `GET /modulo-servico/6_consultarItemServico`

**operationId:** `consultarItemServico`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoSecao` | query | No | `integer (int64)` |  |
| `codigoDivisao` | query | No | `integer (int64)` |  |
| `codigoGrupo` | query | No | `integer (int64)` |  |
| `codigoClasse` | query | No | `integer (int64)` |  |
| `codigoSubclasse` | query | No | `integer (int64)` |  |
| `codigoCpc` | query | No | `integer (int64)` |  |
| `codigoServico` | query | No | `integer (int64)` |  |
| `exclusivoCentralCompras` | query | No | `boolean` |  |
| `statusServico` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `DmServicoItemAPIResponseDTO`

#### `GET /modulo-servico/5_consultarSubClasseServico`

**operationId:** `consultarSubClasseServico`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `codigoClasse` | query | No | `integer (int64)` |  |
| `codigoSubclasse` | query | No | `integer (int64)` |  |
| `statusSubclasse` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `DmServicoSubClasseAPIResponseDTO`

#### `GET /modulo-servico/4_consultarClasseServico`

**operationId:** `consultarClasseServico`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `codigoGrupo` | query | No | `integer (int64)` |  |
| `codigoClasse` | query | No | `integer (int64)` |  |
| `statusGrupo` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `DmServicoClasseAPIResponseDTO`

#### `GET /modulo-servico/3_consultarGrupoServico`

**operationId:** `consultarGrupoServico`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `codigoDivisao` | query | No | `integer (int64)` |  |
| `codigoGrupo` | query | No | `integer (int64)` |  |
| `statusGrupo` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `DmServicoGrupoAPIResponseDTO`

#### `GET /modulo-servico/2_consultarDivisaoServico`

**operationId:** `consultarDivisaoServico`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `codigoSecao` | query | No | `integer (int64)` |  |
| `codigoDivisao` | query | No | `integer (int64)` |  |
| `statusDivisao` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `DmServicoDivisaoAPIResponseDTO`

#### `GET /modulo-servico/1_consultarSecaoServico`

**operationId:** `consultarSecaoServico`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `codigoSecao` | query | No | `integer (int64)` |  |
| `statusSecao` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `DmServicoSecaoAPIResponseDTO`

### 04 - PGC

#### `GET /modulo-pgc/3_consultarPgcAgregacao`

**operationId:** `consultarPgcAgregacao`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `orgao` | query | Yes | `string` |  |
| `ano` | query | Yes | `integer (int32)` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOFtPgcAgregacaoDTO`

#### `GET /modulo-pgc/3.1_consultarPgcAgregacao_CSV`

**operationId:** `consultarPgcAgregacao_CSV`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `orgao` | query | Yes | `string` |  |
| `ano` | query | Yes | `integer (int32)` |  |

**Response `200`** (`text/csv`): `string (byte)`

#### `GET /modulo-pgc/2_consultarPgcDetalheCatalogo`

**operationId:** `consultarPgcDetalheCatalogo`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `anoPcaProjetoCompra` | query | Yes | `integer (int32)` |  |
| `tipo` | query | Yes | `string` |  |
| `codigo` | query | Yes | `integer (int32)` | Código de classe para material ou código do grupo para serviço |

**Response `200`** (`*/*`): `GenericAPIResponseDTOFtPgcDetalheDTO`

#### `GET /modulo-pgc/2.1_consultarPgcDetalheCatalogo_CSV`

**operationId:** `consultarPgcDetalheCatalogo_CSV`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `anoPcaProjetoCompra` | query | Yes | `integer (int32)` |  |
| `tipo` | query | Yes | `string` |  |
| `codigo` | query | Yes | `integer (int32)` | Código de classe para material ou código do grupo para serviço |

**Response `200`** (`text/csv`): `string (byte)`

#### `GET /modulo-pgc/1_consultarPgcDetalhe`

**operationId:** `consultarPgcDetalhe`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `orgao` | query | Yes | `string` |  |
| `anoPcaProjetoCompra` | query | Yes | `integer (int32)` |  |
| `codigoUasg` | query | No | `string` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOFtPgcDetalheDTO`

#### `GET /modulo-pgc/1.1_consultarPgcDetalhe_CSV`

**operationId:** `consultarPgcDetalhe_CSV`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `orgao` | query | Yes | `string` |  |
| `anoPcaProjetoCompra` | query | Yes | `integer (int32)` |  |
| `codigoUasg` | query | No | `string` |  |

**Response `200`** (`text/csv`): `string (byte)`

### AUTENTICACAO

#### `POST /autenticacao/login`

**operationId:** `login`

**Request body** (`application/json`): `AutenticacaoDTO`

**Response `200`** (`*/*`): `string`

### 08 - ARP

#### `GET /modulo-arp/5_consultarAdesoesItem`

**operationId:** `consultarAdesoesItem`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `numeroAta` | query | Yes | `string` |  |
| `unidadeGerenciadora` | query | Yes | `string` |  |
| `numeroItem` | query | Yes | `string` |  |
| `unidade` | query | No | `string` |  |
| `dataAtualizacao` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `VwFtArpAdesoesItemAPIResponseDTO`

#### `GET /modulo-arp/4_consultarEmpenhosSaldoItem`

**operationId:** `consultarEmpenhosItem`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `numeroAta` | query | Yes | `string` |  |
| `unidadeGerenciadora` | query | Yes | `string` |  |
| `dataAtualizacao` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `VwArpEmpenhosItemAPI`

#### `GET /modulo-arp/3_consultarUnidadesItem`

**operationId:** `consultarUnidadesItem`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `numeroAta` | query | Yes | `string` |  |
| `unidadeGerenciadora` | query | Yes | `string` |  |
| `numeroItem` | query | Yes | `string` |  |
| `dataAtualizacao` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `VwFtArpUnidadesItemAPIResponseDTO`

#### `GET /modulo-arp/2_consultarARPItem`

**operationId:** `consultarARPItem`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoUnidadeGerenciadora` | query | No | `integer (int32)` |  |
| `codigoModalidadeCompra` | query | No | `string` |  |
| `dataVigenciaInicialMin` | query | Yes | `string` | YYYY-MM-DD |
| `dataVigenciaInicialMax` | query | Yes | `string` | YYYY-MM-DD |
| `dataAssinaturaInicial` | query | No | `string` | YYYY-MM-DD |
| `dataAssinaturaFinal` | query | No | `string` | YYYY-MM-DD |
| `numeroItem` | query | No | `string` |  |
| `codigoItem` | query | No | `integer (int32)` |  |
| `tipoItem` | query | No | `string` |  |
| `niFornecedor` | query | No | `string` |  |
| `codigoPdm` | query | No | `integer (int32)` |  |
| `numeroCompra` | query | No | `string` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwFtArpItemDTO`

#### `GET /modulo-arp/2.1_consultarARPItem_Id`

**operationId:** `consultarARPItem_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `numeroControlePncpAta` | query | Yes | `string` |  |
| `dataAtualizacao` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwFtArpItemDTO`

#### `GET /modulo-arp/1_consultarARP`

**operationId:** `consultarARP`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoUnidadeGerenciadora` | query | No | `string` |  |
| `codigoModalidadeCompra` | query | No | `string` |  |
| `numeroAtaRegistroPreco` | query | No | `string` |  |
| `dataVigenciaInicialMin` | query | Yes | `string` | YYYY-MM-DD |
| `dataVigenciaInicialMax` | query | Yes | `string` | YYYY-MM-DD |
| `dataAssinaturaInicial` | query | No | `string` | YYYY-MM-DD |
| `dataAssinaturaFinal` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwFtArpDTO`

#### `GET /modulo-arp/1.2_consultarARP_FimVigencia`

**operationId:** `consultarARP_FimVigencia`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoUnidadeGerenciadora` | query | No | `string` |  |
| `codigoModalidadeCompra` | query | No | `string` |  |
| `numeroAtaRegistroPreco` | query | No | `string` |  |
| `dataVigenciaFinalMin` | query | Yes | `string` | YYYY-MM-DD |
| `dataVigenciaFinalMax` | query | Yes | `string` | YYYY-MM-DD |
| `dataAssinaturaInicial` | query | No | `string` | YYYY-MM-DD |
| `dataAssinaturaFinal` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwFtArpDTO`

#### `GET /modulo-arp/1.1_consultarARP_Id`

**operationId:** `consultarARP_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `numeroControlePncpAta` | query | Yes | `string` |  |
| `dataAtualizacao` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwFtArpDTO`

### 07 - CONTRATAÇÕES

#### `GET /modulo-contratacoes/3_consultarResultadoItensContratacoes_PNCP_14133`

**operationId:** `consultarResultadoItensContratacoes_PNCP_14133`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `unidadeOrgaoCodigoUnidade` | query | No | `string` |  |
| `orgaoEntidadeCnpj` | query | No | `string` |  |
| `niFornecedor` | query | No | `string` |  |
| `codigoPais` | query | No | `string` |  |
| `porteFornecedorId` | query | No | `integer (int32)` |  |
| `naturezaJuridicaId` | query | No | `string` |  |
| `situacaoCompraItemResultadoId` | query | No | `integer` |  |
| `valorUnitarioHomologadoInicial` | query | No | `number` |  |
| `valorUnitarioHomologadoFinal` | query | No | `number` |  |
| `valorTotalHomologadoInicial` | query | No | `number` |  |
| `valorTotalHomologadoFinal` | query | No | `number` |  |
| `dataResultadoPncpInicial` | query | Yes | `string` | YYYY-MM-DD |
| `dataResultadoPncpFinal` | query | Yes | `string` | YYYY-MM-DD |
| `aplicacaoMargemPreferencia` | query | No | `boolean` |  |
| `aplicacaoBeneficioMeepp` | query | No | `boolean` |  |
| `aplicacaoCriterioDesempate` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `VwDmPNCPItemResultadoAPIResponseDTO`

#### `GET /modulo-contratacoes/3.1_consultarResultadoItensContratacoes_PNCP_14133_Id`

**operationId:** `consultarResultadoItensContratacoes_PNCP_14133_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `tipo` | query | Yes | `string` |  |
| `codigo` | query | Yes | `string` |  |
| `idCompraItem` | query | No | `string` |  |
| `dataAtualizacaoPncp` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `VwDmPNCPItemResultadoAPIResponseDTO`

#### `GET /modulo-contratacoes/2_consultarItensContratacoes_PNCP_14133`

**operationId:** `consultarItensContratacoes_PNCP_14133`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `unidadeOrgaoCodigoUnidade` | query | No | `string` |  |
| `orgaoEntidadeCnpj` | query | No | `string` |  |
| `situacaoCompraItem` | query | No | `string` |  |
| `materialOuServico` | query | No | `string` |  |
| `codigoClasse` | query | No | `integer (int32)` |  |
| `codigoGrupo` | query | No | `integer (int32)` |  |
| `codItemCatalogo` | query | No | `integer (int32)` |  |
| `temResultado` | query | No | `boolean` |  |
| `codFornecedor` | query | No | `string` |  |
| `dataInclusaoPncpInicial` | query | Yes | `string` | YYYY-MM-DD |
| `dataInclusaoPncpFinal` | query | Yes | `string` | YYYY-MM-DD |
| `dataAtualizacaoPncp` | query | No | `string` |  |
| `bps` | query | No | `boolean` |  |
| `margemPreferenciaNormal` | query | No | `boolean` |  |
| `codigoNCM` | query | No | `string` |  |

**Response `200`** (`*/*`): `VwFtPNCPCompraItemAPIResponseDTO`

#### `GET /modulo-contratacoes/2.1_consultarItensContratacoes_PNCP_14133_Id`

**operationId:** `consultarItensContratacoes_PNCP_14133_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `tipo` | query | Yes | `string` |  |
| `codigo` | query | Yes | `string` |  |
| `idCompraItem` | query | No | `string` |  |
| `dataAtualizacaoPncp` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `VwFtPNCPCompraItemAPIResponseDTO`

#### `GET /modulo-contratacoes/1_consultarContratacoes_PNCP_14133`

**operationId:** `consultarContratacoes_PNCP_14133`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `unidadeOrgaoCodigoUnidade` | query | No | `string` |  |
| `codigoOrgao` | query | No | `integer (int32)` |  |
| `orgaoEntidadeCnpj` | query | No | `string` |  |
| `dataPublicacaoPncpInicial` | query | Yes | `string` | YYYY-MM-DD |
| `dataPublicacaoPncpFinal` | query | Yes | `string` | YYYY-MM-DD |
| `codigoModalidade` | query | Yes | `integer (int32)` |  |
| `unidadeOrgaoCodigoIbge` | query | No | `integer` |  |
| `unidadeOrgaoUfSigla` | query | No | `string` |  |
| `dataAualizacaoPncp` | query | No | `string` | YYYY-MM-DD |
| `amparoLegalCodigoPncp` | query | No | `integer (int32)` |  |
| `contratacaoExcluida` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `VwFtPNCPCompraAPIResponseDTO`

#### `GET /modulo-contratacoes/1.1_consultarContratacoes_PNCP_14133_Id`

**operationId:** `consultarContratacoes_PNCP_14133_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `tipo` | query | Yes | `string` |  |
| `codigo` | query | Yes | `string` |  |
| `dataAtualizacaoPncp` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `VwFtPNCPCompraAPIResponseDTO`

### 03 - PESQUISA DE PREÇO - PREÇOS PRATICADOS

#### `GET /modulo-pesquisa-preco/4_consultarServicoDetalhe`

**operationId:** `consultarServicoDetalhe`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoItemCatalogo` | query | Yes | `integer (int32)` |  |
| `dataCompraInicio` | query | No | `string` | YYYY-MM-DD |
| `dataCompraFim` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `FtPesqPrecoCompraServicoDetalheAPIResponseDTO`

#### `GET /modulo-pesquisa-preco/4.1_consultarServicoDetalhe_CSV`

**operationId:** `consultarServicoDetalheCSV`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoItemCatalogo` | query | No | `integer (int32)` |  |
| `dataCompraInicio` | query | No | `string` | YYYY-MM-DD |
| `dataCompraFim` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`text/csv`): `string (byte)`

#### `GET /modulo-pesquisa-preco/3_consultarServico`

**operationId:** `consultarServico`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoItemCatalogo` | query | Yes | `integer (int32)` |  |
| `codigoUasg` | query | No | `string` |  |
| `estado` | query | No | `string` |  |
| `codigoMunicipio` | query | No | `integer (int32)` |  |
| `dataResultado` | query | No | `boolean` |  |
| `poder` | query | No | `string` |  |
| `esfera` | query | No | `string` |  |
| `dataCompraInicio` | query | No | `string` | YYYY-MM-DD |
| `dataCompraFim` | query | No | `string` | YYYY-MM-DD |
| `idCompra` | query | No | `string` |  |

**Response `200`** (`*/*`): `FtPesqPrecoCompraServicoAPIResponseDTO`

#### `GET /modulo-pesquisa-preco/3.1_consultarServico_CSV`

**operationId:** `consultarServicoCSV`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoItemCatalogo` | query | Yes | `integer (int32)` |  |
| `codigoUasg` | query | No | `string` |  |
| `estado` | query | No | `string` |  |
| `codigoMunicipio` | query | No | `integer (int32)` |  |
| `dataResultado` | query | No | `boolean` |  |
| `poder` | query | No | `string` |  |
| `esfera` | query | No | `string` |  |
| `dataCompraInicio` | query | No | `string` | YYYY-MM-DD |
| `dataCompraFim` | query | No | `string` | YYYY-MM-DD |
| `idCompra` | query | No | `string` |  |

**Response `200`** (`text/csv`): `string (byte)`

#### `GET /modulo-pesquisa-preco/2_consultarMaterialDetalhe`

**operationId:** `consultarMaterialDetalhe`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoItemCatalogo` | query | Yes | `integer (int32)` |  |
| `dataCompraInicio` | query | No | `string` | YYYY-MM-DD |
| `dataCompraFim` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `FtPesqPrecoCompraMaterialDetalheAPIResponseDTO`

#### `GET /modulo-pesquisa-preco/2.1_consultarMaterialDetalhe_CSV`

**operationId:** `consultarMaterialDetalheCSV`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoItemCatalogo` | query | No | `integer (int32)` |  |
| `dataCompraInicio` | query | No | `string` | YYYY-MM-DD |
| `dataCompraFim` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`text/csv`): `string (byte)`

#### `GET /modulo-pesquisa-preco/1_consultarMaterial`

**operationId:** `consultarMaterial`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoItemCatalogo` | query | Yes | `integer (int32)` |  |
| `codigoUasg` | query | No | `string` |  |
| `estado` | query | No | `string` |  |
| `codigoMunicipio` | query | No | `integer (int32)` |  |
| `dataResultado` | query | No | `boolean` |  |
| `codigoClasse` | query | No | `integer (int32)` |  |
| `poder` | query | No | `string` |  |
| `esfera` | query | No | `string` |  |
| `idCompra` | query | No | `string` |  |
| `dataCompraInicio` | query | No | `string` | YYYY-MM-DD |
| `dataCompraFim` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `FtPesqPrecoCompraMaterialAPIResponseDTO`

#### `GET /modulo-pesquisa-preco/1.1_consultarMaterial_CSV`

**operationId:** `consultarMaterialCSV`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoItemCatalogo` | query | Yes | `integer (int32)` |  |
| `codigoUasg` | query | No | `string` |  |
| `estado` | query | No | `string` |  |
| `codigoMunicipio` | query | No | `integer (int32)` |  |
| `dataResultado` | query | No | `boolean` |  |
| `codigoClasse` | query | No | `integer (int32)` |  |
| `poder` | query | No | `string` |  |
| `esfera` | query | No | `string` |  |
| `idCompra` | query | No | `string` |  |
| `dataCompraInicio` | query | No | `string` | YYYY-MM-DD |
| `dataCompraFim` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`text/csv`): `string (byte)`

### 99 - USUARIOS

#### `POST /usuarios/criar` 🔒

**operationId:** `criar`

**Request body** (`application/json`): `UsuariosDTO`

**Response `200`** (`*/*`): `UsuariosDTOResponse`

#### `PATCH /usuarios/resetSenha/{id}` 🔒

**operationId:** `resetSenha`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `id` | path | Yes | `integer (int32)` |  |

**Response `200`** (`*/*`): `string`

#### `PATCH /usuarios/atualizar/{id}` 🔒

**operationId:** `atualizar`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `id` | path | Yes | `integer (int32)` |  |

**Request body** (`application/json`): `UsuariosDTO`

**Response `200`** (`*/*`): `UsuariosResponseDTO`

#### `GET /usuarios/consultar` 🔒

**operationId:** `consultar`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `id` | query | No | `integer (int32)` |  |

**Response `200`** (`*/*`): `array<UsuariosResponseDTO>`

### 05 - UASG

#### `GET /modulo-uasg/2_consultarOrgao`

**operationId:** `consultarOrgao`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `cnpjCpfOrgao` | query | No | `string` |  |
| `cnpjCpfOrgaoVinculado` | query | No | `string` |  |
| `cnpjCpfOrgaoSuperior` | query | No | `string` |  |
| `codigoOrgao` | query | No | `integer (int32)` |  |
| `statusOrgao` | query | Yes | `boolean` |  |
| `usoSisg` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `DmCorpOrgaoAPIResponseDTO`

#### `GET /modulo-uasg/2.1_consultarOrgao_CSV`

**operationId:** `consultarOrgaoCSV`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `cnpjCpfOrgao` | query | No | `string` |  |
| `cnpjCpfOrgaoVinculado` | query | No | `string` |  |
| `cnpjCpfOrgaoSuperior` | query | No | `string` |  |
| `codigoOrgao` | query | No | `integer (int32)` |  |
| `statusOrgao` | query | Yes | `boolean` |  |
| `usoSisg` | query | No | `boolean` |  |

**Response `200`** (`text/csv`): `string (byte)`

#### `GET /modulo-uasg/1_consultarUasg`

**operationId:** `consultarUasg`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `codigoUasg` | query | No | `string` |  |
| `usoSisg` | query | No | `boolean` |  |
| `cnpjCpfOrgao` | query | No | `string` |  |
| `cnpjCpfOrgaoVinculado` | query | No | `string` |  |
| `cnpjCpfOrgaoSuperior` | query | No | `string` |  |
| `siglaUf` | query | No | `string` |  |
| `statusUasg` | query | Yes | `boolean` |  |

**Response `200`** (`*/*`): `DmCorpUasgAPIResponseDTO`

#### `GET /modulo-uasg/1.1_consultarUasg_CSV`

**operationId:** `consultarUasgCSV`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `codigoUasg` | query | No | `string` |  |
| `usoSisg` | query | No | `boolean` |  |
| `cnpjCpfOrgao` | query | No | `string` |  |
| `cnpjCpfOrgaoVinculado` | query | No | `string` |  |
| `cnpjCpfOrgaoSuperior` | query | No | `string` |  |
| `siglaUf` | query | No | `string` |  |
| `statusUasg` | query | Yes | `boolean` |  |

**Response `200`** (`text/csv`): `string (byte)`

### 01 - CATÁLOGO - MATERIAL

#### `GET /modulo-material/7_consultarMaterialCaracteristicas`

**operationId:** `consultarMaterialCaracteristicas`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoItem` | query | No | `integer (int64)` |  |

**Response `200`** (`*/*`): `DmMaterialCaracteristicasAPIResponseDTO`

#### `GET /modulo-material/6_consultarMaterialUnidadeFornecimento`

**operationId:** `consultarMaterialUnidadeFornecimento`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoPdm` | query | No | `integer (int64)` |  |
| `statusUnidadeFornecimentoPdm` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `DmMaterialUnidadeFornecimentoAPIResponseDTO`

#### `GET /modulo-material/5_consultarMaterialNaturezaDespesa`

**operationId:** `consultarMaterialNaturezaDespesa`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoPdm` | query | No | `integer (int64)` |  |
| `codigoNaturezaDespesa` | query | No | `string` |  |
| `statusNaturezaDespesa` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `DmMaterialNaturezaDespesaAPIResponseDTO`

#### `GET /modulo-material/4_consultarItemMaterial`

**operationId:** `consultarItemMaterial`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoItem` | query | No | `integer (int64)` |  |
| `codigoGrupo` | query | No | `integer (int64)` |  |
| `codigoClasse` | query | No | `integer (int64)` |  |
| `codigoPdm` | query | No | `integer (int64)` |  |
| `descricaoItem` | query | No | `string` |  |
| `statusItem` | query | No | `boolean` |  |
| `bps` | query | No | `boolean` |  |
| `codigo_ncm` | query | No | `string` |  |

**Response `200`** (`*/*`): `DmMaterialItemAPIResponseDTO`

#### `GET /modulo-material/3_consultarPdmMaterial`

**operationId:** `consultarPdmMaterial`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `statusPdm` | query | No | `boolean` |  |
| `codigoPdm` | query | No | `integer (int64)` |  |
| `codigoGrupo` | query | No | `integer (int64)` |  |
| `codigoClasse` | query | No | `integer (int64)` |  |
| `bps` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `DmMaterialPDMAPIResponseDTO`

#### `GET /modulo-material/2_consultarClasseMaterial`

**operationId:** `consultarClasseMaterial`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `codigoGrupo` | query | No | `integer (int64)` |  |
| `codigoClasse` | query | No | `integer (int64)` |  |
| `statusClasse` | query | No | `boolean` |  |
| `bps` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTODmMaterialClasseDTO`

#### `GET /modulo-material/1_consultarGrupoMaterial`

**operationId:** `consultarGrupoMaterial`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `codigoGrupo` | query | No | `integer (int64)` |  |
| `statusGrupo` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTODmMaterialGrupoDTO`

### 06 - LEGADO

#### `GET /modulo-legado/7_consultarRdc`

**operationId:** `consultarRdc`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `data_publicacao_min` | query | Yes | `string` | YYYY-MM-DD |
| `data_publicacao_max` | query | Yes | `string` | YYYY-MM-DD |
| `endereco_entrega_edital` | query | No | `string` |  |
| `forma_de_realizacao` | query | No | `string` |  |
| `funcao_responsavel` | query | No | `string` |  |
| `modalidade` | query | No | `integer (int32)` |  |
| `nome_responsavel` | query | No | `string` |  |
| `numero_aviso` | query | No | `integer (int32)` |  |
| `objeto` | query | No | `string` |  |
| `orgao` | query | No | `integer (int32)` |  |
| `situacao_aviso` | query | No | `string` |  |
| `uasg` | query | No | `integer (int32)` |  |
| `uf_uasg` | query | No | `string` |  |
| `valor_estimado_total_max` | query | No | `number` |  |
| `valor_estimado_total_min` | query | No | `number` |  |
| `valor_homologado_total_max` | query | No | `number` |  |
| `valor_homologado_total_min` | query | No | `number` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwRdcDTO`

#### `GET /modulo-legado/6_consultarCompraItensSemLicitacao`

**operationId:** `consultarCompraItensSemLicitacao`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `co_uasg` | query | No | `integer` |  |
| `co_orgao` | query | No | `string` |  |
| `dt_ano_aviso_licitacao` | query | Yes | `integer (int32)` |  |
| `co_modalidade_licitacao` | query | No | `integer (int32)` |  |
| `co_conjunto_materiais` | query | No | `integer (int32)` |  |
| `co_servico` | query | No | `integer (int32)` |  |
| `nu_cpf_cnpj_fornecedor` | query | No | `string` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwCompraItensSemLicitacaoDTO`

#### `GET /modulo-legado/6.1_consultarItensComprasSemLicitacao_Id`

**operationId:** `consultarItensComprasSemLicitacao_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `id_compra` | query | Yes | `string` |  |
| `id_compra_item` | query | No | `string` |  |
| `dt_alteracao` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwCompraItensSemLicitacaoDTO`

#### `GET /modulo-legado/5_consultarComprasSemLicitacao`

**operationId:** `consultarComprasSemLicitacao`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `dt_ano_aviso` | query | Yes | `integer (int32)` |  |
| `nu_aviso_licitacao` | query | No | `integer (int64)` |  |
| `co_modalidade_licitacao` | query | No | `integer (int32)` |  |
| `co_orgao` | query | No | `string` |  |
| `co_orgao_superior` | query | No | `string` |  |
| `co_uasg` | query | No | `integer (int64)` |  |
| `dtDeclaracaoDispensaInicial` | query | No | `string` | YYYY-MM-DD |
| `dtDeclaracaoDispensaFinal` | query | No | `string` | YYYY-MM-DD |
| `dtRatificacao` | query | No | `string` | YYYY-MM-DD |
| `dtPublicacao` | query | No | `string` | YYYY-MM-DD |
| `pertence14133` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwComprasSemLicitacaoDTO`

#### `GET /modulo-legado/5.1_consultarCompraSemLicitacao_Id`

**operationId:** `consultarCompraSemLicitacao_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `idCompra` | query | Yes | `string` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwComprasSemLicitacaoDTO`

#### `GET /modulo-legado/4_consultarItensPregoes`

**operationId:** `consultarItensPregoes`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `co_uasg` | query | No | `integer (int32)` |  |
| `decreto_7174` | query | No | `string` |  |
| `fornecedor_vencedor` | query | No | `string` |  |
| `dt_hom_inicial` | query | Yes | `string` | YYYY-MM-DD |
| `dt_hom_final` | query | Yes | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwItensPregaoDTO`

#### `GET /modulo-legado/4.1_consultarItensPregoes_Id`

**operationId:** `consultarItensPregoes_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `id_compra` | query | Yes | `string` |  |
| `id_compra_item` | query | No | `string` |  |
| `dt_alteracao` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwItensPregaoDTO`

#### `GET /modulo-legado/3_consultarPregoes`

**operationId:** `consultarPregoes`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `co_uasg` | query | No | `integer (int32)` |  |
| `co_orgao` | query | No | `integer (int32)` |  |
| `numero` | query | No | `integer (int32)` |  |
| `ds_tipo_pregao_compra` | query | No | `string` |  |
| `dt_data_edital_inicial` | query | Yes | `string` | YYYY-MM-DD |
| `dt_data_edital_final` | query | Yes | `string` | YYYY-MM-DD |
| `pertence14133` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwPregaoDTO`

#### `GET /modulo-legado/3.1_consultarPregoes_Id`

**operationId:** `consultarPregoes_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `id_compra` | query | Yes | `string` |  |
| `dt_alteracao` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwPregaoDTO`

#### `GET /modulo-legado/2_consultarItemLicitacao`

**operationId:** `consultarItemLicitacao`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `uasg` | query | No | `integer (int32)` |  |
| `numero_aviso` | query | No | `integer (int32)` |  |
| `modalidade` | query | Yes | `integer (int32)` |  |
| `decreto_7174` | query | No | `boolean` |  |
| `codigo_item_material` | query | No | `integer (int32)` |  |
| `codigo_item_servico` | query | No | `integer (int32)` |  |
| `cnpj_fornecedor` | query | No | `string` |  |
| `cpfVencedor` | query | No | `string` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwItemLicitacaoDTO`

#### `GET /modulo-legado/2.1_consultarItemLicitacao_Id`

**operationId:** `consultarItemLicitacao_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `id_compra` | query | Yes | `string` |  |
| `id_compra_item` | query | No | `string` |  |
| `dt_alteracao` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwItemLicitacaoDTO`

#### `GET /modulo-legado/1_consultarLicitacao`

**operationId:** `consultarLicitacao`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `uasg` | query | No | `integer (int32)` |  |
| `numero_aviso` | query | No | `integer (int32)` |  |
| `modalidade` | query | No | `integer (int32)` |  |
| `data_publicacao_inicial` | query | Yes | `string` | YYYY-MM-DD |
| `data_publicacao_final` | query | Yes | `string` | YYYY-MM-DD |
| `pertence14133` | query | No | `boolean` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwLicitacaoDTO`

#### `GET /modulo-legado/1.1_consultarLicitacao_Id`

**operationId:** `consultarLicitacao_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `id_compra` | query | Yes | `string` |  |
| `dt_alteracao` | query | No | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `GenericAPIResponseDTOTbVwLicitacaoDTO`

### 97 - INDICADORES

#### `GET /modulo-indicadores/2_consultarIndicadoresPorPeriodo`

**operationId:** `consultarIndicadoresPorPeriodo`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `ano` | query | Yes | `integer (int32)` |  |
| `mes` | query | No | `integer (int32)` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwKpisConsolidadosDTO`

#### `GET /modulo-indicadores/1_consultarIndicadoresConsolidados`

**operationId:** `consultarIndicadoresConsolidados`

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwKpisGeralDTO`

### 09 - CONTRATOS

#### `GET /modulo-contratos/2_consultarContratosItem`

**operationId:** `consultarContratosItem`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoOrgao` | query | Yes | `string` |  |
| `codigoUnidadeGestora` | query | No | `string` |  |
| `codigoUnidadeGestoraOrigemContrato` | query | No | `string` |  |
| `codigoUnidadeRealizadoraCompra` | query | No | `string` |  |
| `numeroContrato` | query | No | `string` |  |
| `codigoModalidadeCompra` | query | No | `string` |  |
| `tipoItem` | query | No | `string` |  |
| `codigoItem` | query | No | `integer (int32)` |  |
| `niFornecedor` | query | No | `string` |  |
| `dataVigenciaInicialMin` | query | Yes | `string` | YYYY-MM-DD |
| `dataVigenciaInicialMax` | query | Yes | `string` | YYYY-MM-DD |
| `poder` | query | No | `string` |  |
| `esfera` | query | No | `string` |  |
| `idCompra` | query | No | `string` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwFtContratoItemDTO`

#### `GET /modulo-contratos/2.1_consultarContratosItem_Id`

**operationId:** `consultarContratosItem_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `tipo` | query | Yes | `string` |  |
| `codigo` | query | Yes | `string` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwFtContratoItemDTO`

#### `GET /modulo-contratos/1_consultarContratos`

**operationId:** `consultarContratos`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoOrgao` | query | Yes | `string` |  |
| `codigoUnidadeGestora` | query | No | `string` |  |
| `codigoUnidadeGestoraOrigemContrato` | query | No | `string` |  |
| `codigoUnidadeRealizadoraCompra` | query | No | `string` |  |
| `numeroContrato` | query | No | `string` |  |
| `codigoModalidadeCompra` | query | No | `string` |  |
| `codigoTipo` | query | No | `string` |  |
| `codigoCategoria` | query | No | `string` |  |
| `niFornecedor` | query | No | `string` |  |
| `dataVigenciaInicialMin` | query | Yes | `string` | YYYY-MM-DD |
| `dataVigenciaInicialMax` | query | Yes | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwFtContratoDTO`

#### `GET /modulo-contratos/1.2_consultarContratos_FimVigencia`

**operationId:** `consultarContratos_FimVigencia`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `codigoOrgao` | query | Yes | `string` |  |
| `codigoUnidadeGestora` | query | No | `string` |  |
| `codigoUnidadeGestoraOrigemContrato` | query | No | `string` |  |
| `codigoUnidadeRealizadoraCompra` | query | No | `string` |  |
| `numeroContrato` | query | No | `string` |  |
| `codigoModalidadeCompra` | query | No | `string` |  |
| `codigoTipo` | query | No | `string` |  |
| `codigoCategoria` | query | No | `string` |  |
| `niFornecedor` | query | No | `string` |  |
| `dataVigenciaFinalMin` | query | Yes | `string` | YYYY-MM-DD |
| `dataVigenciaFinalMax` | query | Yes | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwFtContratoDTO`

#### `GET /modulo-contratos/1.1_consultarContratos_Id`

**operationId:** `consultarContratos_Id`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `codigo` | query | Yes | `string` |  |
| `tipo` | query | Yes | `string` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwFtContratoDTO`

### 10 - FORNECEDOR

#### `GET /modulo-fornecedor/1_consultarFornecedor`

**operationId:** `consultarFornecedor`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `pagina` | query | No | `integer (int32)` |  |
| `tamanhoPagina` | query | No | `integer (int32)` |  |
| `cnpj` | query | No | `string` |  |
| `cpf` | query | No | `string` |  |
| `naturezaJuridicaId` | query | No | `integer (int64)` |  |
| `porteEmpresaId` | query | No | `integer (int64)` |  |
| `codigoCnae` | query | No | `integer` |  |
| `ativo` | query | Yes | `boolean` |  |

**Response `200`** (`*/*`): `GenericAPIResponseDTOVwFtFornecedorDTO`

### 11 - OCDS

#### `GET /modulo-ocds/1_releases`

**operationId:** `releases`

**Parameters:**

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `page` | query | No | `integer (int32)` |  |
| `offSet` | query | No | `integer (int32)` |  |
| `buyerID` | query | Yes | `string` | BR-CNPJ |
| `releaseStartDate` | query | Yes | `string` | YYYY-MM-DD |
| `releaseEndDate` | query | Yes | `string` | YYYY-MM-DD |

**Response `200`** (`*/*`): `VwOCDSApiResponseDTO`

## 6. Response Schemas (Key DTOs)

This section documents the most important data-transfer objects.
All paginated responses share a common wrapper.

### 6.1 Common Pagination Wrapper

Every list endpoint returns a response shaped like:

```json
{
  "resultado": [ ... ],
  "totalRegistros": 1234,
  "totalPaginas": 50,
  "paginasRestantes": 49
}
```

### 6.2 Contracts

**Contract record (Lei 14.133 / PNCP).**

| Field | Type | Description |
|---|---|---|
| `codigoOrgao` | `string` |  |
| `nomeOrgao` | `string` |  |
| `codigoUnidadeGestora` | `string` |  |
| `nomeUnidadeGestora` | `string` |  |
| `codigoUnidadeGestoraOrigemContrato` | `string` |  |
| `nomeUnidadeGestoraOrigemContrato` | `string` |  |
| `receitaDespesa` | `string` |  |
| `numeroContrato` | `string` |  |
| `codigoUnidadeRealizadoraCompra` | `string` |  |
| `nomeUnidadeRealizadoraCompra` | `string` |  |
| `numeroCompra` | `string` |  |
| `codigoModalidadeCompra` | `string` |  |
| `nomeModalidadeCompra` | `string` |  |
| `codigoTipo` | `string` |  |
| `nomeTipo` | `string` |  |
| `codigoCategoria` | `string` |  |
| `nomeCategoria` | `string` |  |
| `codigoSubcategoria` | `string` |  |
| `nomeSubcategoria` | `string` |  |
| `niFornecedor` | `string` |  |
| `nomeRazaoSocialFornecedor` | `string` |  |
| `processo` | `string` |  |
| `objeto` | `string` |  |
| `informacoesComplementares` | `string` |  |
| `dataVigenciaInicial` | `string (date-time)` | YYYY-MM-DD |
| `dataVigenciaFinal` | `string (date-time)` | YYYY-MM-DD |
| `valorGlobal` | `number` |  |
| `numeroParcelas` | `integer (int32)` |  |
| `valorParcela` | `number` |  |
| `valorAcumulado` | `number` |  |
| `totalDespesasAcessorias` | `number` |  |
| `dataHoraInclusao` | `string (date-time)` | YYYY-MM-DD |
| `numeroControlePncpContrato` | `string` |  |
| `numeroControlePncpCompra` | `string` |  |
| `idCompra` | `string` |  |
| `dataHoraExclusao` | `string (date-time)` | YYYY-MM-DD |
| `contratoExcluido` | `boolean` |  |
| `unidadesRequisitantes` | `string` |  |

**Example:**

```json
{
  "codigoOrgao": "example",
  "nomeOrgao": "example",
  "codigoUnidadeGestora": "example",
  "nomeUnidadeGestora": "example",
  "codigoUnidadeGestoraOrigemContrato": "example",
  "nomeUnidadeGestoraOrigemContrato": "example",
  "receitaDespesa": "example",
  "numeroContrato": "example",
  "codigoUnidadeRealizadoraCompra": "example",
  "nomeUnidadeRealizadoraCompra": "example",
  "numeroCompra": "example",
  "codigoModalidadeCompra": "example",
  "nomeModalidadeCompra": "example",
  "codigoTipo": "example",
  "nomeTipo": "example",
  "codigoCategoria": "example",
  "nomeCategoria": "example",
  "codigoSubcategoria": "example",
  "nomeSubcategoria": "example",
  "niFornecedor": "example",
  "nomeRazaoSocialFornecedor": "example",
  "processo": "example",
  "objeto": "example",
  "informacoesComplementares": "example",
  "dataVigenciaInicial": "2025-01-15",
  "dataVigenciaFinal": "2025-01-15",
  "valorGlobal": 0.0,
  "numeroParcelas": 1,
  "valorParcela": 0.0,
  "valorAcumulado": 0.0,
  "totalDespesasAcessorias": 0.0,
  "dataHoraInclusao": "2025-01-15",
  "numeroControlePncpContrato": "example",
  "numeroControlePncpCompra": "example",
  "idCompra": "example",
  "dataHoraExclusao": "2025-01-15",
  "contratoExcluido": true,
  "unidadesRequisitantes": "example"
}
```

### 6.3 Contract Items

**Individual item within a contract.**

| Field | Type | Description |
|---|---|---|
| `codigoOrgao` | `string` |  |
| `codigoUnidadeGestora` | `string` |  |
| `codigoUnidadeGestoraOrigemContrato` | `string` |  |
| `codigoUnidadeRealizadoraCompra` | `string` |  |
| `codigoModalidadeCompra` | `string` |  |
| `numeroContrato` | `string` |  |
| `niFornecedor` | `string` |  |
| `nomeRazaoSocialFornecedor` | `string` |  |
| `processo` | `string` |  |
| `dataVigenciaInicial` | `string (date-time)` | YYYY-MM-DD |
| `dataVigenciaFinal` | `string (date-time)` | YYYY-MM-DD |
| `valorGlobal` | `number` |  |
| `tipoItem` | `string` |  |
| `codigoItem` | `integer (int32)` |  |
| `descricaoIitem` | `string` |  |
| `quantidadeItem` | `integer (int32)` |  |
| `valorUnitarioItem` | `number` |  |
| `valorTotalItem` | `number` |  |
| `dataHoraInclusao` | `string (date-time)` | YYYY-MM-DD |
| `numeroControlePncpContrato` | `string` |  |
| `idCompra` | `string` |  |
| `dataHoraExclusaoContrato` | `string (date-time)` | YYYY-MM-DD |
| `contratoExcluido` | `boolean` |  |
| `nomeOrgao` | `string` |  |
| `nomeUnidadeGestora` | `string` |  |
| `nomeUnidadeGestoraOrigemContrato` | `string` |  |
| `nomeUnidadeRealizadoraCompra` | `string` |  |
| `nomeModalidadeCompra` | `string` |  |
| `numeroCompra` | `string` |  |
| `dataHoraExclusaoItem` | `string (date-time)` | YYYY-MM-DD |
| `contratoItemExcluido` | `boolean` |  |
| `numeroItem` | `string` |  |
| `esfera` | `string` |  |
| `poder` | `string` |  |
| `numeroControlePncpCompra` | `string` |  |

**Example:**

```json
{
  "codigoOrgao": "example",
  "codigoUnidadeGestora": "example",
  "codigoUnidadeGestoraOrigemContrato": "example",
  "codigoUnidadeRealizadoraCompra": "example",
  "codigoModalidadeCompra": "example",
  "numeroContrato": "example",
  "niFornecedor": "example",
  "nomeRazaoSocialFornecedor": "example",
  "processo": "example",
  "dataVigenciaInicial": "2025-01-15",
  "dataVigenciaFinal": "2025-01-15",
  "valorGlobal": 0.0,
  "tipoItem": "example",
  "codigoItem": 1,
  "descricaoIitem": "example",
  "quantidadeItem": 1,
  "valorUnitarioItem": 0.0,
  "valorTotalItem": 0.0,
  "dataHoraInclusao": "2025-01-15",
  "numeroControlePncpContrato": "example",
  "idCompra": "example",
  "dataHoraExclusaoContrato": "2025-01-15",
  "contratoExcluido": true,
  "nomeOrgao": "example",
  "nomeUnidadeGestora": "example",
  "nomeUnidadeGestoraOrigemContrato": "example",
  "nomeUnidadeRealizadoraCompra": "example",
  "nomeModalidadeCompra": "example",
  "numeroCompra": "example",
  "dataHoraExclusaoItem": "2025-01-15",
  "contratoItemExcluido": true,
  "numeroItem": "example",
  "esfera": "example",
  "poder": "example",
  "numeroControlePncpCompra": "example"
}
```

### 6.4 ARP (Price Register)

**Ata de Registro de Preço header.**

| Field | Type | Description |
|---|---|---|
| `numeroAtaRegistroPreco` | `string` |  |
| `codigoUnidadeGerenciadora` | `string` |  |
| `nomeUnidadeGerenciadora` | `string` |  |
| `codigoOrgao` | `integer (int32)` |  |
| `nomeOrgao` | `string` |  |
| `linkAtaPNCP` | `string` |  |
| `linkCompraPNCP` | `string` |  |
| `numeroCompra` | `string` |  |
| `anoCompra` | `string` |  |
| `codigoModalidadeCompra` | `string` |  |
| `nomeModalidadeCompra` | `string` |  |
| `dataAssinatura` | `string (date)` | YYYY-MM-DD |
| `dataVigenciaInicial` | `string (date)` | YYYY-MM-DD |
| `dataVigenciaFinal` | `string (date)` | YYYY-MM-DD |
| `valorTotal` | `number` |  |
| `statusAta` | `string` |  |
| `objeto` | `string` |  |
| `quantidadeItens` | `integer` |  |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraInclusao` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraExclusao` | `string (date-time)` | YYYY-MM-DD |
| `ataExcluido` | `boolean` |  |
| `numeroControlePncpAta` | `string` |  |
| `numeroControlePncpCompra` | `string` |  |
| `idCompra` | `string` |  |

**Example:**

```json
{
  "numeroAtaRegistroPreco": "example",
  "codigoUnidadeGerenciadora": "example",
  "nomeUnidadeGerenciadora": "example",
  "codigoOrgao": 1,
  "nomeOrgao": "example",
  "linkAtaPNCP": "example",
  "linkCompraPNCP": "example",
  "numeroCompra": "example",
  "anoCompra": "example",
  "codigoModalidadeCompra": "example",
  "nomeModalidadeCompra": "example",
  "dataAssinatura": "2025-01-15",
  "dataVigenciaInicial": "2025-01-15",
  "dataVigenciaFinal": "2025-01-15",
  "valorTotal": 0.0,
  "statusAta": "example",
  "objeto": "example",
  "quantidadeItens": 1,
  "dataHoraAtualizacao": "2025-01-15",
  "dataHoraInclusao": "2025-01-15",
  "dataHoraExclusao": "2025-01-15",
  "ataExcluido": true,
  "numeroControlePncpAta": "example",
  "numeroControlePncpCompra": "example",
  "idCompra": "example"
}
```

### 6.5 ARP Items

**Individual item within an ARP.**

| Field | Type | Description |
|---|---|---|
| `numeroAtaRegistroPreco` | `string` |  |
| `codigoUnidadeGerenciadora` | `string` |  |
| `numeroCompra` | `string` |  |
| `anoCompra` | `string` |  |
| `codigoModalidadeCompra` | `string` |  |
| `dataAssinatura` | `string (date-time)` | YYYY-MM-DD |
| `dataVigenciaInicial` | `string (date)` |  |
| `dataVigenciaFinal` | `string (date)` |  |
| `numeroItem` | `string` |  |
| `codigoItem` | `integer (int32)` |  |
| `descricaoItem` | `string` |  |
| `tipoItem` | `string` |  |
| `quantidadeHomologadaItem` | `number` |  |
| `classificacaoFornecedor` | `string` |  |
| `niFornecedor` | `string` |  |
| `nomeRazaoSocialFornecedor` | `string` |  |
| `quantidadeHomologadaVencedor` | `number` |  |
| `valorUnitario` | `number` |  |
| `valorTotal` | `number` |  |
| `maximoAdesao` | `number` |  |
| `nomeUnidadeGerenciadora` | `string` |  |
| `nomeModalidadeCompra` | `string` |  |
| `idCompra` | `string` |  |
| `numeroControlePncpCompra` | `string` |  |
| `dataHoraInclusao` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |
| `quantidadeEmpenhada` | `number` |  |
| `percentualMaiorDesconto` | `number` |  |
| `situacaoSicaf` | `string` |  |
| `dataHoraExclusao` | `string (date-time)` | YYYY-MM-DD |
| `itemExcluido` | `boolean` |  |
| `numeroControlePncpAta` | `string` |  |
| `codigoPdm` | `integer (int32)` |  |
| `nomePdm` | `string` |  |

**Example:**

```json
{
  "numeroAtaRegistroPreco": "example",
  "codigoUnidadeGerenciadora": "example",
  "numeroCompra": "example",
  "anoCompra": "example",
  "codigoModalidadeCompra": "example",
  "dataAssinatura": "2025-01-15",
  "dataVigenciaInicial": "2025-01-15",
  "dataVigenciaFinal": "2025-01-15",
  "numeroItem": "example",
  "codigoItem": 1,
  "descricaoItem": "example",
  "tipoItem": "example",
  "quantidadeHomologadaItem": 0.0,
  "classificacaoFornecedor": "example",
  "niFornecedor": "example",
  "nomeRazaoSocialFornecedor": "example",
  "quantidadeHomologadaVencedor": 0.0,
  "valorUnitario": 0.0,
  "valorTotal": 0.0,
  "maximoAdesao": 0.0,
  "nomeUnidadeGerenciadora": "example",
  "nomeModalidadeCompra": "example",
  "idCompra": "example",
  "numeroControlePncpCompra": "example",
  "dataHoraInclusao": "2025-01-15",
  "dataHoraAtualizacao": "2025-01-15",
  "quantidadeEmpenhada": 0.0,
  "percentualMaiorDesconto": 0.0,
  "situacaoSicaf": "example",
  "dataHoraExclusao": "2025-01-15",
  "itemExcluido": true,
  "numeroControlePncpAta": "example",
  "codigoPdm": 1,
  "nomePdm": "example"
}
```

### 6.6 ARP Units per Item

**Units (unidades requisitantes) linked to an ARP item.**

| Field | Type | Description |
|---|---|---|
| `numeroAta` | `string` |  |
| `unidadeGerenciadora` | `string` |  |
| `numeroItem` | `string` |  |
| `codigoPdm` | `string` |  |
| `descricaoItem` | `string` |  |
| `fornecedor` | `string` |  |
| `quantidadeRegistrada` | `number` |  |
| `saldoAdesoes` | `number` |  |
| `saldoRemanejamentoEmpenho` | `number` |  |
| `qtdLimiteAdesao` | `number` |  |
| `qtdLimiteInformadoCompra` | `number` |  |
| `aceitaAdesao` | `boolean` |  |
| `dataHoraInclusao` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraExclusao` | `string (date-time)` | YYYY-MM-DD |
| `codigoUnidade` | `string` |  |
| `nomeUnidade` | `string` |  |
| `tipoUnidade` | `string` |  |

**Example:**

```json
{
  "numeroAta": "example",
  "unidadeGerenciadora": "example",
  "numeroItem": "example",
  "codigoPdm": "example",
  "descricaoItem": "example",
  "fornecedor": "example",
  "quantidadeRegistrada": 0.0,
  "saldoAdesoes": 0.0,
  "saldoRemanejamentoEmpenho": 0.0,
  "qtdLimiteAdesao": 0.0,
  "qtdLimiteInformadoCompra": 0.0,
  "aceitaAdesao": true,
  "dataHoraInclusao": "2025-01-15",
  "dataHoraAtualizacao": "2025-01-15",
  "dataHoraExclusao": "2025-01-15",
  "codigoUnidade": "example",
  "nomeUnidade": "example",
  "tipoUnidade": "example"
}
```

### 6.7 ARP Commitments

**Budget commitments and balances for an ARP item.**

| Field | Type | Description |
|---|---|---|
| `numeroItem` | `string` |  |
| `unidade` | `string` |  |
| `tipo` | `string` |  |
| `quantidadeRegistrada` | `number` |  |
| `quantidadeEmpenhada` | `number` |  |
| `saldoEmpenho` | `number` |  |
| `dataHoraInclusao` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "numeroItem": "example",
  "unidade": "example",
  "tipo": "example",
  "quantidadeRegistrada": 0.0,
  "quantidadeEmpenhada": 0.0,
  "saldoEmpenho": 0.0,
  "dataHoraInclusao": "2025-01-15",
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.8 ARP Adhesions

**Adhesion records (adesões) to an ARP item.**

| Field | Type | Description |
|---|---|---|
| `numeroAta` | `string` |  |
| `unidadeGerenciadora` | `string` |  |
| `unidadeNaoParticipante` | `string` |  |
| `dataAprovacaoAnalise` | `string (date-time)` | YYYY-MM-DD |
| `quantidadeAprovadaAdesao` | `integer (int32)` |  |

**Example:**

```json
{
  "numeroAta": "example",
  "unidadeGerenciadora": "example",
  "unidadeNaoParticipante": "example",
  "dataAprovacaoAnalise": "2025-01-15",
  "quantidadeAprovadaAdesao": 1
}
```

### 6.9 PNCP Purchase

**PNCP procurement record (Lei 14.133).**

| Field | Type | Description |
|---|---|---|
| `idCompra` | `string` |  |
| `numeroControlePNCP` | `string` |  |
| `anoCompraPncp` | `integer (int32)` |  |
| `sequencialCompraPncp` | `integer (int32)` |  |
| `orgaoEntidadeCnpj` | `string` |  |
| `orgaoSubrogadoCnpj` | `string` |  |
| `codigoOrgao` | `integer (int32)` |  |
| `orgaoEntidadeRazaoSocial` | `string` |  |
| `orgaoSubrogadoRazaoSocial` | `string` |  |
| `orgaoEntidadeEsferaId` | `string` |  |
| `orgaoSubrogadoEsferaId` | `string` |  |
| `orgaoEntidadePoderId` | `string` |  |
| `orgaoSubrogadoPoderId` | `string` |  |
| `unidadeOrgaoCodigoUnidade` | `string` |  |
| `unidadeSubrogadaCodigoUnidade` | `string` |  |
| `unidadeOrgaoNomeUnidade` | `string` |  |
| `unidadeSubrogadaNomeUnidade` | `string` |  |
| `unidadeOrgaoUfSigla` | `string` |  |
| `unidadeSubrogadaUfSigla` | `string` |  |
| `unidadeOrgaoMunicipioNome` | `string` |  |
| `unidade_subrogada_municipio_nome` | `string` |  |
| `unidadeOrgaoCodigoIbge` | `integer` |  |
| `unidadeSubrogadaCodigoIbge` | `integer` |  |
| `numeroCompra` | `string` |  |
| `modalidadeIdPncp` | `integer (int32)` |  |
| `codigoModalidade` | `integer (int32)` |  |
| `modalidadeNome` | `string` |  |
| `srp` | `boolean` |  |
| `modoDisputaIdPncp` | `integer (int32)` |  |
| `codigoModoDisputa` | `integer (int32)` |  |
| `amparoLegalCodigoPncp` | `integer (int32)` |  |
| `amparoLegalNome` | `string` |  |
| `amparoLegalDescricao` | `string` |  |
| `informacaoComplementar` | `string` |  |
| `processo` | `string` |  |
| `objetoCompra` | `string` |  |
| `existeResultado` | `boolean` |  |
| `orcamentoSigilosoCodigo` | `integer (int32)` |  |
| `orcamentoSigilosoDescricao` | `string` |  |
| `situacaoCompraIdPncp` | `integer (int32)` |  |
| `situacaoCompraNomePncp` | `string` |  |
| `tipoInstrumentoConvocatorioCodigoPncp` | `integer (int32)` |  |
| `tipoInstrumentoConvocatorioNome` | `string` |  |
| `modoDisputaNomePncp` | `string` |  |
| `valorTotalEstimado` | `number` |  |
| `valorTotalHomologado` | `number` |  |
| `dataInclusaoPncp` | `string (date-time)` | YYYY-MM-DD |
| `dataAtualizacaoPncp` | `string (date-time)` | YYYY-MM-DD |
| `dataPublicacaoPncp` | `string (date-time)` | YYYY-MM-DD |
| `dataAberturaPropostaPncp` | `string (date-time)` | YYYY-MM-DD |
| `dataEncerramentoPropostaPncp` | `string (date-time)` | YYYY-MM-DD |
| `contratacaoExcluida` | `boolean` |  |

**Example:**

```json
{
  "idCompra": "example",
  "numeroControlePNCP": "example",
  "anoCompraPncp": 1,
  "sequencialCompraPncp": 1,
  "orgaoEntidadeCnpj": "example",
  "orgaoSubrogadoCnpj": "example",
  "codigoOrgao": 1,
  "orgaoEntidadeRazaoSocial": "example",
  "orgaoSubrogadoRazaoSocial": "example",
  "orgaoEntidadeEsferaId": "example",
  "orgaoSubrogadoEsferaId": "example",
  "orgaoEntidadePoderId": "example",
  "orgaoSubrogadoPoderId": "example",
  "unidadeOrgaoCodigoUnidade": "example",
  "unidadeSubrogadaCodigoUnidade": "example",
  "unidadeOrgaoNomeUnidade": "example",
  "unidadeSubrogadaNomeUnidade": "example",
  "unidadeOrgaoUfSigla": "example",
  "unidadeSubrogadaUfSigla": "example",
  "unidadeOrgaoMunicipioNome": "example",
  "unidade_subrogada_municipio_nome": "example",
  "unidadeOrgaoCodigoIbge": 1,
  "unidadeSubrogadaCodigoIbge": 1,
  "numeroCompra": "example",
  "modalidadeIdPncp": 1,
  "codigoModalidade": 1,
  "modalidadeNome": "example",
  "srp": true,
  "modoDisputaIdPncp": 1,
  "codigoModoDisputa": 1,
  "amparoLegalCodigoPncp": 1,
  "amparoLegalNome": "example",
  "amparoLegalDescricao": "example",
  "informacaoComplementar": "example",
  "processo": "example",
  "objetoCompra": "example",
  "existeResultado": true,
  "orcamentoSigilosoCodigo": 1,
  "orcamentoSigilosoDescricao": "example",
  "situacaoCompraIdPncp": 1,
  "situacaoCompraNomePncp": "example",
  "tipoInstrumentoConvocatorioCodigoPncp": 1,
  "tipoInstrumentoConvocatorioNome": "example",
  "modoDisputaNomePncp": "example",
  "valorTotalEstimado": 0.0,
  "valorTotalHomologado": 0.0,
  "dataInclusaoPncp": "2025-01-15",
  "dataAtualizacaoPncp": "2025-01-15",
  "dataPublicacaoPncp": "2025-01-15",
  "dataAberturaPropostaPncp": "2025-01-15",
  "dataEncerramentoPropostaPncp": "2025-01-15",
  "contratacaoExcluida": true
}
```

### 6.10 PNCP Purchase Items

**Item within a PNCP procurement.**

| Field | Type | Description |
|---|---|---|
| `idCompra` | `string` |  |
| `idCompraItem` | `string` |  |
| `idContratacaoPNCP` | `string` |  |
| `unidadeOrgaoCodigoUnidade` | `string` |  |
| `orgaoEntidadeCnpj` | `string` |  |
| `numeroItemPncp` | `integer (int32)` |  |
| `numeroItemCompra` | `integer (int32)` |  |
| `numeroGrupo` | `integer (int32)` |  |
| `descricaoResumida` | `string` |  |
| `materialOuServico` | `string` |  |
| `materialOuServicoNome` | `string` |  |
| `codigoClasse` | `integer (int32)` |  |
| `codigoGrupo` | `integer (int32)` |  |
| `codItemCatalogo` | `integer (int32)` |  |
| `descricaodetalhada` | `string` |  |
| `unidadeMedida` | `string` |  |
| `orcamentoSigiloso` | `boolean` |  |
| `itemCategoriaIdPncp` | `integer (int32)` |  |
| `itemCategoriaNome` | `string` |  |
| `criterioJulgamentoIdPncp` | `integer (int32)` |  |
| `criterioJulgamentoNome` | `string` |  |
| `situacaoCompraItem` | `string` |  |
| `situacaoCompraItemNome` | `string` |  |
| `tipoBeneficio` | `string` |  |
| `tipoBeneficioNome` | `string` |  |
| `incentivoProdutivoBasico` | `boolean` |  |
| `quantidade` | `number` |  |
| `valorUnitarioEstimado` | `number` |  |
| `valorTotal` | `number` |  |
| `temResultado` | `boolean` |  |
| `codFornecedor` | `string` |  |
| `nomeFornecedor` | `string` |  |
| `quantidadeResultado` | `number` |  |
| `valorUnitarioResultado` | `number` |  |
| `valorTotalResultado` | `number` |  |
| `dataInclusaoPncp` | `string (date-time)` | YYYY-MM-DD |
| `dataAtualizacaoPncp` | `string (date-time)` | YYYY-MM-DD |
| `dataResultado` | `string` |  |
| `margemPreferenciaNormal` | `boolean` |  |
| `percentualMargemPreferenciaNormal` | `number` |  |
| `margemPreferenciaAdicional` | `boolean` |  |
| `percentualMargemPreferenciaAdicional` | `number` |  |
| `codigoNCM` | `string` |  |
| `descricaoNCM` | `string` |  |
| `numeroControlePNCPCompra` | `string` |  |

**Example:**

```json
{
  "idCompra": "example",
  "idCompraItem": "example",
  "idContratacaoPNCP": "example",
  "unidadeOrgaoCodigoUnidade": "example",
  "orgaoEntidadeCnpj": "example",
  "numeroItemPncp": 1,
  "numeroItemCompra": 1,
  "numeroGrupo": 1,
  "descricaoResumida": "example",
  "materialOuServico": "example",
  "materialOuServicoNome": "example",
  "codigoClasse": 1,
  "codigoGrupo": 1,
  "codItemCatalogo": 1,
  "descricaodetalhada": "example",
  "unidadeMedida": "example",
  "orcamentoSigiloso": true,
  "itemCategoriaIdPncp": 1,
  "itemCategoriaNome": "example",
  "criterioJulgamentoIdPncp": 1,
  "criterioJulgamentoNome": "example",
  "situacaoCompraItem": "example",
  "situacaoCompraItemNome": "example",
  "tipoBeneficio": "example",
  "tipoBeneficioNome": "example",
  "incentivoProdutivoBasico": true,
  "quantidade": 0.0,
  "valorUnitarioEstimado": 0.0,
  "valorTotal": 0.0,
  "temResultado": true,
  "codFornecedor": "example",
  "nomeFornecedor": "example",
  "quantidadeResultado": 0.0,
  "valorUnitarioResultado": 0.0,
  "valorTotalResultado": 0.0,
  "dataInclusaoPncp": "2025-01-15",
  "dataAtualizacaoPncp": "2025-01-15",
  "dataResultado": "example",
  "margemPreferenciaNormal": true,
  "percentualMargemPreferenciaNormal": 0.0,
  "margemPreferenciaAdicional": true,
  "percentualMargemPreferenciaAdicional": 0.0,
  "codigoNCM": "example",
  "descricaoNCM": "example",
  "numeroControlePNCPCompra": "example"
}
```

### 6.11 PNCP Item Result

**Awarded result for a PNCP item.**

| Field | Type | Description |
|---|---|---|
| `idCompraItem` | `string` |  |
| `idCompra` | `string` |  |
| `idContratacaoPNCP` | `string` |  |
| `unidadeOrgaoCodigoUnidade` | `string` |  |
| `unidadeOrgaoUfSigla` | `string` |  |
| `numeroItemPncp` | `integer (int32)` |  |
| `sequencialResultado` | `integer (int32)` |  |
| `niFornecedor` | `string` |  |
| `tipoPessoa` | `string` |  |
| `nomeRazaoSocialFornecedor` | `string` |  |
| `codigoPais` | `string` |  |
| `indicadorSubcontratacao` | `boolean` |  |
| `ordemClassificacaoSrp` | `integer (int32)` |  |
| `quantidadeHomologada` | `number` |  |
| `valorUnitarioHomologado` | `number` |  |
| `valorTotalHomologado` | `number` |  |
| `percentualDesconto` | `number` |  |
| `situacaoCompraItemResultadoId` | `integer` |  |
| `situacaoCompraItemResultadoNome` | `string` |  |
| `motivoCancelamento` | `string` |  |
| `porteFornecedorId` | `integer (int32)` |  |
| `porteFornecedorNome` | `string` |  |
| `naturezaJuridicaNome` | `string` |  |
| `naturezaJuridicaId` | `string` |  |
| `dataInclusaoPncp` | `string (date-time)` | YYYY-MM-DD |
| `dataAtualizacaoPncp` | `string (date-time)` | YYYY-MM-DD |
| `dataCancelamentoPncp` | `string (date-time)` | YYYY-MM-DD |
| `dataResultadoPncp` | `string (date-time)` | YYYY-MM-DD |
| `numeroControlePNCPCompra` | `string` |  |
| `orgaoEntidadeCnpj` | `string` |  |
| `aplicacaoMargemPreferencia` | `boolean` |  |
| `amparoLegalMargemPreferenciaId` | `integer (int32)` |  |
| `amparoLegalMargemPreferenciaNome` | `string` |  |
| `aplicacaoBeneficioMeepp` | `boolean` |  |
| `aplicacaoCriterioDesempate` | `boolean` |  |
| `amparoLegalCriterioDesempateId` | `integer (int32)` |  |
| `amparoLegalCriterioDesempateNome` | `string` |  |
| `moedaEstrangeiraId` | `integer (int32)` |  |
| `dataCotacaoMoedaEstrangeira` | `string (date-time)` | YYYY-MM-DD |
| `valorNominalMoedaEstrangeira` | `number` |  |
| `paisOrigemProdutoServicoId` | `string` |  |
| `timezoneCotacaoMoedaEstrangeira` | `string` |  |

**Example:**

```json
{
  "idCompraItem": "example",
  "idCompra": "example",
  "idContratacaoPNCP": "example",
  "unidadeOrgaoCodigoUnidade": "example",
  "unidadeOrgaoUfSigla": "example",
  "numeroItemPncp": 1,
  "sequencialResultado": 1,
  "niFornecedor": "example",
  "tipoPessoa": "example",
  "nomeRazaoSocialFornecedor": "example",
  "codigoPais": "example",
  "indicadorSubcontratacao": true,
  "ordemClassificacaoSrp": 1,
  "quantidadeHomologada": 0.0,
  "valorUnitarioHomologado": 0.0,
  "valorTotalHomologado": 0.0,
  "percentualDesconto": 0.0,
  "situacaoCompraItemResultadoId": 1,
  "situacaoCompraItemResultadoNome": "example",
  "motivoCancelamento": "example",
  "porteFornecedorId": 1,
  "porteFornecedorNome": "example",
  "naturezaJuridicaNome": "example",
  "naturezaJuridicaId": "example",
  "dataInclusaoPncp": "2025-01-15",
  "dataAtualizacaoPncp": "2025-01-15",
  "dataCancelamentoPncp": "2025-01-15",
  "dataResultadoPncp": "2025-01-15",
  "numeroControlePNCPCompra": "example",
  "orgaoEntidadeCnpj": "example",
  "aplicacaoMargemPreferencia": true,
  "amparoLegalMargemPreferenciaId": 1,
  "amparoLegalMargemPreferenciaNome": "example",
  "aplicacaoBeneficioMeepp": true,
  "aplicacaoCriterioDesempate": true,
  "amparoLegalCriterioDesempateId": 1,
  "amparoLegalCriterioDesempateNome": "example",
  "moedaEstrangeiraId": 1,
  "dataCotacaoMoedaEstrangeira": "2025-01-15",
  "valorNominalMoedaEstrangeira": 0.0,
  "paisOrigemProdutoServicoId": "example",
  "timezoneCotacaoMoedaEstrangeira": "example"
}
```

### 6.12 Material Price Research

**Historical material purchase price.**

| Field | Type | Description |
|---|---|---|
| `idCompra` | `string` |  |
| `idItemCompra` | `integer` |  |
| `forma` | `string` |  |
| `modalidade` | `integer (int32)` |  |
| `criterioJulgamento` | `string` |  |
| `numeroItemCompra` | `integer (int32)` |  |
| `descricaoItem` | `string` |  |
| `codigoItemCatalogo` | `integer (int32)` |  |
| `nomeUnidadeMedida` | `integer (int32)` |  |
| `siglaUnidadeMedida` | `string` |  |
| `nomeUnidadeFornecimento` | `string` |  |
| `siglaUnidadeFornecimento` | `string` |  |
| `capacidadeUnidadeFornecimento` | `number` |  |
| `quantidade` | `number` |  |
| `precoUnitario` | `number` |  |
| `percentualMaiorDesconto` | `number` |  |
| `niFornecedor` | `string` |  |
| `nomeFornecedor` | `string` |  |
| `marca` | `string` |  |
| `codigoUasg` | `string` |  |
| `nomeUasg` | `string` |  |
| `codigoMunicipio` | `integer (int32)` |  |
| `municipio` | `string` |  |
| `estado` | `string` |  |
| `codigoOrgao` | `integer (int32)` |  |
| `nomeOrgao` | `string` |  |
| `poder` | `string` |  |
| `esfera` | `string` |  |
| `dataCompra` | `string (date)` | YYYY-MM-DD |
| `dataHoraAtualizacaoCompra` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraAtualizacaoItem` | `string (date-time)` | YYYY-MM-DD |
| `dataResultado` | `string (date)` | YYYY-MM-DD |
| `dataHoraAtualizacaoUasg` | `string (date-time)` | YYYY-MM-DD |
| `codigoClasse` | `integer (int32)` |  |
| `nomeClasse` | `string` |  |
| `objetoCompra` | `string` |  |
| `descricaoDetalhadaItem` | `string` |  |

**Example:**

```json
{
  "idCompra": "example",
  "idItemCompra": 1,
  "forma": "example",
  "modalidade": 1,
  "criterioJulgamento": "example",
  "numeroItemCompra": 1,
  "descricaoItem": "example",
  "codigoItemCatalogo": 1,
  "nomeUnidadeMedida": 1,
  "siglaUnidadeMedida": "example",
  "nomeUnidadeFornecimento": "example",
  "siglaUnidadeFornecimento": "example",
  "capacidadeUnidadeFornecimento": 0.0,
  "quantidade": 0.0,
  "precoUnitario": 0.0,
  "percentualMaiorDesconto": 0.0,
  "niFornecedor": "example",
  "nomeFornecedor": "example",
  "marca": "example",
  "codigoUasg": "example",
  "nomeUasg": "example",
  "codigoMunicipio": 1,
  "municipio": "example",
  "estado": "example",
  "codigoOrgao": 1,
  "nomeOrgao": "example",
  "poder": "example",
  "esfera": "example",
  "dataCompra": "2025-01-15",
  "dataHoraAtualizacaoCompra": "2025-01-15",
  "dataHoraAtualizacaoItem": "2025-01-15",
  "dataResultado": "2025-01-15",
  "dataHoraAtualizacaoUasg": "2025-01-15",
  "codigoClasse": 1,
  "nomeClasse": "example",
  "objetoCompra": "example",
  "descricaoDetalhadaItem": "example"
}
```

### 6.13 Material Price Detail

**Detailed description for a material price record.**

| Field | Type | Description |
|---|---|---|
| `idCompra` | `string` |  |
| `idItemCompra` | `integer` |  |
| `numeroItemCompra` | `integer (int32)` |  |
| `codigoItemCatalogo` | `integer (int32)` |  |
| `objetoCompra` | `string` |  |
| `descricaoDetalhadaItem` | `string` |  |

**Example:**

```json
{
  "idCompra": "example",
  "idItemCompra": 1,
  "numeroItemCompra": 1,
  "codigoItemCatalogo": 1,
  "objetoCompra": "example",
  "descricaoDetalhadaItem": "example"
}
```

### 6.14 Service Price Research

**Historical service purchase price.**

| Field | Type | Description |
|---|---|---|
| `idCompra` | `string` |  |
| `idItemCompra` | `integer` |  |
| `forma` | `string` |  |
| `modalidade` | `integer (int32)` |  |
| `criterioJulgamento` | `string` |  |
| `numeroItemCompra` | `integer (int32)` |  |
| `descricaoItem` | `string` |  |
| `codigoItemCatalogo` | `integer (int32)` |  |
| `nomeUnidadeMedida` | `string` |  |
| `siglaUnidadeMedida` | `string` |  |
| `quantidade` | `number` |  |
| `precoUnitario` | `number` |  |
| `percentualMaiorDesconto` | `number` |  |
| `niFornecedor` | `string` |  |
| `nomeFornecedor` | `string` |  |
| `codigoUasg` | `string` |  |
| `nomeUasg` | `string` |  |
| `codigoMunicipio` | `integer (int32)` |  |
| `municipio` | `string` |  |
| `estado` | `string` |  |
| `codigoOrgao` | `integer (int32)` |  |
| `nomeOrgao` | `string` |  |
| `poder` | `string` |  |
| `esfera` | `string` |  |
| `dataCompra` | `string (date)` | YYYY-MM-DD |
| `dataHoraAtualizacaoCompra` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraAtualizacaoItem` | `string (date-time)` | YYYY-MM-DD |
| `dataResultado` | `string (date)` | YYYY-MM-DD |
| `dataHoraAtualizacaoUasg` | `string (date-time)` | YYYY-MM-DD |
| `objetoCompra` | `string` |  |
| `descricaoDetalhadaItem` | `string` |  |

**Example:**

```json
{
  "idCompra": "example",
  "idItemCompra": 1,
  "forma": "example",
  "modalidade": 1,
  "criterioJulgamento": "example",
  "numeroItemCompra": 1,
  "descricaoItem": "example",
  "codigoItemCatalogo": 1,
  "nomeUnidadeMedida": "example",
  "siglaUnidadeMedida": "example",
  "quantidade": 0.0,
  "precoUnitario": 0.0,
  "percentualMaiorDesconto": 0.0,
  "niFornecedor": "example",
  "nomeFornecedor": "example",
  "codigoUasg": "example",
  "nomeUasg": "example",
  "codigoMunicipio": 1,
  "municipio": "example",
  "estado": "example",
  "codigoOrgao": 1,
  "nomeOrgao": "example",
  "poder": "example",
  "esfera": "example",
  "dataCompra": "2025-01-15",
  "dataHoraAtualizacaoCompra": "2025-01-15",
  "dataHoraAtualizacaoItem": "2025-01-15",
  "dataResultado": "2025-01-15",
  "dataHoraAtualizacaoUasg": "2025-01-15",
  "objetoCompra": "example",
  "descricaoDetalhadaItem": "example"
}
```

### 6.15 PGC Detail

**PGC (purchase program) item detail.**

| Field | Type | Description |
|---|---|---|
| `codigoUasg` | `string` |  |
| `nomeUasg` | `string` |  |
| `orgao` | `string` |  |
| `numeroArtefato` | `integer (int32)` |  |
| `anoArtefato` | `integer (int32)` |  |
| `codigoEstadoArtefato` | `integer (int32)` |  |
| `codigoCategoriaArtefato` | `integer (int32)` |  |
| `descricaoArtefato` | `string` |  |
| `codigoTipoArtefato` | `number` |  |
| `ordemDfd` | `integer (int32)` |  |
| `descricaoObjetoDfd` | `string` |  |
| `nivelPrioridadeDfd` | `integer (int32)` |  |
| `dataPrevistaFormalizacaoDemanda` | `string (date-time)` | YYYY-MM-DD |
| `codigoAreaDfd` | `string` |  |
| `tipoItem` | `string` |  |
| `itemSustentavel` | `boolean` |  |
| `codigoGrupoMaterial` | `integer (int32)` |  |
| `nomeGrupoMaterial` | `string` |  |
| `codigoClasseMaterial` | `integer (int32)` |  |
| `nomeClasseMaterial` | `string` |  |
| `codigoPdmMaterial` | `integer (int32)` |  |
| `nomePdmMaterial` | `string` |  |
| `codigoSecaoServico` | `integer (int32)` |  |
| `nomeSecaoServico` | `string` |  |
| `codigoDivisaoServico` | `integer (int32)` |  |
| `nomeDivisaoServico` | `string` |  |
| `codigoGrupoServico` | `integer (int32)` |  |
| `nomeGrupoServico` | `string` |  |
| `codigoClasseServico` | `integer (int32)` |  |
| `nomeClasseServico` | `string` |  |
| `codigoSubclasseServico` | `integer (int32)` |  |
| `nomeSubclasseServico` | `string` |  |
| `codigoItemCatalogo` | `string` |  |
| `descricaoItemCatalogo` | `string` |  |
| `siglaUnidadeFornecimento` | `string` |  |
| `nomeUnidadeFornecimento` | `string` |  |
| `quantidadeItem` | `number` |  |
| `valorUnitarioItem` | `number` |  |
| `valorTotalItem` | `number` |  |
| `tituloProjetoCompra` | `string` |  |
| `descricaoProjetoCompra` | `string` |  |
| `anoPcaProjetoCompra` | `integer (int32)` |  |
| `dataInicioProcessoCompra` | `string (date-time)` | YYYY-MM-DD |
| `dataFimProcessoCompra` | `string (date-time)` | YYYY-MM-DD |
| `duracaoProcessoCompra` | `integer (int32)` |  |
| `numeroItemPncp` | `integer (int32)` |  |
| `statusContratacaoExecucao` | `integer (int32)` |  |
| `dataHoraPublicacaoPncp` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraAtualizacaoArtefato` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraAtualizacaoProjetoCompra` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraAtualizacaoDfd` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraAtualizacaoItem` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoUasg": "example",
  "nomeUasg": "example",
  "orgao": "example",
  "numeroArtefato": 1,
  "anoArtefato": 1,
  "codigoEstadoArtefato": 1,
  "codigoCategoriaArtefato": 1,
  "descricaoArtefato": "example",
  "codigoTipoArtefato": 0.0,
  "ordemDfd": 1,
  "descricaoObjetoDfd": "example",
  "nivelPrioridadeDfd": 1,
  "dataPrevistaFormalizacaoDemanda": "2025-01-15",
  "codigoAreaDfd": "example",
  "tipoItem": "example",
  "itemSustentavel": true,
  "codigoGrupoMaterial": 1,
  "nomeGrupoMaterial": "example",
  "codigoClasseMaterial": 1,
  "nomeClasseMaterial": "example",
  "codigoPdmMaterial": 1,
  "nomePdmMaterial": "example",
  "codigoSecaoServico": 1,
  "nomeSecaoServico": "example",
  "codigoDivisaoServico": 1,
  "nomeDivisaoServico": "example",
  "codigoGrupoServico": 1,
  "nomeGrupoServico": "example",
  "codigoClasseServico": 1,
  "nomeClasseServico": "example",
  "codigoSubclasseServico": 1,
  "nomeSubclasseServico": "example",
  "codigoItemCatalogo": "example",
  "descricaoItemCatalogo": "example",
  "siglaUnidadeFornecimento": "example",
  "nomeUnidadeFornecimento": "example",
  "quantidadeItem": 0.0,
  "valorUnitarioItem": 0.0,
  "valorTotalItem": 0.0,
  "tituloProjetoCompra": "example",
  "descricaoProjetoCompra": "example",
  "anoPcaProjetoCompra": 1,
  "dataInicioProcessoCompra": "2025-01-15",
  "dataFimProcessoCompra": "2025-01-15",
  "duracaoProcessoCompra": 1,
  "numeroItemPncp": 1,
  "statusContratacaoExecucao": 1,
  "dataHoraPublicacaoPncp": "2025-01-15",
  "dataHoraAtualizacaoArtefato": "2025-01-15",
  "dataHoraAtualizacaoProjetoCompra": "2025-01-15",
  "dataHoraAtualizacaoDfd": "2025-01-15",
  "dataHoraAtualizacaoItem": "2025-01-15"
}
```

### 6.16 PGC Aggregation

**PGC aggregated summary by agency and year.**

| Field | Type | Description |
|---|---|---|
| `orgao` | `string` |  |
| `ano` | `integer (int32)` |  |
| `poder` | `string` |  |
| `esfera` | `string` |  |
| `dataHoraPublicacaoPncp` | `string (date-time)` | YYYY-MM-DD |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |
| `quantidadeTotalItens` | `number` |  |
| `valorTotalEstimado` | `number` |  |

**Example:**

```json
{
  "orgao": "example",
  "ano": 1,
  "poder": "example",
  "esfera": "example",
  "dataHoraPublicacaoPncp": "2025-01-15",
  "dataHoraAtualizacao": "2025-01-15",
  "quantidadeTotalItens": 0.0,
  "valorTotalEstimado": 0.0
}
```

### 6.17 UASG

**Administrative unit (UASG) record.**

| Field | Type | Description |
|---|---|---|
| `codigoUasg` | `string` |  |
| `nomeUasg` | `string` |  |
| `usoSisg` | `boolean` |  |
| `adesaoSiasg` | `boolean` |  |
| `siglaUf` | `string` |  |
| `codigoMunicipio` | `integer (int32)` |  |
| `codigoMunicipioIbge` | `integer (int32)` |  |
| `nomeMunicipioIbge` | `string` |  |
| `codigoUnidadePolo` | `integer (int32)` |  |
| `nomeUnidadePolo` | `string` |  |
| `codigoUnidadeEspelho` | `integer (int32)` |  |
| `nomeUnidadeEspelho` | `string` |  |
| `uasgCadastradora` | `boolean` |  |
| `cnpjCpfUasg` | `string` |  |
| `codigoOrgao` | `integer (int32)` |  |
| `cnpjCpfOrgao` | `string` |  |
| `cnpjCpfOrgaoVinculado` | `string` |  |
| `cnpjCpfOrgaoSuperior` | `string` |  |
| `codigoSiorg` | `string` |  |
| `statusUasg` | `boolean` |  |
| `dataImplantacaoSidec` | `string (date-time)` |  |
| `dataHoraMovimento` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoUasg": "example",
  "nomeUasg": "example",
  "usoSisg": true,
  "adesaoSiasg": true,
  "siglaUf": "example",
  "codigoMunicipio": 1,
  "codigoMunicipioIbge": 1,
  "nomeMunicipioIbge": "example",
  "codigoUnidadePolo": 1,
  "nomeUnidadePolo": "example",
  "codigoUnidadeEspelho": 1,
  "nomeUnidadeEspelho": "example",
  "uasgCadastradora": true,
  "cnpjCpfUasg": "example",
  "codigoOrgao": 1,
  "cnpjCpfOrgao": "example",
  "cnpjCpfOrgaoVinculado": "example",
  "cnpjCpfOrgaoSuperior": "example",
  "codigoSiorg": "example",
  "statusUasg": true,
  "dataImplantacaoSidec": "2025-01-15",
  "dataHoraMovimento": "2025-01-15"
}
```

### 6.18 Government Body

**Government body (órgão) record.**

| Field | Type | Description |
|---|---|---|
| `codigoOrgao` | `integer (int32)` |  |
| `nomeOrgao` | `string` |  |
| `nomeMnemonicoOrgao` | `string` |  |
| `cnpjCpfOrgao` | `string` |  |
| `codigoOrgaoVinculado` | `integer (int32)` |  |
| `cnpjCpfOrgaoVinculado` | `string` |  |
| `nomeOrgaoVinculado` | `string` |  |
| `codigoOrgaoSuperior` | `integer (int32)` |  |
| `cnpjCpfOrgaoSuperior` | `string` |  |
| `nomeOrgaoSuperior` | `string` |  |
| `codigoTipoAdministracao` | `integer (int32)` |  |
| `nomeTipoAdministracao` | `string` |  |
| `poder` | `string` |  |
| `esfera` | `string` |  |
| `usoSisg` | `boolean` |  |
| `statusOrgao` | `boolean` |  |
| `dataHoraMovimento` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoOrgao": 1,
  "nomeOrgao": "example",
  "nomeMnemonicoOrgao": "example",
  "cnpjCpfOrgao": "example",
  "codigoOrgaoVinculado": 1,
  "cnpjCpfOrgaoVinculado": "example",
  "nomeOrgaoVinculado": "example",
  "codigoOrgaoSuperior": 1,
  "cnpjCpfOrgaoSuperior": "example",
  "nomeOrgaoSuperior": "example",
  "codigoTipoAdministracao": 1,
  "nomeTipoAdministracao": "example",
  "poder": "example",
  "esfera": "example",
  "usoSisg": true,
  "statusOrgao": true,
  "dataHoraMovimento": "2025-01-15"
}
```

### 6.19 Material Group

**Material catalog group.**

| Field | Type | Description |
|---|---|---|
| `codigoGrupo` | `integer (int64)` |  |
| `nomeGrupo` | `string` |  |
| `statusGrupo` | `boolean` |  |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoGrupo": 1,
  "nomeGrupo": "example",
  "statusGrupo": true,
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.20 Material Class

**Material catalog class.**

| Field | Type | Description |
|---|---|---|
| `codigoClasse` | `integer (int64)` |  |
| `codigoGrupo` | `integer (int64)` |  |
| `nomeGrupo` | `string` |  |
| `nomeClasse` | `string` |  |
| `statusClasse` | `boolean` |  |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoClasse": 1,
  "codigoGrupo": 1,
  "nomeGrupo": "example",
  "nomeClasse": "example",
  "statusClasse": true,
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.21 Material Item

**Material catalog item (CATMAT).**

| Field | Type | Description |
|---|---|---|
| `codigoItem` | `integer (int64)` |  |
| `codigoGrupo` | `integer (int64)` |  |
| `nomeGrupo` | `string` |  |
| `codigoClasse` | `integer (int64)` |  |
| `nomeClasse` | `string` |  |
| `codigoPdm` | `integer (int64)` |  |
| `nomePdm` | `string` |  |
| `descricaoItem` | `string` |  |
| `statusItem` | `boolean` |  |
| `itemSustentavel` | `boolean` |  |
| `codigo_ncm` | `string` |  |
| `descricao_ncm` | `string` |  |
| `aplica_margem_preferencia` | `boolean` |  |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoItem": 1,
  "codigoGrupo": 1,
  "nomeGrupo": "example",
  "codigoClasse": 1,
  "nomeClasse": "example",
  "codigoPdm": 1,
  "nomePdm": "example",
  "descricaoItem": "example",
  "statusItem": true,
  "itemSustentavel": true,
  "codigo_ncm": "example",
  "descricao_ncm": "example",
  "aplica_margem_preferencia": true,
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.22 Material PDM

**Material PDM (product descriptor) entry.**

| Field | Type | Description |
|---|---|---|
| `codigoGrupo` | `integer (int64)` |  |
| `nomeGrupo` | `string` |  |
| `codigoClasse` | `integer (int64)` |  |
| `nomeClasse` | `string` |  |
| `codigoPdm` | `integer (int64)` |  |
| `nomePdm` | `string` |  |
| `statusPdm` | `boolean` |  |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoGrupo": 1,
  "nomeGrupo": "example",
  "codigoClasse": 1,
  "nomeClasse": "example",
  "codigoPdm": 1,
  "nomePdm": "example",
  "statusPdm": true,
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.23 Material Characteristics

**Characteristics of a material item.**

| Field | Type | Description |
|---|---|---|
| `codigoItem` | `integer (int64)` |  |
| `itemSustentavel` | `boolean` |  |
| `statusItem` | `boolean` |  |
| `codigoCaracteristica` | `string` |  |
| `nomeCaracteristica` | `string` |  |
| `statusCaracteristica` | `boolean` |  |
| `codigoValorCaracteristica` | `string` |  |
| `nomeValorCaracteristica` | `string` |  |
| `statusValorCaracteristica` | `boolean` |  |
| `numeroCaracteristica` | `integer (int32)` |  |
| `siglaUnidadeMedida` | `string` |  |
| `dataHoraAtualizacao` | `string (date-time)` |  |

**Example:**

```json
{
  "codigoItem": 1,
  "itemSustentavel": true,
  "statusItem": true,
  "codigoCaracteristica": "example",
  "nomeCaracteristica": "example",
  "statusCaracteristica": true,
  "codigoValorCaracteristica": "example",
  "nomeValorCaracteristica": "example",
  "statusValorCaracteristica": true,
  "numeroCaracteristica": 1,
  "siglaUnidadeMedida": "example",
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.24 Material Unit of Supply

**Unit of supply for a PDM entry.**

| Field | Type | Description |
|---|---|---|
| `codigoPdm` | `integer (int64)` |  |
| `siglaUnidadeFornecimento` | `string` |  |
| `nomeUnidadeFornecimento` | `string` |  |
| `descricaoUnidadeFornecimento` | `string` |  |
| `siglaUnidadeMedida` | `string` |  |
| `capacidadeUnidadeFornecimento` | `number` |  |
| `numeroSequencialUnidadeFornecimento` | `integer (int32)` |  |
| `statusUnidadeFornecimentoPdm` | `boolean` |  |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoPdm": 1,
  "siglaUnidadeFornecimento": "example",
  "nomeUnidadeFornecimento": "example",
  "descricaoUnidadeFornecimento": "example",
  "siglaUnidadeMedida": "example",
  "capacidadeUnidadeFornecimento": 0.0,
  "numeroSequencialUnidadeFornecimento": 1,
  "statusUnidadeFornecimentoPdm": true,
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.25 Material Expense Nature

**Expense nature (natureza de despesa) for a material.**

| Field | Type | Description |
|---|---|---|
| `codigoPdm` | `integer (int64)` |  |
| `codigoNaturezaDespesa` | `string` |  |
| `nomeNaturezaDespesa` | `string` |  |
| `statusNaturezaDespesa` | `boolean` |  |

**Example:**

```json
{
  "codigoPdm": 1,
  "codigoNaturezaDespesa": "example",
  "nomeNaturezaDespesa": "example",
  "statusNaturezaDespesa": true
}
```

### 6.26 Service Section

**Service catalog section.**

| Field | Type | Description |
|---|---|---|
| `codigoSecao` | `integer (int64)` |  |
| `nomeSecao` | `string` |  |
| `statusSecao` | `boolean` |  |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoSecao": 1,
  "nomeSecao": "example",
  "statusSecao": true,
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.27 Service Division

**Service catalog division.**

| Field | Type | Description |
|---|---|---|
| `codigoSecao` | `integer (int64)` |  |
| `nomeSecao` | `string` |  |
| `codigoDivisao` | `integer (int64)` |  |
| `nomeDivisao` | `string` |  |
| `statusDivisao` | `boolean` |  |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoSecao": 1,
  "nomeSecao": "example",
  "codigoDivisao": 1,
  "nomeDivisao": "example",
  "statusDivisao": true,
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.28 Service Group

**Service catalog group.**

| Field | Type | Description |
|---|---|---|
| `nomeSecao` | `string` |  |
| `codigoDivisao` | `integer (int64)` |  |
| `nomeDivisao` | `string` |  |
| `codigoGrupo` | `integer (int64)` |  |
| `nomeGrupo` | `string` |  |
| `statusGrupo` | `boolean` |  |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "nomeSecao": "example",
  "codigoDivisao": 1,
  "nomeDivisao": "example",
  "codigoGrupo": 1,
  "nomeGrupo": "example",
  "statusGrupo": true,
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.29 Service Class

**Service catalog class.**

| Field | Type | Description |
|---|---|---|
| `codigoGrupo` | `integer (int64)` |  |
| `nomeGrupo` | `string` |  |
| `codigoClasse` | `integer (int64)` |  |
| `nomeClasse` | `string` |  |
| `statusGrupo` | `boolean` |  |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoGrupo": 1,
  "nomeGrupo": "example",
  "codigoClasse": 1,
  "nomeClasse": "example",
  "statusGrupo": true,
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.30 Service Subclass

**Service catalog subclass.**

| Field | Type | Description |
|---|---|---|
| `codigoClasse` | `integer (int64)` |  |
| `nomeClasse` | `string` |  |
| `codigoSubclasse` | `integer (int64)` |  |
| `nomeSubclasse` | `string` |  |
| `statusSubclasse` | `boolean` |  |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoClasse": 1,
  "nomeClasse": "example",
  "codigoSubclasse": 1,
  "nomeSubclasse": "example",
  "statusSubclasse": true,
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.31 Service Item

**Service catalog item (CATSER).**

| Field | Type | Description |
|---|---|---|
| `codigoSecao` | `integer (int64)` |  |
| `nomeSecao` | `string` |  |
| `codigoDivisao` | `integer (int64)` |  |
| `nomeDivisao` | `string` |  |
| `codigoGrupo` | `integer (int64)` |  |
| `nomeGrupo` | `string` |  |
| `codigoClasse` | `integer (int64)` |  |
| `nomeClasse` | `string` |  |
| `codigoSubclasse` | `integer (int64)` |  |
| `nomeSubclasse` | `string` |  |
| `codigoServico` | `integer (int64)` |  |
| `nomeServico` | `string` |  |
| `codigoCpc` | `integer (int64)` |  |
| `exclusivoCentralCompras` | `boolean` |  |
| `statusServico` | `boolean` |  |
| `dataHoraAtualizacao` | `string (date-time)` | YYYY-MM-DD |

**Example:**

```json
{
  "codigoSecao": 1,
  "nomeSecao": "example",
  "codigoDivisao": 1,
  "nomeDivisao": "example",
  "codigoGrupo": 1,
  "nomeGrupo": "example",
  "codigoClasse": 1,
  "nomeClasse": "example",
  "codigoSubclasse": 1,
  "nomeSubclasse": "example",
  "codigoServico": 1,
  "nomeServico": "example",
  "codigoCpc": 1,
  "exclusivoCentralCompras": true,
  "statusServico": true,
  "dataHoraAtualizacao": "2025-01-15"
}
```

### 6.32 Service Unit of Measure

**Unit of measure for a service item.**

| Field | Type | Description |
|---|---|---|
| `codigoServico` | `integer (int64)` |  |
| `siglaUnidadeMedida` | `string` |  |
| `nomeUnidadeMedida` | `string` |  |
| `statusUnidadeMedida` | `boolean` |  |

**Example:**

```json
{
  "codigoServico": 1,
  "siglaUnidadeMedida": "example",
  "nomeUnidadeMedida": "example",
  "statusUnidadeMedida": true
}
```

### 6.33 Service Expense Nature

**Expense nature for a service item.**

| Field | Type | Description |
|---|---|---|
| `codigoServico` | `integer (int64)` |  |
| `codigoNaturezaDespesa` | `string` |  |
| `nomeNaturezaDespesa` | `string` |  |
| `statusNaturezaDespesa` | `boolean` |  |

**Example:**

```json
{
  "codigoServico": 1,
  "codigoNaturezaDespesa": "example",
  "nomeNaturezaDespesa": "example",
  "statusNaturezaDespesa": true
}
```

### 6.34 Supplier

**Supplier (fornecedor) record.**

| Field | Type | Description |
|---|---|---|
| `ativo` | `boolean` |  |
| `cnpj` | `string` |  |
| `cpf` | `string` |  |
| `habilitadoLicitar` | `boolean` |  |
| `codigoCnae` | `integer` |  |
| `nomeCnae` | `string` |  |
| `nomeMunicipio` | `string` |  |
| `naturezaJuridicaId` | `integer (int64)` |  |
| `naturezaJuridicaNome` | `string` |  |
| `porteEmpresaId` | `integer (int64)` |  |
| `porteEmpresaNome` | `string` |  |
| `nomeRazaoSocialFornecedor` | `string` |  |
| `ufSigla` | `string` |  |

**Example:**

```json
{
  "ativo": true,
  "cnpj": "example",
  "cpf": "example",
  "habilitadoLicitar": true,
  "codigoCnae": 1,
  "nomeCnae": "example",
  "nomeMunicipio": "example",
  "naturezaJuridicaId": 1,
  "naturezaJuridicaNome": "example",
  "porteEmpresaId": 1,
  "porteEmpresaNome": "example",
  "nomeRazaoSocialFornecedor": "example",
  "ufSigla": "example"
}
```

### 6.35 Legacy Bid (Pregão)

**Legacy pregão record (Lei 8.666/93).**

| Field | Type | Description |
|---|---|---|
| `id_compra` | `string` |  |
| `co_processo` | `string` |  |
| `co_portaria` | `string` |  |
| `co_uasg` | `integer (int32)` |  |
| `no_ausg` | `string` |  |
| `co_orgao` | `integer (int32)` |  |
| `no_orgao` | `string` |  |
| `numero` | `integer (int32)` |  |
| `ds_situacao_pregao` | `string` |  |
| `ds_tipo_pregao` | `string` |  |
| `ds_tipo_pregao_compra` | `string` |  |
| `tx_objeto` | `string` |  |
| `vl_estimado_total` | `string` |  |
| `vl_homologado_total` | `string` |  |
| `dt_portaria` | `string (date-time)` |  |
| `dt_data_edital` | `string (date-time)` |  |
| `dt_inicio_proposta` | `string (date-time)` |  |
| `dt_fim_proposta` | `string (date-time)` |  |
| `dt_alteracao` | `string (date-time)` |  |
| `dt_encerramento` | `string (date-time)` |  |
| `dt_resultado` | `string (date-time)` |  |
| `pertence14133` | `boolean` |  |

**Example:**

```json
{
  "id_compra": "example",
  "co_processo": "example",
  "co_portaria": "example",
  "co_uasg": 1,
  "no_ausg": "example",
  "co_orgao": 1,
  "no_orgao": "example",
  "numero": 1,
  "ds_situacao_pregao": "example",
  "ds_tipo_pregao": "example",
  "ds_tipo_pregao_compra": "example",
  "tx_objeto": "example",
  "vl_estimado_total": "example",
  "vl_homologado_total": "example",
  "dt_portaria": "2025-01-15",
  "dt_data_edital": "2025-01-15",
  "dt_inicio_proposta": "2025-01-15",
  "dt_fim_proposta": "2025-01-15",
  "dt_alteracao": "2025-01-15",
  "dt_encerramento": "2025-01-15",
  "dt_resultado": "2025-01-15",
  "pertence14133": true
}
```

### 6.36 Legacy Pregão Items

**Items from a legacy pregão.**

| Field | Type | Description |
|---|---|---|
| `idCompra` | `string` |  |
| `idCompraItem` | `string` |  |
| `decreto7174` | `string` |  |
| `situacaoItem` | `string` |  |
| `descricaoItem` | `string` |  |
| `descricaoDetalhadaItem` | `string` |  |
| `margemPreferencial` | `string` |  |
| `tratamentoDiferenciado` | `string` |  |
| `quantidadeItem` | `string` |  |
| `unidadeFornecimento` | `string` |  |
| `valorEstimadoItem` | `string` |  |
| `menorLance` | `string` |  |
| `valorNegociado` | `string` |  |
| `valorHomologadoItem` | `string` |  |
| `fornecedorVencedor` | `string` |  |
| `noAdjudic` | `string` |  |
| `noHom` | `string` |  |
| `dtEncerramento` | `string (date)` |  |
| `dtAdjudic` | `string (date)` |  |
| `dtHom` | `string (date)` |  |
| `dtAlteracao` | `string (date-time)` |  |

**Example:**

```json
{
  "idCompra": "example",
  "idCompraItem": "example",
  "decreto7174": "example",
  "situacaoItem": "example",
  "descricaoItem": "example",
  "descricaoDetalhadaItem": "example",
  "margemPreferencial": "example",
  "tratamentoDiferenciado": "example",
  "quantidadeItem": "example",
  "unidadeFornecimento": "example",
  "valorEstimadoItem": "example",
  "menorLance": "example",
  "valorNegociado": "example",
  "valorHomologadoItem": "example",
  "fornecedorVencedor": "example",
  "noAdjudic": "example",
  "noHom": "example",
  "dtEncerramento": "2025-01-15",
  "dtAdjudic": "2025-01-15",
  "dtHom": "2025-01-15",
  "dtAlteracao": "2025-01-15"
}
```

### 6.37 Legacy Tender

**Legacy licitação record.**

| Field | Type | Description |
|---|---|---|
| `id_compra` | `string` |  |
| `identificador` | `string` |  |
| `numero_processo` | `string` |  |
| `uasg` | `integer (int32)` |  |
| `modalidade` | `integer (int32)` |  |
| `nome_modalidade` | `string` |  |
| `numero_aviso` | `integer (int32)` |  |
| `situacao_aviso` | `string` |  |
| `tipo_pregao` | `string` |  |
| `tipo_recurso` | `string` |  |
| `nome_responsavel` | `string` |  |
| `funcao_responsavel` | `string` |  |
| `numero_itens` | `integer (int32)` |  |
| `valor_estimado_total` | `number` |  |
| `valor_homologado_total` | `number` |  |
| `informacoes_gerais` | `string` |  |
| `objeto` | `string` |  |
| `endereco_entrega_edital` | `string` |  |
| `codigo_municipio_uasg` | `integer (int32)` |  |
| `data_abertura_proposta` | `string (date)` | YYYY-MM-DD |
| `data_entrega_edital` | `string (date)` | YYYY-MM-DD |
| `data_entrega_proposta` | `string (date)` | YYYY-MM-DD |
| `data_publicacao` | `string (date)` | YYYY-MM-DD |
| `dt_alteracao` | `string (date-time)` | YYYY-MM-DD |
| `pertence14133` | `boolean` |  |

**Example:**

```json
{
  "id_compra": "example",
  "identificador": "example",
  "numero_processo": "example",
  "uasg": 1,
  "modalidade": 1,
  "nome_modalidade": "example",
  "numero_aviso": 1,
  "situacao_aviso": "example",
  "tipo_pregao": "example",
  "tipo_recurso": "example",
  "nome_responsavel": "example",
  "funcao_responsavel": "example",
  "numero_itens": 1,
  "valor_estimado_total": 0.0,
  "valor_homologado_total": 0.0,
  "informacoes_gerais": "example",
  "objeto": "example",
  "endereco_entrega_edital": "example",
  "codigo_municipio_uasg": 1,
  "data_abertura_proposta": "2025-01-15",
  "data_entrega_edital": "2025-01-15",
  "data_entrega_proposta": "2025-01-15",
  "data_publicacao": "2025-01-15",
  "dt_alteracao": "2025-01-15",
  "pertence14133": true
}
```

### 6.38 Legacy Tender Items

**Items from a legacy licitação.**

| Field | Type | Description |
|---|---|---|
| `isnSidecResultadoCompra` | `integer (int64)` |  |
| `numeroLicitacao` | `string` |  |
| `uasg` | `integer (int64)` |  |
| `nomeUasg` | `string` |  |
| `modalidade` | `integer (int32)` |  |
| `nomeModalidade` | `string` |  |
| `numeroAviso` | `integer (int32)` |  |
| `numeroItemLicitacao` | `integer (int32)` |  |
| `codigoItemMaterial` | `integer (int64)` |  |
| `nomeMaterial` | `string` |  |
| `codigoItemServico` | `integer (int64)` |  |
| `nomeServico` | `string` |  |
| `cnpjFornecedor` | `string` |  |
| `nomeFornecedor` | `string` |  |
| `quantidade` | `number` |  |
| `unidade` | `string` |  |
| `descricaoItem` | `string` |  |
| `beneficio` | `string` |  |
| `valorEstimado` | `number` |  |
| `decreto7174` | `string` |  |
| `criterioJulgamento` | `string` |  |
| `cpfVencedor` | `string` |  |
| `nomeVencedorPf` | `string` |  |
| `sustentavel` | `integer (int32)` |  |
| `dtAlteracao` | `string (date-time)` | YYYY-MM-DD |
| `idCompra` | `string` |  |
| `idCompraItem` | `string` |  |

**Example:**

```json
{
  "isnSidecResultadoCompra": 1,
  "numeroLicitacao": "example",
  "uasg": 1,
  "nomeUasg": "example",
  "modalidade": 1,
  "nomeModalidade": "example",
  "numeroAviso": 1,
  "numeroItemLicitacao": 1,
  "codigoItemMaterial": 1,
  "nomeMaterial": "example",
  "codigoItemServico": 1,
  "nomeServico": "example",
  "cnpjFornecedor": "example",
  "nomeFornecedor": "example",
  "quantidade": 0.0,
  "unidade": "example",
  "descricaoItem": "example",
  "beneficio": "example",
  "valorEstimado": 0.0,
  "decreto7174": "example",
  "criterioJulgamento": "example",
  "cpfVencedor": "example",
  "nomeVencedorPf": "example",
  "sustentavel": 1,
  "dtAlteracao": "2025-01-15",
  "idCompra": "example",
  "idCompraItem": "example"
}
```

### 6.39 Legacy Dispense

**Purchase without bidding (dispensa de licitação).**

| Field | Type | Description |
|---|---|---|
| `idCompra` | `string` |  |
| `co_orgao` | `string` |  |
| `co_orgao_superior` | `string` |  |
| `co_uasg` | `integer (int64)` |  |
| `no_ausg` | `string` |  |
| `co_modalidade_licitacao` | `integer (int32)` |  |
| `ds_lei` | `string` |  |
| `nu_processo` | `string` |  |
| `qt_total_item` | `integer (int64)` |  |
| `vr_estimado` | `number` |  |
| `nu_aviso_licitacao` | `integer (int64)` |  |
| `ds_objeto_licitacao` | `string` |  |
| `ds_fundamento_legal` | `string` |  |
| `ds_justificativa` | `string` |  |
| `no_responsavel_decl_disp` | `string` |  |
| `no_cargo_resp_decl_disp` | `string` |  |
| `no_responsavel_ratificacao` | `string` |  |
| `no_cargo_resp_ratificacao` | `string` |  |
| `dtDeclaracaoDispensa` | `string (date)` | YYYY-MM-DD |
| `dtRatificacao` | `string (date)` | YYYY-MM-DD |
| `dtPublicacao` | `string (date)` | YYYY-MM-DD |
| `dt_ano_aviso` | `integer (int32)` |  |
| `dt_alteracao` | `string (date)` | YYYY-MM-DD |
| `pertence14133` | `boolean` |  |

**Example:**

```json
{
  "idCompra": "example",
  "co_orgao": "example",
  "co_orgao_superior": "example",
  "co_uasg": 1,
  "no_ausg": "example",
  "co_modalidade_licitacao": 1,
  "ds_lei": "example",
  "nu_processo": "example",
  "qt_total_item": 1,
  "vr_estimado": 0.0,
  "nu_aviso_licitacao": 1,
  "ds_objeto_licitacao": "example",
  "ds_fundamento_legal": "example",
  "ds_justificativa": "example",
  "no_responsavel_decl_disp": "example",
  "no_cargo_resp_decl_disp": "example",
  "no_responsavel_ratificacao": "example",
  "no_cargo_resp_ratificacao": "example",
  "dtDeclaracaoDispensa": "2025-01-15",
  "dtRatificacao": "2025-01-15",
  "dtPublicacao": "2025-01-15",
  "dt_ano_aviso": 1,
  "dt_alteracao": "2025-01-15",
  "pertence14133": true
}
```

### 6.40 Legacy Dispense Items

**Items from a purchase without bidding.**

| Field | Type | Description |
|---|---|---|
| `id` | `integer (int32)` |  |
| `isn_sidec_resultado_compra` | `integer (int32)` |  |
| `coServico` | `integer (int32)` |  |
| `dsDetalhada` | `string` |  |
| `inTipoFornecedorVencedor` | `string` |  |
| `noFornecedorVencedor` | `string` |  |
| `noConjuntoMateriais` | `string` |  |
| `noMarcaMaterial` | `string` |  |
| `noServico` | `string` |  |
| `noUnidadeMedida` | `string` |  |
| `nuCnpjVencedor` | `string` |  |
| `nuCpfVencedor` | `string` |  |
| `nuCpfCnpjFiltro` | `string` |  |
| `qtMaterialAlt` | `integer (int64)` |  |
| `vrEstimado` | `number` |  |
| `inMaterialServico` | `string` |  |
| `dtPublicacao` | `string (date)` | YYYY-MM-DD |
| `idCompra` | `string` |  |
| `idCompraItem` | `string` |  |
| `coUasg` | `integer` |  |
| `coModalidadeLicitacao` | `integer (int32)` |  |
| `noModalidadeLicitacao` | `string` |  |
| `nuAvisoLicitacao` | `integer` |  |
| `dtAnoAvisoLicitacao` | `integer (int32)` |  |
| `nuInciso` | `string` |  |
| `nuProcesso` | `string` |  |
| `qtTotalItem` | `integer` |  |
| `dsObjetoLicitacao` | `string` |  |
| `dsFundamentoLegal` | `string` |  |
| `dsJustificativa` | `string` |  |
| `nuCpfRespDeclDisp` | `string` |  |
| `nuCpfRespRatificacao` | `string` |  |
| `nuCpfRespPublicacao` | `string` |  |
| `noResponsavelDeclDisp` | `string` |  |
| `noCargoRespDeclDisp` | `string` |  |
| `noResponsavelRatificacao` | `string` |  |
| `noCargoRespRatificacao` | `string` |  |
| `nuItemMaterial` | `integer (int32)` |  |
| `vrEstimadoItem` | `number` |  |
| `dsFabricante` | `string` |  |
| `dtAlteracao` | `string (date-time)` | YYYY-MM-DD |
| `coOrgao` | `string` |  |

**Example:**

```json
{
  "id": 1,
  "isn_sidec_resultado_compra": 1,
  "coServico": 1,
  "dsDetalhada": "example",
  "inTipoFornecedorVencedor": "example",
  "noFornecedorVencedor": "example",
  "noConjuntoMateriais": "example",
  "noMarcaMaterial": "example",
  "noServico": "example",
  "noUnidadeMedida": "example",
  "nuCnpjVencedor": "example",
  "nuCpfVencedor": "example",
  "nuCpfCnpjFiltro": "example",
  "qtMaterialAlt": 1,
  "vrEstimado": 0.0,
  "inMaterialServico": "example",
  "dtPublicacao": "2025-01-15",
  "idCompra": "example",
  "idCompraItem": "example",
  "coUasg": 1,
  "coModalidadeLicitacao": 1,
  "noModalidadeLicitacao": "example",
  "nuAvisoLicitacao": 1,
  "dtAnoAvisoLicitacao": 1,
  "nuInciso": "example",
  "nuProcesso": "example",
  "qtTotalItem": 1,
  "dsObjetoLicitacao": "example",
  "dsFundamentoLegal": "example",
  "dsJustificativa": "example",
  "nuCpfRespDeclDisp": "example",
  "nuCpfRespRatificacao": "example",
  "nuCpfRespPublicacao": "example",
  "noResponsavelDeclDisp": "example",
  "noCargoRespDeclDisp": "example",
  "noResponsavelRatificacao": "example",
  "noCargoRespRatificacao": "example",
  "nuItemMaterial": 1,
  "vrEstimadoItem": 0.0,
  "dsFabricante": "example",
  "dtAlteracao": "2025-01-15",
  "coOrgao": "example"
}
```

### 6.41 Legacy RDC

**RDC (Régime Diferenciado de Contratações) record.**

| Field | Type | Description |
|---|---|---|
| `data_abertura_proposta` | `string (date-time)` |  |
| `data_entrega_edital` | `string (date-time)` |  |
| `data_entrega_proposta` | `string (date-time)` |  |
| `data_publicacao` | `string (date)` |  |
| `endereco_entrega_edital` | `string` |  |
| `forma_de_realizacao_licitacao` | `string` |  |
| `funcao_responsavel` | `string` |  |
| `identificador` | `string` |  |
| `informacoes_gerais` | `string` |  |
| `modalidade` | `integer (int32)` |  |
| `nome_responsavel` | `string` |  |
| `numero_aviso` | `integer (int32)` |  |
| `numero_itens` | `integer (int32)` |  |
| `numero_processo` | `string` |  |
| `objeto` | `string` |  |
| `situacao_aviso` | `string` |  |
| `tipo_recurso` | `string` |  |
| `uasg` | `integer (int32)` |  |
| `orgao_uasg` | `integer (int32)` |  |
| `uf_uasg` | `string` |  |

**Example:**

```json
{
  "data_abertura_proposta": "2025-01-15",
  "data_entrega_edital": "2025-01-15",
  "data_entrega_proposta": "2025-01-15",
  "data_publicacao": "2025-01-15",
  "endereco_entrega_edital": "example",
  "forma_de_realizacao_licitacao": "example",
  "funcao_responsavel": "example",
  "identificador": "example",
  "informacoes_gerais": "example",
  "modalidade": 1,
  "nome_responsavel": "example",
  "numero_aviso": 1,
  "numero_itens": 1,
  "numero_processo": "example",
  "objeto": "example",
  "situacao_aviso": "example",
  "tipo_recurso": "example",
  "uasg": 1,
  "orgao_uasg": 1,
  "uf_uasg": "example"
}
```

### 6.42 OCDS Release

**Top-level OCDS response container.**

| Field | Type | Description |
|---|---|---|
| `publisherDTO` | `PublisherDTO` |  |
| `publishedDate` | `string (date-time)` |  |
| `version` | `string` |  |
| `publicationPolicy` | `string` |  |
| `license` | `string` |  |
| `extensions` | `array<string>` |  |
| `releases` | `array<ReleaseDTO>` |  |
| `links` | `LinksDTO` |  |
| `uri` | `string` |  |

**Example:**

```json
{
  "publisherDTO": {
  "name": "example",
  "uri": "example"
},
  "publishedDate": "2025-01-15",
  "version": "example",
  "publicationPolicy": "example",
  "license": "example",
  "extensions": ["example"],
  "releases": [{
  "ocid": "example",
  "id": "example",
  "date": "2025-01-15",
  "tag": ["example"],
  "initiationType": "example",
  "buyer": {
  "id": "example",
  "name": "example"
},
  "language": "example",
  "parties": [{
  "id": "example",
  "name": "example",
  "identifier": {
  "scheme": "example",
  "id": "example",
  "legalName": "example"
},
  "additionalIdentifiers": [{
  "id": "example",
  "legalName": "example"
}],
  "address": {
  "region": "example",
  "locality": "example",
  "countryName": "example"
},
  "roles": ["example"],
  "details": {
  "classifications": [{
  "scheme": "example",
  "id": "example",
  "uri": "example"
}]
},
  "suppliers": [{
  "id": "example",
  "name": "example"
}]
}],
  "tender": {
  "id": "example",
  "title": "example",
  "description": "example",
  "procuringEntity": {
  "name": "example",
  "id": "example"
},
  "value": {
  "amount": 0.0,
  "currency": "example"
},
  "procurementMethod": "example",
  "procurementMethodDetails": "example",
  "procurementMethodRationale": "example",
  "submissionMethod": ["example"],
  "tenderPeriod": {
  "startDate": "2025-01-15",
  "endDate": "2025-01-15",
  "maxExtentDate": "2025-01-15",
  "durationInDays": 1
},
  "items": [{
  "id": "example",
  "description": "example",
  "statusDetails": "example",
  "quantity": 0.0,
  "unit": {
  "name": "example",
  "value": {
  "amount": 0.0,
  "currency": "example"
}
},
  "relatedLot": "example"
}],
  "lots": [{
  "id": "example",
  "statusDetailsId": "example",
  "statusDetails": "example",
  "value": {
  "amount": 0.0,
  "currency": "example"
},
  "confidentialBudget": true,
  "asset": "example",
  "realEstateRegistrationCode": "example",
  "standardPreferenceMarginApplicability": true,
  "standardPreferenceMarginPercentage": 0.0,
  "additionalPreferenceMarginApplicability": true,
  "additionalPreferenceMarginPercentage": 0.0,
  "ncmNbsCode": "example",
  "ncmNbsDescription": "example",
  "catalogItemCategoryId": 1,
  "catalogItemCategoryName": "example",
  "catalogItemCode": 1,
  "awardCriteria": "example",
  "awardCriteriaDetails": "example",
  "sustainability": [{
  "goal": "example",
  "strategies": ["example"]
}],
  "otherRequirements": {
  "reservedParticipation": ["example"]
},
  "subcontractingTerms": {
  "description": "example"
}
}]
},
  "awards": [{
  "id": "example",
  "title": "example",
  "description": "example",
  "date": "2025-01-15",
  "hasSubcontracting": true,
  "value": {
  "amount": 0.0,
  "currency": "example"
},
  "suppliers": [{
  "id": "example",
  "name": "example"
}],
  "items": [{
  "id": "example",
  "description": "example",
  "statusDetails": "example",
  "quantity": 0.0,
  "unit": {
  "name": "example",
  "value": {
  "amount": 0.0,
  "currency": "example"
}
},
  "relatedLot": "example"
}]
}]
}],
  "links": {
  "next": "example",
  "prev": "example"
},
  "uri": "example"
}
```

### 6.43 OCDS Release Item

**A single OCDS release (purchase record).**

| Field | Type | Description |
|---|---|---|
| `ocid` | `string` |  |
| `id` | `string` |  |
| `date` | `string (date-time)` |  |
| `tag` | `array<string>` |  |
| `initiationType` | `string` |  |
| `buyer` | `BuyerDTO` |  |
| `language` | `string` |  |
| `parties` | `array<PartyDTO>` |  |
| `tender` | `TenderDTO` |  |
| `awards` | `array<AwardDTO>` |  |

**Example:**

```json
{
  "ocid": "example",
  "id": "example",
  "date": "2025-01-15",
  "tag": ["example"],
  "initiationType": "example",
  "buyer": {
  "id": "example",
  "name": "example"
},
  "language": "example",
  "parties": [{
  "id": "example",
  "name": "example",
  "identifier": {
  "scheme": "example",
  "id": "example",
  "legalName": "example"
},
  "additionalIdentifiers": [{
  "id": "example",
  "legalName": "example"
}],
  "address": {
  "region": "example",
  "locality": "example",
  "countryName": "example"
},
  "roles": ["example"],
  "details": {
  "classifications": [{
  "scheme": "example",
  "id": "example",
  "uri": "example"
}]
},
  "suppliers": [{
  "id": "example",
  "name": "example"
}]
}],
  "tender": {
  "id": "example",
  "title": "example",
  "description": "example",
  "procuringEntity": {
  "name": "example",
  "id": "example"
},
  "value": {
  "amount": 0.0,
  "currency": "example"
},
  "procurementMethod": "example",
  "procurementMethodDetails": "example",
  "procurementMethodRationale": "example",
  "submissionMethod": ["example"],
  "tenderPeriod": {
  "startDate": "2025-01-15",
  "endDate": "2025-01-15",
  "maxExtentDate": "2025-01-15",
  "durationInDays": 1
},
  "items": [{
  "id": "example",
  "description": "example",
  "statusDetails": "example",
  "quantity": 0.0,
  "unit": {
  "name": "example",
  "value": {
  "amount": 0.0,
  "currency": "example"
}
},
  "relatedLot": "example"
}],
  "lots": [{
  "id": "example",
  "statusDetailsId": "example",
  "statusDetails": "example",
  "value": {
  "amount": 0.0,
  "currency": "example"
},
  "confidentialBudget": true,
  "asset": "example",
  "realEstateRegistrationCode": "example",
  "standardPreferenceMarginApplicability": true,
  "standardPreferenceMarginPercentage": 0.0,
  "additionalPreferenceMarginApplicability": true,
  "additionalPreferenceMarginPercentage": 0.0,
  "ncmNbsCode": "example",
  "ncmNbsDescription": "example",
  "catalogItemCategoryId": 1,
  "catalogItemCategoryName": "example",
  "catalogItemCode": 1,
  "awardCriteria": "example",
  "awardCriteriaDetails": "example",
  "sustainability": [{
  "goal": "example",
  "strategies": ["example"]
}],
  "otherRequirements": {
  "reservedParticipation": ["example"]
},
  "subcontractingTerms": {
  "description": "example"
}
}]
},
  "awards": [{
  "id": "example",
  "title": "example",
  "description": "example",
  "date": "2025-01-15",
  "hasSubcontracting": true,
  "value": {
  "amount": 0.0,
  "currency": "example"
},
  "suppliers": [{
  "id": "example",
  "name": "example"
}],
  "items": [{
  "id": "example",
  "description": "example",
  "statusDetails": "example",
  "quantity": 0.0,
  "unit": {
  "name": "example",
  "value": {
  "amount": 0.0,
  "currency": "example"
}
},
  "relatedLot": "example"
}]
}]
}
```

### 6.44 ALICE Analysis (with items)

**ALICE purchase analysis including item warnings.**

| Field | Type | Description |
|---|---|---|
| `msgErro` | `string` |  |
| `dataSolicitacaoAnalise` | `string` |  |
| `dataEncerramentoAnalise` | `string` |  |
| `ticketAnalise` | `string` |  |
| `tipoAnalise` | `integer (int32)` |  |
| `codigoStatusAnalise` | `integer (int32)` |  |
| `descricaoStatusAnalise` | `string` |  |
| `chaveCompra` | `string` |  |
| `itens` | `array<AvisosVwDTO>` |  |

**Example:**

```json
{
  "msgErro": "example",
  "dataSolicitacaoAnalise": "example",
  "dataEncerramentoAnalise": "example",
  "ticketAnalise": "example",
  "tipoAnalise": 1,
  "codigoStatusAnalise": 1,
  "descricaoStatusAnalise": "example",
  "chaveCompra": "example",
  "itens": [{
  "idAviso": 1,
  "codigoTipoAviso": 1,
  "nomeTipoAviso": "example",
  "texto": "example",
  "descricao": "example",
  "fundamentacao": "example",
  "numeroSequencialAviso": 1
}]
}
```

### 6.45 ALICE Analysis (no items)

**ALICE purchase analysis without item details.**

| Field | Type | Description |
|---|---|---|
| `msgErro` | `string` |  |
| `dataSolicitacaoAnalise` | `string` |  |
| `dataEncerramentoAnalise` | `string` |  |
| `ticketAnalise` | `string` |  |
| `tipoAnalise` | `integer (int32)` |  |
| `codigoStatusAnalise` | `integer (int32)` |  |
| `descricaoStatusAnalise` | `string` |  |
| `chaveCompra` | `string` |  |

**Example:**

```json
{
  "msgErro": "example",
  "dataSolicitacaoAnalise": "example",
  "dataEncerramentoAnalise": "example",
  "ticketAnalise": "example",
  "tipoAnalise": 1,
  "codigoStatusAnalise": 1,
  "descricaoStatusAnalise": "example",
  "chaveCompra": "example"
}
```

### 6.46 API Usage KPIs

**Monthly API usage metrics.**

| Field | Type | Description |
|---|---|---|
| `anoMes` | `string` |  |
| `ano` | `integer (int32)` |  |
| `mes` | `integer (int32)` |  |
| `totalServicos` | `integer (int32)` |  |
| `totalRequisicoes` | `integer (int64)` |  |
| `percentualSucesso` | `number` |  |
| `mediaTempoRespostaMs` | `number` |  |
| `totalDownloadGb` | `number` |  |
| `totalDownloadMbytes` | `number` |  |

**Example:**

```json
{
  "anoMes": "example",
  "ano": 1,
  "mes": 1,
  "totalServicos": 1,
  "totalRequisicoes": 1,
  "percentualSucesso": 0.0,
  "mediaTempoRespostaMs": 0.0,
  "totalDownloadGb": 0.0,
  "totalDownloadMbytes": 0.0
}
```

### 6.47 Login Request

**Login payload (credentials).**

| Field | Type | Description |
|---|---|---|
| `login` | `string` |  |
| `senha` | `string` |  |

**Example:**

```json
{
  "login": "example",
  "senha": "example"
}
```

### 6.48 User Record

**User data returned after create/update.**

| Field | Type | Description |
|---|---|---|
| `id` | `integer (int32)` |  |
| `nome` | `string` |  |
| `cpfCnpj` | `string` |  |
| `email` | `string` |  |
| `telefone` | `string` |  |
| `login` | `string` |  |
| `administrador` | `boolean` |  |
| `dataInclusao` | `string (date-time)` |  |
| `dataAtualizacao` | `string (date-time)` |  |
| `dataDelecaoSuspensao` | `string (date-time)` |  |
| `excluidoSuspenso` | `boolean` |  |
| `razaoExclusaoSuspensao` | `string` |  |

**Example:**

```json
{
  "id": 1,
  "nome": "example",
  "cpfCnpj": "example",
  "email": "example",
  "telefone": "example",
  "login": "example",
  "administrador": true,
  "dataInclusao": "2025-01-15",
  "dataAtualizacao": "2025-01-15",
  "dataDelecaoSuspensao": "2025-01-15",
  "excluidoSuspenso": true,
  "razaoExclusaoSuspensao": "example"
}
```

## 7. Practical Examples

### 7.1 Login (obtain JWT)

```bash
curl -s -X POST https://dadosabertos.compras.gov.br/autenticacao/login \
  -H "Content-Type: application/json" \
  -d '{"login": "user@example.com", "senha": "secret"}'
```

### 7.2 Query UASGs (public)

```bash
curl -s "https://dadosabertos.compras.gov.br/modulo-uasg/1_consultarUasg?statusUasg=true&pagina=1" \
  -H "Accept: application/json" | python3 -m json.tool
```

### 7.3 Query Contracts (date-range filter)

```bash
curl -s "https://dadosabertos.compras.gov.br/modulo-contratos/1_consultarContratos \
  ?codigoOrgao=190660 \
  &dataVigenciaInicialMin=2025-01-01 \
  &dataVigenciaInicialMax=2025-06-30 \
  &pagina=1" \
  -H "Authorization: Bearer $JWT"
```

### 7.4 Query ARP by End-of-Vigência

```bash
curl -s "https://dadosabertos.compras.gov.br/modulo-arp/1.2_consultarARP_FimVigencia \
  ?dataVigenciaFinalMin=2025-07-01 \
  &dataVigenciaFinalMax=2025-12-31 \
  &pagina=1" \
  -H "Authorization: Bearer $JWT"
```

### 7.5 Material Price Research

```bash
curl -s "https://dadosabertos.compras.gov.br/modulo-pesquisa-preco/1_consultarMaterial \
  ?codigoItemCatalogo=587203 \
  &estado=SP \
  &pagina=1"
```

### 7.6 PNCP Contratações (Lei 14.133)

```bash
curl -s "https://dadosabertos.compras.gov.br/modulo-contratacoes/1_consultarContratacoes_PNCP_14133 \
  ?dataPublicacaoPncpInicial=2025-01-01 \
  &dataPublicacaoPncpFinal=2025-03-31 \
  &codigoModalidade=8 \
  &pagina=1"
```

### 7.7 OCDS Releases

```bash
curl -s "https://dadosabertos.compras.gov.br/modulo-ocds/1_releases \
  ?buyerID=00394602000145 \
  &releaseStartDate=2025-01-01 \
  &releaseEndDate=2025-03-31"
```

### 7.8 ALICE Tickets (requires auth)

```bash
curl -s "https://dadosabertos.compras.gov.br/alice/tickets?tickets=12345&tickets=67890" \
  -H "Authorization: Bearer $JWT"
```

### 7.9 Legacy Pregão Items

```bash
curl -s "https://dadosabertos.compras.gov.br/modulo-legado/4_consultarItensPregoes \
  ?co_uasg=998877 \
  &dt_hom_inicial=2025-01-01 \
  &dt_hom_final=2025-06-30 \
  &pagina=1"
```

### 7.10 Supplier Query

```bash
curl -s "https://dadosabertos.compras.gov.br/modulo-fornecedor/1_consultarFornecedor \
  ?ativo=true \
  &pagina=1"
```

## 8. Glossary

| Term | Full Name | Description |
|---|---|---|
| **UASG** | Unidade Administrativa de Serviços Gerais | Administrative procurement unit within a government body |
| **ARP** | Ata de Registro de Preço | Price register record: a formal document registering prices from competitive processes |
| **PGC** | Programa de Gerenciamento de Compras | Purchase management program: aggregate demand planning across government bodies |
| **PNCP** | Portal Nacional de Contratações Públicas | National Public Procurement Portal (Lei 14.133/2021) |
| **OCDS** | Open Contracting Data Standard | International standard for publishing procurement data (version 1.1) |
| **CATMAT** | Catálogo de Materiais | Material catalog code (used in material procurement) |
| **CATSER** | Catálogo de Serviços | Service catalog code (used in service procurement) |
| **ALICE** | — | AI-powered purchase analysis tool within Compras.gov.br |
| **Lei 8.666/93** | — | Legacy Brazilian procurement law (replaced by Lei 14.133/21 for new contracts) |
| **Lei 14.133/21** | — | New Brazilian procurement law (PNCP framework) |
| **RDC** | Régime Diferenciado de Contratações | Special procurement regime for large infrastructure projects |
| **Pregão** | — | Reverse auction (bidding type) under Lei 8.666/93 |
| **SIASG** | Sistema de Administração de Materiais e Serviços Gerais | Federal government procurement management system |
| **SIPEC** | Sistema Integrado de Planejamento e Contratações | Integrated planning and procurement system |
| **PNCP ID** | — | Unique identifier in the PNCP portal |

## 9. Appendix

### 9.1 CSV Variants

Endpoints with `_CSV` suffix or `.1_` infix return `text/csv` with the same parameters.
CSV is useful for bulk exports.

### 9.2 Incremental Updates

Endpoints ending in `_Id` or accepting `dataAtualizacao` / `dt_alteracao` parameters
allow querying a single record by its internal ID or filtering by last-update date.

### 9.3 Date Filters

Most list endpoints require a mandatory date range (`dataVigenciaInicialMin/Max`,
 `dataPublicacaoPncpInicial/Final`, `dt_data_edital_inicial/final`, etc.).
 Always provide both `Min` and `Max` values.

### 9.4 Pagination Limits

The API does not declare an explicit maximum page size. Start with small pages
 (e.g., `tamanhoPagina=10`) and increase as needed. The `totalPaginas` and
 `paginasRestantes` fields in the response guide pagination.

### 9.5 Rate Limiting

No rate-limit headers or documentation were found in the spec.
 Use reasonable request intervals (e.g., 1 request/second) to avoid triggering
 server-side throttling.

### 9.6 Deleted Records

Many DTOs include `dataHoraExclusao`, `*Excluido`, or `contratacaoExcluida` fields.
 Deleted records may still appear in query results unless explicitly filtered.

### 9.7 `pertence14133` Flag

Legacy endpoints (module 06) include a `pertence14133` boolean.
 `true` indicates the record belongs to the new Lei 14.133/21 framework;
 `false` indicates it falls under the legacy Lei 8.666/93.
