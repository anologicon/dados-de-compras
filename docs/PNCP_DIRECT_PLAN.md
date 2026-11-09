# Integração direta com o PNCP — plano do próximo ciclo

**Estado: planejamento; implementação e coleta real não iniciadas.**

Decisões de escopo confirmadas em 2026-10-26. Referência de código: `0cdab76`.
A confirmação deste plano não autoriza iniciar coletas, modificar bases reais,
reiniciar serviços ou alterar agendas existentes.

## 1. Objetivo e decisões confirmadas

Corrigir a lacuna de cobertura observada em Brusque acrescentando o **PNCP
oficial como fonte direta**, além da API do Compras.gov.br. Não se trata de
habilitar apenas outra modalidade de licitação.

- Primeira entrega: **compra → itens → resultados → fornecedor observado**,
  integrada ao panorama, à listagem e à ficha existentes.
- Novas coletas gerenciadas: **PNCP direto + Compras.gov.br por padrão**.
  Registrar explicitamente as fontes escolhidas; permitir seleção de fonte.
- Execuções já criadas, retomadas e agendas existentes mantêm seu escopo atual.
  Não acrescentar a fonte ao histórico ou à fila por mudança de default.
- Piloto: **Brusque/SC, IBGE 4202909, 2026-01-01 a 2026-01-31**.
- Preservar o recorte territorial atual: unidades/órgãos localizados no município,
  não somente a prefeitura. O pertencimento precisa de evidência do registro ou
  de uma relação parental comprovada, não do diretório ou filtro da coleta.
- Abranger todas as modalidades válidas do domínio oficial, não apenas pregão
  eletrônico e dispensa. Domínio consultado/versionado e limites ficam no relatório.

### Evidência que motivou a integração

Na investigação anterior, as 52 respostas PNCP armazenadas pelo coletor do
Compras.gov.br para Brusque continham listas vazias. Uma comparação diagnóstica
com o PNCP direto, no período **2026-03-01 a 2026-10-25**, informou 236 registros
de pregão eletrônico e 86 de dispensa. São contagens da fonte naquele momento,
não compras únicas conciliadas, nem metas para o piloto de janeiro.

Há também dez compras legadas de 2020, com publicação ausente, fora do panorama
por publicação. Não preencher sua data com a data de declaração para fazer o
indicador aumentar. Esta integração não corrige o histórico por suposição.

**O conteúdo real de janeiro no PNCP direto ainda não foi validado neste plano.**

## 2. Contrato oficial e diferenças relevantes

Documentação OpenAPI consultada por GET em 2026-10-26:

