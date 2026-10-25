# Pipeline lake local — plano e acompanhamento

## Revisão atual aprovada — ingestão e Bronze

Esta seção orienta a próxima implementação. As seções posteriores registram a primeira entrega da interface e seus requisitos anteriores. A prioridade agora é operar a ingestão e enxergar a Bronze chegando; modelagem de camadas derivadas fica fora desta revisão.

### Armazenamento e histórico

- A Bronze principal do fluxo gerenciado passa a ser **Parquet local, bruto e imutável**, preservando payloads e metadados de origem, execução, requisição, paginação, hash e instante de coleta.
- Manter a granularidade bruta de resposta/página já utilizada; a interface pode apresentar os registros contidos no JSON sem aplicar regras de negócio à ingestão.
- Converter também a Bronze já importada para a área gerenciada. Não importar automaticamente as outras bases do repositório e não sobrescrever nem apagar os bancos/arquivos originais.
- A conversão deve preservar as ocorrências históricas e ser idempotente. Repetir uma migração ou confirmar novamente a mesma página/lote não cria outra observação; uma nova coleta pode registrar uma nova observação, inclusive de um payload inalterado.
- Arquivos em escrita não ficam disponíveis para consulta. Arquivos concluídos são publicados mediante um manifesto/registro consistente, associado aos checkpoints; a retomada não pode pular dados ainda não confirmados.
- Fazer a transição com exclusão de escrita nos municípios afetados, preservando fila, agendas e o histórico operacional. Manter compatibilidade dos comandos existentes da CLI/TUI.

### Acompanhamento e interface

- **Tela principal: painel do pipeline**, não o panorama de compras. Mostrar coletas, fontes/etapas, páginas, registros recebidos e confirmados, arquivos, falhas, retries e acesso à Bronze.
- Atualizar eventos e contadores a cada **2 segundos**.
- Publicar lotes de Bronze em janelas de até **30 segundos**, também ao concluir a coleta ou executar uma parada cooperativa segura. Atrasos de gravação/falhas devem aparecer, nunca ser apresentados como confirmação bem-sucedida.
- Diferenciar dados recebidos de dados efetivamente confirmados em Parquet. Não apresentar uma contagem de observações brutas como quantidade de compras únicas.
- Permitir prévia dos registros confirmados e exploração paginada da Bronze **durante a coleta**, com filtros, JSON original e proveniência; não depender da projeção analítica publicada ao término.
- Preservar exportações CSV/JSON do resultado filtrado completo e a distinção entre ausência de dados, falta de cobertura e zero.
- As análises existentes ficam secundárias; sua ampliação não faz parte desta revisão.

### Pesquisa do município

- Pesquisar pelo nome e UF, usando o catálogo oficial do IBGE; preencher o código a partir da opção selecionada, sem exigir digitação manual.
- Manter catálogo oficial em cache persistente. Na indisponibilidade do IBGE, pesquisar o catálogo salvo; sem resultado confirmado, informar a indisponibilidade e aguardar nova tentativa.
- Não permitir cadastro manual não verificado como fallback. Municípios já cadastrados continuam operacionais.
- A consulta cadastral ao IBGE não autoriza complementação automática dos dados de compras por outras APIs.

### Página contextual de consulta e fontes — escopo aprovado

