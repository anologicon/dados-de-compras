# Resumo documental — evo-b42e05820fce

## Entrega

Proposta não implementada em `docs/evolution/unified-storage-contract.md`, com
referências de código conferidas por leitura estática na base
`ef8a7fff9cb5f22ac6d0f4f9f2e9b0ed979a23e3`. O `packet.json` copiado pelo start
é incluído sem alteração. `permissions=[]`; nenhuma decisão arquitetural é tomada.

## Cobertura documental dos critérios do pacote

1. Seção 1: mapa CLI/sync/full-city/web/MCP, argumentos, persistência e leituras;
   fatos separados de inferências e propostas não implementadas.
2. Seção 1.1 e caso `caminhos-explicitos`: prefixo sync, Bronze/Ops derivados,
   default distinto de ProjectAccess e seleção explícita sem mudar defaults.
3. Seção 2: páginas, observações históricas, última identidade, compras
   conciliadas, precedência por existência de `silver_records` e Silver/Gold
   consolidadas a definir; `records`/`purchases` não são camadas aprovadas.
4. Seções 3 e 5.1: duas novas observações PNCP, mesma identidade `sintetica-1`,
   runs `a`/`b`, payloads distintos, instantes ISO crescentes e proveniência;
   expectativas 2/1/`b`, replay distinto de nova observação e sem deduplicar
   histórico por hash. Não estende a expectativa a compras conciliadas.
5. Seções 5.2–5.3: caminhos apenas ilustrativos; Ops explícito; caso de Bronze
   inexistente específico de `ProjectAccess.list_entities`, com erro antes da
   abertura e sem criação de arquivos, distinto de `get_project_info`.
6. Seções 2.4, 4 e 6: recorte de coleta separado de pertencimento municipal;
   cinco decisões pendentes, alternativas/consequências, compatibilidade e
   candidatos posteriores com dependências, sem autorizar execução ou migração.
7. Seção 5.4: exatamente um bloco JSON pedagógico, com as chaves e expectativas
   congeladas. Entrega limitada aos três documentos autorizados do ciclo.
   Passagem nos checks e revisão semântica independente ainda não atestadas.

## Validação e limitações

O escritor realizou apenas leitura de documentação/fontes e inspeção Git, além
da escrita documental e commit local autorizado. Estado inicial conferido:
cwd/branch/base do handoff, com somente o packet copiado não rastreado.

**Nenhum check documental foi executado pelo escritor.** Ficam reservados ao
pai/controlador, no HEAD limpo e commitado, exatamente os checks congelados:

- `ul01-conteudo-da-especificacao`;
- `ul01-diff-documental-sem-erros`;
- `ul01-caminhos-exclusivos-do-ciclo`.

Os três cenários são especificações **não executadas**: sem fixtures reais,
software do projeto, pytest, transportes MCP ou serviços. Caminhos ilustrativos
não foram abertos/criados. Não houve acesso a bases existentes, credenciais,
rede, instalação, coleta ou migração. Não se reproduziram os candidatos de
checkpoint sync por `job.name` ou extração CSV; são inferências de código.

Riscos remanescentes: estrutura JSON/diff não prova runtime, toda a semântica do
contrato ou segurança de concorrência. Layout físico, backend, ID portátil,
visões e precedência legada permanecem pendentes; Parquet/DuckDB único não foram
adotados. Não há recibo de checks, revisão, aceite ou integração nesta entrega.

## Próximo passo

Pai confere revisão/árvore limpa, atribui a identidade nativa real do escritor,
executa os checks pelo controlador e solicita revisão semântica independente por
critério no mesmo HEAD. Aceite humano e eventual integração exigem decisões
posteriores distintas; esta entrega não os concede.