- [API de consulta](https://pncp.gov.br/api/consulta/v3/api-docs).
- [API PNCP — operações de leitura e manutenção](https://pncp.gov.br/api/pncp/v3/api-docs).

Usar somente os GET públicos explicitamente permitidos abaixo. A segunda API
também documenta escrita e administração; **não** percorrer todas as operações,
usar credenciais de publicação ou seguir os links dos sistemas de origem.

| Finalidade | Base e rota GET documentadas |
| --- | --- |
| Modalidades | `https://pncp.gov.br/api/pncp/v1/modalidades` |
| Compras por publicação | `https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao` |
| Detalhe de compra, quando necessário | `https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}` |
| Itens | `https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens` |
| Quantidade de itens, para conferência | mesma base/compra, sufixo `/itens/quantidade` |
| Resultados de um item | mesma base/compra, sufixo `/itens/{numeroItem}/resultados` |

### Listagem

- Parâmetros: `dataInicial`/`dataFinal` em `yyyyMMdd`,
  `codigoModalidadeContratacao`, `codigoMunicipioIbge`, `uf`, `pagina` e
  `tamanhoPagina`. Datas da interface continuam em ISO e são convertidas no cliente.
- A listagem exige modalidade e página; o limite documentado é **50 registros
  por página**, mínimo 10. Não herdar o default 100 do cliente Compras.gov.br.
- Envelope `data`, com `totalRegistros`, `totalPaginas`, `numeroPagina` e
  `paginasRestantes`. HTTP 204 é uma resposta sem conteúdo, não JSON inválido.
- Listagem contém `numeroControlePNCP`, `anoCompra`, `sequencialCompra`,
  `orgaoEntidade.cnpj`, `orgaoEntidade.razaoSocial` e
  `unidadeOrgao.codigoIbge`/`codigoUnidade`, além de publicação e valores.
- `unidadeOrgao.codigoUnidade` **não é uma UASG**. Não cruzar esses códigos por
  igualdade textual com as unidades do Compras.gov.br.

### Filhos

- Itens e resultados retornam arrays, não o mesmo envelope da listagem.
- Itens têm `numeroItem`, `descricao`, `temResultado`, valores, unidade e
  `orcamentoSigiloso`; não pressupor `idCompra` ou `idCompraItem`.
- Resultados têm `numeroControlePNCPCompra`, `numeroItem`, `sequencialResultado`,
  fornecedor, valores e cancelamento em `dataCancelamento`.
- `tipoPessoa` admite **PF, PJ e PE**. Documento estrangeiro não é CPF/CNPJ.
- A rota de itens aceita paginação; a de resultados listados não documenta
  `pagina`. Não enviar parâmetros inventados ou presumir paginação idêntica.
- Detalhe de compra é um objeto. O parsing deve ser específico da operação,
  para não descartar objetos válidos nem interpretar um objeto de erro como compra.

A documentação confirma esses contratos, mas não prova o comportamento real de
paginação, acesso público, sigilo ou consistência entre páginas. Esses pontos
precisam de testes simulados e, posteriormente, verificação real autorizada.

## 3. Desenho técnico proposto

### 3.1 Cliente e orquestração

Criar um cliente/coletor PNCP separado do `FullCityCrawler` atual. Compartilhar
controle de parada, reserva de disco, throttling e persistência transacional;
não compartilhar cegamente parsing, autenticação ou regras de paginação.

Um orquestrador municipal executará as fontes selecionadas sequencialmente sob
o mesmo `writer.lock`, começando pelo PNCP direto. Cada fonte terá execução Ops,
estatísticas e erros identificáveis, agrupados pela execução gerenciada. Uma
falha recuperável em uma fonte não deve apagar nem impedir o aproveitamento da
outra; parada cooperativa e falta de disco continuam interrompendo o conjunto.

- Preservar até dois municípios simultâneos e **1 requisição/segundo global**,
  contando ambas as fontes e retries. Nenhum escritor concorrente por município.
- Usar hosts HTTPS fixos e caminhos validados. Não enviar `COMPRAS_GOV_TOKEN` ao
  PNCP, inclusive após 401/403; impedir redirecionamento para host não permitido.
- Aplicar timeout, retries limitados e `Retry-After`/cooldown compartilhado.
- Separar consultas por modalidade e por janelas de datas suportadas, sem
  lacunas; filtros solicitados não substituem validação do município retornado.
- Conferir paginação da listagem, páginas repetidas, término prematuro e limites.
  Para itens, validar término contra quantidade/páginas observadas; divergência
  ou variação não resolvida fica explícita, nunca recebe conclusão silenciosa.
- Consultar resultados quando `temResultado` for verdadeiro ou desconhecido.
  Falso permite registrar “sem resultado publicado segundo a fonte naquele
  instante”; não equivale a coleta completa de resultados históricos.
- Estimar custo pelo número de páginas, compras e itens com resultado. Não
  prometer duração fixa: o fanout de resultados pode dominar a execução.

### 3.2 Bronze e retomada

Manter **DuckDB Bronze + SQLite operacional** nesta entrega. Não condicionar a
nova fonte a Parquet, banco único ou à proposta UL-01, ainda não implementada.

- Guardar o payload da fonte sem inserir nele campos artificiais de parentagem.
- Nas novas páginas, guardar fonte, método GET, URL/path, parâmetros públicos,
  contexto do caminho, instante, status e hash, sem credenciais.
- Proposta de compatibilidade: metadados adicionais reservados no JSON de
  proveniência/parâmetros existente, separados dos parâmetros enviados à API.
  Não alterar a estrutura física do Bronze apenas para acrescentar a fonte.
- Namespaces de entidades/jobs distintos, por exemplo `pncp_direct_contratacao`,
  `pncp_direct_item_contratacao` e `pncp_direct_resultado_item`.
- Retomada identifica fonte, versão do contrato, coleção, host/rota, município,
  datas, modalidade, parentagem e paginação. Não reutilizar checkpoint de outra
  fonte, período ou limite sob um nome de job coincidente.
- Página e avanço do checkpoint continuam na mesma transação do Bronze.
  Replay da confirmação não duplica a página; nova coleta pode guardar outra
  observação de conteúdo idêntico. Não deduplicar o histórico por hash.
- Histórico sem URL/fonte explícita continua identificado como tal. Não
  preencher sua proveniência retroativamente por inferência de nomes de entidade.

### 3.3 Normalização, identidade e conciliação

Adaptar os novos formatos **na projeção reconstruível**, mantendo os originais
acessíveis. O payload mostrado como original deve continuar sendo o recebido.

| Entidade | Identidade/vínculo seguro proposto |
| --- | --- |
| Compra | `numeroControlePNCP`; validar coerência com CNPJ/ano/sequencial retornados |
| Item | controle da compra + `numeroItem` |
| Resultado | controle da compra + `numeroItem` + `sequencialResultado` |
| Fornecedor observado | tipo + documento completo compatível, quando disponível |

- Para filhos sem controle no corpo, o caminho **efetivamente requisitado**,
  registrado com seus parâmetros, pode provar parentagem a uma compra validada.
  Indicar essa evidência como derivada do endpoint, não como campo do payload.
- Parentagem do endpoint não sobrescreve controle, item ou município contraditório
  no corpo. Contradições ficam ambíguas, sem vínculo confirmado por conveniência.
- Não fabricar `idCompra`/`idCompraItem` para satisfazer a ficha atual. Ajustar a
  camada de vínculos para suportar a identidade composta do PNCP direto.
- Unificar compras presentes nas duas fontes apenas por controle PNCP explícito
  e aliases unívocos comprovados. Preservar as chaves atuais quando compatíveis.
  Não unir por objeto, número de processo, nome de órgão ou posição de registro.
- Tratar registros de fonte e entidades conciliadas como populações diferentes.
  Manter versões/origens das duas fontes consultáveis; a seleção da projeção
  não pode esconder conflito de identidade ou apagar evidências alternativas.
- Itens/resultados só são conciliados entre fontes quando as chaves compostas
  e os identificadores explícitos forem compatíveis e unívocos.
- Proposta de precedência: PNCP direto para os campos publicados pelo PNCP;
  Compras.gov.br como complemento de identificadores/cadastro com evidência.
  Expor divergências e a origem do valor selecionado, sem somar as duas versões
  ou montar silenciosamente um registro híbrido. Conflitos de identidade ou
  pertencimento ficam fora do consolidado. Divergências de cancelamento/exclusão
  sem versão autoritativa comprovada precisam de tratamento explícito, sem
  reativação automática de registros.
- Relógio de coleta e atualização da fonte permanecem distintos. Não chamar
  “mais recente na fonte” um registro escolhido apenas pelo instante de ingestão.
- Não recalcular o homologado da compra pela soma dos resultados, nem interpretar
  homologação como pagamento. Manter ausências, zeros, cancelamentos e sigilo.
- Código de catálogo só é interpretado com o sistema de catálogo identificado;
  códigos de outro catálogo não viram CATMAT/CATSER por semelhança.

### 3.4 Fornecedor e interface conectada

Reutilizar a ficha atual com campos de apresentação independentes do formato da
fonte. Exibir número do item, descrição, quantidades, valores, situação e as
evidências; permitir acessar o original e a proveniência de cada origem.

Fornecedor observado vem do resultado, inclusive quando não existe cadastro de
referência. O cadastro local só pode ser associado por documento completo e tipo
compatível. Não prometer cadastro SICAF para todo fornecedor do PNCP e não criar
nova consulta cadastral externa neste ciclo. Preservar máscara de CPF; PE e
identificadores incompletos permanecem distintos de identidades domésticas.

Manter paginação, contexto de retorno e token do snapshot; mudança de versão
continua retornando 409 em vez de misturar fontes/snapshots de momentos distintos.

### 3.5 Configuração e compatibilidade

Propor `collection_sources` com valores `comprasgov` e `pncp_direct`:

- Formulários novos enviam explicitamente as duas fontes por padrão; a API
  valida lista não vazia, sem fontes desconhecidas ou duplicadas.
- Configuração ausente em execuções antigas significa apenas Compras.gov.br.
  Retomada nunca transforma uma execução antiga em coleta da fonte nova.
- Novas agendas persistem sua escolha. Agendas antigas conservam Compras.gov.br,
  inclusive quando gerarem execuções futuras. Reativar agenda não muda fontes.
- Hoje agendas não têm esse campo: será necessária evolução **aditiva do controle
  SQLite**, com default legado e teste de idempotência. Isso é trabalho futuro,
  não uma migração executada durante o planejamento; Bronze/originais preservados.
- Expor capacidades no `/api/status`. Frontend novo em backend antigo mantém
  recursos atuais, avisa que a integração não está disponível e não envia campos
  que o backend antigo rejeita. Nenhum reinício automático para habilitar a fonte.
- Reutilizar o coletor na CLI por opção explícita, preservando os comandos atuais
  da CLI/TUI. Não redefinir `sync --source pncp`: esse seletor hoje se refere ao
  módulo PNCP **dentro do Compras.gov.br**. Documentar a diferença de nomes.
- O MCP configurado continua apontando para a base da raiz. Esta entrega não o
  redireciona às bases municipais nem promete unificação automática dos contextos.

### 3.6 Cobertura e apresentação do zero

Separar cobertura por **fonte, período e etapa**: listagem, itens e resultados.
Exibir conclusão, resposta vazia válida, não selecionado, não coletado,
indisponibilidade, erro/truncagem e dados anteriores preservados, conforme o caso.

- Não usar a nova fonte somente como fallback quando a antiga retorna zero:
  também há lacunas quando Compras.gov.br retorna algumas compras.
- Indicador descreve **compras consolidadas no snapshot**, não “total de compras
  existentes no município”. Zero local não comprova inexistência na cidade.
- Separar família de negócio (PNCP/legado) da origem de coleta
  (PNCP direto/Compras.gov.br). A contagem por fonte pode se sobrepor e não deve
  ser somada para obter o total conciliado.
- Detalhar o que veio de cada origem e o que foi conciliado/excluído. Não promover
  cobertura desconhecida de fontes antigas a “completa” por nova coleta parcial.
- Falha no Compras.gov.br, por exemplo OCDS, não apaga o PNCP bem-sucedido; a
  execução conjunta permanece parcial e a cobertura PNCP tem seu próprio estado.

## 4. Sequência de implementação

Todas as etapas abaixo são **planejadas**, não entregues:

| Etapa | Entrega | Arquivos/áreas previstos |
| --- | --- | --- |
| 1. Contrato e fixtures | Fixar formatos, domínio de modalidades, paginação/204 e casos de sigilo/cancelamento; exemplos sintéticos sem credenciais | documento de API PNCP e testes de cliente |
| 2. Coletor durável | Cliente PNCP, fanout, proveniência, retomada atômica e throttling compartilhado | novos módulos PNCP; `crawl_state.py`, testes de persistência |
| 3. Projeção e vínculos | Campos aninhados, identidades compostas, conciliação com duas origens e fornecedores observados | `web/analytics.py`, `web/exploration.py` e testes |
| 4. Operação e UI | Orquestrador, configuração persistida, agendas compatíveis, capacidades, cobertura por fonte e ficha | `web/worker.py`, `models.py`, `store.py`, `app.py`, frontend; opção explícita CLI |
| 5. Aceite sintético | Ponta a ponta com as duas fontes simuladas, testes existentes e build | fixtures, testes Python/Chromium e documentação |
| 6. Piloto autorizado | Rodar Brusque/janeiro, conferir páginas/origens, navegar e repetir sem duplicar indicadores | somente após autorização explícita de operação real |

O primeiro incremento de código deve ser o **cliente/coletor testado offline**,
sem ativar a fonte em serviços existentes. A primeira entrega funcional completa
somente termina após integração da projeção, operação e interface.

## 5. Critérios de aceite

### Automatizados, antes de usar bases reais

1. Caso “Brusque vazio no Compras.gov.br e presente no PNCP” produz compras,
   itens e resultados navegáveis, mesmo sem `idCompra` e `idCompraItem`.
2. Compra observada nas duas fontes entra uma vez no consolidado, com as duas
   origens acessíveis. Publicações com controles diferentes não são unidas por texto.
3. Item/resultado sem identificador estável ou com pai contraditório fica explícito;
   não vincular por nome, documento do fornecedor, valor ou posição.
4. Paginação de listagem/itens, arrays de resultados, objetos de detalhe,
   HTTP 204, respostas inválidas, 401/403, 429, timeouts e páginas repetidas cobertos.
5. Falha antes/depois da confirmação, replay e retomada não perdem nem duplicam
   páginas confirmadas. Checkpoints de fontes/escopos distintos não se confundem.
6. Sigilo, zero, ausência, cancelamento, PF/PJ/PE e cadastro ausente preservados.
   Nenhum token do Compras.gov.br chega ao PNCP ou aparece em logs/proveniência.
7. Uma fonte falha e a outra funciona: cobertura e resultado conjunto corretos,
   sem apagar dados anteriores ou declarar sucesso integral.
8. Novas coletas/agendas têm fontes explícitas; antigas e suas retomadas mantêm
   o escopo. Compatibilidade com backend anterior e schemas antigos verificada.
9. Limite global, parada, disco, exclusão municipal e publicação atômica preservados.
   Navegar pela UI não dispara consultas às fontes públicas.
10. Regressões: suíte Python, build TypeScript/Vite, testes Chromium e diff limpo.
    Referência anterior: 241 testes Python e 20 Chromium; não são prova da integração.

### Piloto real, depois de autorização separada

- Brusque, janeiro de 2026, todas as modalidades válidas; sem truncagens ou
  falhas definitivas da integração PNCP. Registrar instante, parâmetros e domínio.
- Conferir totais/páginas da fonte durante a execução, identidades aceitas,
  divergências e motivos de exclusão. Mudança da fonte entre páginas não deve
  ser escondida como reconciliação perfeita.
- Validar compra → item → resultado → fornecedor em registros disponíveis;
  ausência legítima de resultados/cadastro continua possível e sinalizada.
- Repetir a coleta guarda novo histórico, mas não duplica compras/itens/resultados
  conciliados. Demonstrar também retomada e os dois caminhos de proveniência.
- Resposta realmente vazia de janeiro não autoriza inventar registros ou mudar
  datas silenciosamente: registrar o bloqueio e acordar outro recorte, se necessário.
- O aceite desta fonte não substitui o aceite anterior de **todas** as áreas do
  full-city. Erros de OCDS ou outros módulos continuam visíveis e pendentes.

## 6. Fora do ciclo e limites de autorização

Sem contratos/atas/planejamento diretos do PNCP, portais privados, pagamentos,
comparação de preços, novos cadastros externos, expansão automática de municípios,
backfill amplo, migração Parquet, unificação CLI/web/MCP ou mudança de suas bases.

Nenhuma coleta de janeiro, retomada, alteração de agenda, migração de controle,
reinício de serviço, publicação ou commit é executado por este documento.
Implementação será autorizada separadamente; o piloto real exige autorização
adicional quando o código e os testes estiverem prontos.