- Criar uma página de orientação para **consultar os dados locais e suas fontes oficiais**, adaptada ao município selecionado e ao workspace configurado.
- Explicar o percurso API → Bronze, a granularidade de resposta/página, os formatos, os bancos/arquivos e seus caminhos reais. Distinguir dados brutos, controle operacional, catálogo cadastral IBGE e projeções existentes.
- Documentar o armazenamento efetivamente implementado: hoje DuckDB/SQLite; Parquet deve aparecer como planejado enquanto a migração não existir. Não apresentar arquivos, tabelas ou cobertura inexistentes como disponíveis.
- Mostrar entidades disponíveis, campos/metadados de proveniência, referências oficiais e exemplos copiáveis de SQL, Python e requisições às fontes. Os exemplos locais são de leitura, sem console SQL embutido ou execução de código pela página.
- A página deve funcionar também sem município cadastrado, sem primeira coleta e sem snapshot: nesses casos, oferecer orientação geral e explicitar a ausência dos dados contextuais.
- Não consultar automaticamente APIs externas ao abrir a página. Links e exemplos permitem que a pessoa faça a consulta quando desejar; uma resposta atual da API não é uma reprodução garantida do conteúdo histórico guardado.
- Nas novas coletas, persistir endpoint solicitado, método HTTP e parâmetros não sensíveis, aproveitando a informação já conhecida pelo cliente. Preservar payloads e compatibilidade de ingestão/retomada, sem exigir uma migração Parquet nesta entrega.
- Para dados antigos sem URL registrada, indicar a lacuna. Referências do catálogo não devem ser apresentadas como prova da requisição histórica, nem preencher a origem por inferência silenciosa.
- Não mostrar/copiar tokens, senhas, cabeçalhos de autorização ou outros segredos. Validar links e escapar os valores usados nos exemplos copiáveis.
- Orientar leitura segura dos bancos: não recomendar cópia de arquivo DuckDB em gravação; explicitar conflitos entre leitores/escritores de processos distintos. Não abrir o Bronze em disputa com um worker só para gerar a documentação; indicar limitações ou usar metadados já publicados com a referência temporal correta.
- Explicar que a pasta de um município identifica o escopo da coleta, não prova que todo registro bruto é municipal: consultas auxiliares podem trazer conteúdo estadual/nacional. Contagens de páginas/observações não equivalem a compras únicas, e ausência de dados não significa zero.
- Aceite da página: testes dos contextos com/sem dados e durante coleta, exemplos locais validados com a base importada, registro da origem em novas páginas, histórico sem origem explícita, ausência de credenciais nos exemplos/links e regressões da CLI/TUI. Abrir a página não deve fazer novas requisições às fontes oficiais.
- Não bloqueantes: título final (proposta: **Como consultar os dados**), posição exata na navegação e organização visual das seções.

### Operação e aceite

- Permanecem localhost, serviço manual, fila/agendas persistentes, até dois municípios simultâneos, exclusão por município, limite global de uma requisição por segundo, parada cooperativa e proteção de disco.
- Testar falhas antes/depois da publicação do arquivo e do checkpoint, retomada, repetição da conversão, leitura durante ingestão e ausência de páginas parcialmente visíveis.
- Testar pesquisa/cadastro com IBGE simulado, cache offline, nomes ambíguos e indisponibilidade sem catálogo.
- Validar no navegador o painel operacional e a chegada de registros à Bronze antes do término de uma coleta simulada; preservar regressões da CLI/TUI.
- O aceite real de ingestão continua sendo Brusque/SC, **4202909**, de **2026-01-01 a 2026-01-31**, em todas as áreas públicas previstas, sem falhas definitivas ou truncagens. Indisponibilidade externa não equivale a aprovação.

### Entrega implementada nesta revisão — buscador IBGE

- Cadastro com seleção de UF e busca por nome/código, sem distinção de maiúsculas ou acentos; o usuário seleciona um resultado e o código é preenchido em campo somente leitura.
- Catálogo oficial obtido pelo backend em URL fixa, sem token de compras nem redirecionamentos; cache SQLite persistente, renovação após 30 dias e botão de atualização explícita.
- Backend rejeita códigos inexistentes e nomes/UFs divergentes do catálogo. Falhas preservam o último catálogo válido; sem cache, o cadastro novo é bloqueado, sem afetar municípios existentes.
- Trocar UF ou texto pesquisado invalida a seleção anterior; estados de pesquisa, resultado vazio, erro e cache indisponível são explícitos.
- Validação: **107 testes Python e 9 testes Chromium passando**, incluindo cadastro, homônimos/UF, cache offline, falhas de gravação e uso em celular. Build TypeScript concluído.
- Consulta real ao IBGE validada para Brusque/SC (**4202909**) e busca sem acentos de Florianópolis/SC (**4205407**); formulário também verificado no serviço local em execução, sem erros JavaScript.
- Esta entrega não implementa ainda a migração Parquet nem o novo painel do pipeline. O aceite real de coleta de compras de Brusque segue pendente; pesquisar o cadastro IBGE não equivale a executar a coleta.

### Detalhes não bloqueantes

Layout final das partições, limite de bytes por lote e acabamento visual. Devem respeitar isolamento por município, rastreabilidade, retenção e os intervalos de acompanhamento aprovados acima.

## Decisões aprovadas da primeira etapa

- FastAPI + React/TypeScript, localhost, usuário único, inicialização manual.
- Interface em português, desktop primeiro; manter CLI/TUI.
- Coleta somente `full-city`, qualquer município; bases isoladas.
- Fila e agendas persistentes: imediata, pontual, diária e semanal, no fuso configurado.
- Até dois municípios em paralelo, nunca duas coletas do mesmo município; pacing global de 1 req/s, inclusive retries.
- Parada cooperativa, retomada segura, recuperação após reinício e agrupamento de horários perdidos.
- Janela recorrente móvel (padrão: 90 dias); histórico anterior não é atualizado automaticamente.
- Importação explícita da base Bronze API inteira de Florianópolis, sem modificar o original.
- Panorama territorial por publicação; estimado/homologado/contratado separados, nunca chamados de gasto pago.
- Integração PNCP/legado somente por identificadores comprovados; ambiguidades fora do consolidado.
- Análises de compras, itens, fornecedores, contratos e preços; comparação assistida por catálogo/tipo/unidade/moeda.
- CSV e JSON filtrados, com proveniência e cobertura; não exportar apenas a página visível.
- Projeção imutável publicada ao fim da coleta; manter a atual e a anterior. Bronze preservado.
- Cobertura parcial explícita, proteção contra disco cheio; credenciais somente no backend.

## Entregas incrementais

1. Fundação: persistência, controle de execução, retomada correta, API local e frontend navegável.
2. Importação e projeções: panorama, compras e inspeção do Bronze com filtros e exportação.
3. Operação: workers isolados, agenda, parada/recuperação e limites globais.
4. Análise integrada: fornecedores, contratos, preços e conciliação estrita com legado.
5. Aceite: testes automatizados, fluxo web e coleta real completa.

Cada etapa deve registrar o que foi efetivamente testado. A existência de uma tela não equivale à conclusão de uma funcionalidade.

## Progresso da primeira entrega

Implementado:
- Backend opcional e UI navegável: panorama, compras, dados de origem, coletas e agendas.
- Importação não destrutiva, filtros, paginação, CSV/JSON completos e proveniência.
- Projeções reconstruíveis por município; publicação atômica, lease de execução e retenção atual/anterior.
- Fila SQLite, exclusão por município, workers isolados por processo e locks de workspace/escrita.
- Agenda com fuso explícito, recuperação agrupada, controle de parada e retomada.
- Pacing/cooldown entre processos; proteção de disco e limite de recuperação de crashes de workers.
- Retomada do full-city corrigida: página e estado na mesma transação; escopo inclui coleta, município, período e parâmetros.
- Erros/truncagens resultam em coleta parcial, não em sucesso silencioso; endpoints anuais cobrem todos os anos do período.
- Fronteira localhost/Host/Origin e header contra CSRF; campos extras de entrada rejeitados.

Validação local:
- Importadas 2.510 páginas da base API inteira de Florianópolis; 13.560 registros distintos por identidade e 1.440 compras no panorama.
- Originais abertos somente para leitura, sem sobrescrita. Cobertura importada explicitamente não verificada.
- Testes automatizados incluem falha entre página/checkpoint, reconsulta, parada, exclusão de escrita, fila, agendas/fuso, exportação, snapshots e fronteira HTTP.
- Testes Chromium com dados sintéticos: panorama/filtros/origem, fila/agendas e layout móvel básico.
- Resultado desta etapa: **89 testes Python + 3 testes de navegador passando**. Build TypeScript e wheel com HTML/JS/CSS também verificados.

Ainda pendente (não confundir com funcionalidade concluída):
- Telas/análises dedicadas de fornecedores, contratos e comparação assistida de preços.
- Validar e ampliar o mapeamento estrito do legado com amostras reais não vazias; lista dedicada dos não conciliados.
- Cobertura detalhada por área e período, incluindo distinção de dados antigos preservados em coletas parciais.
- Verificar todos os caminhos derivados do full-city contra a API real, especialmente consultas Id, contratos, OCDS e fontes auxiliares.
- Completar o aceite ponta a ponta com workers reais e a coleta estrita de Brusque abaixo. Nenhuma coleta real nova foi executada nesta primeira entrega.

## Aceite final (ainda pendente)

- Suíte existente da CLI/TUI preservada.
- Testes de retomada após falha entre gravação e checkpoint, escopos diferentes, reconsulta, deduplicação e cancelamento.
- Testes de fila, exclusão por município, limite global, agenda/fuso, recuperação e publicação de snapshots.
- Testes web de segurança local, filtros, exportações e navegação com dados locais.
- Coleta real: **Brusque/SC, IBGE 4202909, 2026-01-01 a 2026-01-31**.
- Todas as áreas públicas previstas concluídas, sem falhas definitivas ou truncagens; retries recuperados são permitidos.
- Registros reais visíveis em indicadores/exportação; repetir não pode duplicar os indicadores.
- Indisponibilidade externa pode bloquear o aceite: nunca declarar uma coleta parcial como aceite completo.
