# Evolução supervisionada com Pi

Fluxo local em português: demanda → descoberta/backlog → proposta → aprovação
humana → lane isolada → commit/checks → revisão independente → aceite humano →
integração local autorizada separadamente. A entrega inicial é infraestrutura +
piloto sintético/offline, **não** evolução ou validação real de compras.

## Início rápido e confiança

Pré-requisitos já disponíveis: Git, Python 3.10+ (stdlib para o controlador), Pi e
pi-subagents compatível com workflows JS. Não instale dependências, inicie serviços
ou copie `.env`, credenciais ou dados para usar este fluxo. O checkout de origem
precisa estar limpo. Reveja os arquivos `.pi` antes de conceder confiança ao projeto;
sem confiança, prompts/perfis do projeto podem não carregar. Após alterações,
`/reload` recarrega recursos; não faça reload com trabalho ativo sem reconciliar
seus runs. Worktrees novas também precisam de confiança/discovery corretos.

No Pi, no repositório cuja origem deseja evoluir:

```text
/reload
/evoluir melhorar a clareza de uma mensagem com fixture sintética
/evoluir-status
/evoluir-executar ID
/evoluir-status ID
/evoluir-aceitar ID
```

Os quatro comandos são **prompt templates cooperativos**, não extensões nem
barreiras de segurança. Não se usa `/prompt-workflow evoluir`: o pai precisa manter
a coordenação e as decisões humanas. Não alteramos settings globais ou do projeto.
Confira via descoberta nativa os cinco nomes `evolution-*` abaixo; se faltarem,
pare em vez de usar silenciosamente outro perfil/runner/modelo. Configurações
pessoais podem sobrepor campos: verifique as capacidades efetivas após reload.

Worktree separa o diff, não permissões de host/rede. Bash de inspeção é um contrato
comportamental. Estado e run IDs são atestações, não autenticação; o pai confere a
proveniência real. Revisão/QA/proposta não autorizam execução, aceite ou integração.
O budget financeiro não é imposto. Para limites de segurança fortes, o operador
precisa fornecer isolamento externo; este fluxo não o implementa.

## Demanda, backlog e pacote

Leia [decisions.md](decisions.md), use [backlog.md](backlog.md) e o
[packet.example.json](packet.example.json). WEB_PLAN é entrada revisável, não uma
fila obrigatória nem autorização. Sem demanda específica, descubra no máximo cinco
candidatos locais; priorize impacto, evidência, risco e esforço, depois proponha um
ciclo pequeno. Rascunhos pré-aprovação ficam fora do checkout original, em artefato
local. Só numa lane aprovada são versionados backlog/resumos autorizados.

- **Evidência:** observação verificável com arquivo:linha/revisão/log; separe hipótese.
- **Escopo:** comportamento e caminhos permitidos; out_of_scope explicita exclusões.
- **Risco:** consequência/incerteza, não uma permissão implícita.
- **Aceitação:** resultado observável que precisa de prova para ser passed.
- **Reprodução:** caso sintético e passos para demonstrar comportamento/falha.
- **Check:** comando aprovado que produz log/exit/timeout; exit zero é necessário,
  mas não suficiente para provar todos os critérios.

Pacote JSON estrito, sem chaves extras: `title`, `objective` strings;
`evidence`, `in_scope`, `out_of_scope`, `acceptance` listas não vazias de strings não
vazias; `risks` lista de strings, pode ser vazia; `checks` lista não vazia de objetos
`{name, argv, timeout_seconds}` (argv é lista não vazia de strings, timeout inteiro
1..7200); `permissions` lista, pode ser vazia. Nunca inclua segredos. Listas não aceitam duplicatas, nomes de checks são únicos e o pacote canônico
cabe em 64 KiB. Comandos são **argv, não strings shell**. O operador revisa cada comando antes de aprovar.
Permissões possíveis: `real-data`, `live-collection`, `migration`,
`production-dependencies`, `new-source`, `publish`. Grants precisam ser o conjunto
exato solicitado, sem faltar nem sobrar. O piloto usa `permissions: []` e proíbe
rede, bases reais, `.env`, credenciais, serviços, instalações e publicação.

O check do exemplo só valida aritmética sintética, não o arquivo da nota: a revisão
precisa ler o conteúdo para provar o outro critério. Não execute o piloto de escrita
no checkout original; primeiro propose/approve/start e autorização explícita.

## Controlador: interface e ciclo completo

Somente o coordenador chama `python3 scripts/evolution.py --repo ROOT COMANDO` via
bash; ROOT é o caminho absoluto do **checkout original**, não o cwd do filho.
O script precisa existir na revisão instalada; se faltar, pare, não improvise outro
controlador. Saída JSON, erro não zero. Descubra caminhos pelo `status`, não assuma
nomes internos. Nunca edite estado/recibos manualmente.

Estado/locks/recibos/logs residem no Git common dir resolvido,
`evolution/cycles/<id>/`, compartilhado por worktrees, com salvamento atômico.
`status [ID]` recupera fase, caminhos, aprovação, contadores e evidências sem depender
do histórico do chat. Não há spawn, instalação, acesso a dados/API, stash/reset,
limpeza ou push automático.

Nos exemplos, ROOT, ID, FILE, RUN_ID e TEXT são metavariáveis; use valores reais,
quotados no shell quando necessário. Não execute todos os comandos em sequência
sem os gates humanos/nativos entre eles.

| Comando após `--repo ROOT` | Pré-condição e efeito |
| --- | --- |
| `status [ID]` | Inspeção e recuperação, sem redispatch. |
| `propose --packet FILE` | Valida e copia pacote canônico imutável; registra origem, branch e base; fase proposed. Sem código de produto alterado. |
| `approve ID --approval TEXT [--allow PERMISSION ...]` | Só após entrevista e resposta humana explícita, referência não vazia à decisão; origem limpa na mesma base e grants exatos. Congela hash/base; approved. |
| `start ID` | Exige aprovação válida, origem limpa/base atual e nenhum outro ciclo escritor não terminal. Cria lane persistente e branch evolution/<id>; running. Repetição recusa. |
| `assign ID --implementer RUN_ID [--reconciled]` | Registra identidade nativa real do escritor (ou parent:<session> real). Obrigatório antes de check/review. Trocar escritor exige --reconciled após confirmar término/posse anterior; invalida checks/review e preserva histórico de todos os escritores. |
| `pause ID --reason TEXT` | Depois de reconciliar/parar filho ativo, guarda bloqueio, fase anterior, lane e contadores. Não mata processo. |
| `resume ID` | Verifica pacote/aprovação/identidade da lane. Não faz spawn, não duplica worktree, não zera contadores. Bloqueio de revisão consome rodada corretiva e invalida checks/review antigos. |
| `cancel ID --approval TEXT` | Só decisão humana explícita e ciclo não terminal, após reconciliar/parar filhos. Marca cancelled e libera a faixa para outro ciclo; preserva worktree, branch, commits, logs e estado. Não é limpeza. |
| `check ID` | Só running, escritor atribuído, lane limpa/commitada e packet.json versionado idêntico ao aprovado. Executa exatamente checks aprovados no cwd da lane, grava logs com hashes e HEAD/hash exatos. Erro/timeout/setup ou mudança de HEAD/limpeza bloqueiam. |
| `review ID --report FILE` | Só running com checks passando no HEAD/pacote limpos atuais; copia relatório com hash. Independência, critérios e orçamento validados; pass sem pendências/P0/P1 → ready, senão blocked/review. |
| `accept ID --approval TEXT` | Só ready, evidências ainda válidas, revisão exata limpa e aceite humano explícito. Registra revisão aceita imutável; accepted. **Não integra.** |
| `integrate ID --approval TEXT` | Só após autorização humana separada para integração, referenciada em TEXT. Origem limpa na base aprovada e lane limpa na revisão aceita; fast-forward local. Confirma HEAD e marca integrated; não faz push/limpeza. |

`start` aloca fora da origem em
`ROOT.parent/worktrees/ROOT.name/<id>` e copia o pacote para
`docs/evolution/cycles/<id>/packet.json` na lane; o escritor o inclui no commit.
Não se copiam ambientes, dados ou dependências. Alocação incerta fica registrada e
bloqueada, nunca removida silenciosamente. A lane é persistente inclusive após pausa
ou fim da sessão. Não use a alocação efêmera `worktree:true` do pi-subagents aqui:
lance filho com cwd da lane e `worktree:false` explícito.

No primeiro controlador há uma lane persistente por ciclo. Para múltiplos
componentes, o coordenador precisa particionar caminhos/branches em worktrees
separadas, receber handoffs commitados e designar um único integrador; nunca dois
escritores no mesmo cwd. Esta interface não aloca automaticamente esse arranjo.

`check` persiste checking antes de executar, remove variáveis de credenciais e
PYTHONPATH externo e fixa PYTHONPATH em lane/src. Isso não é sandbox: um argv malicioso
ainda pode acessar o host/rede. Review/accept/integrate conferem também os hashes dos logs; evidência removida ou
alterada não pode ser reutilizada. Setup ausente, falha ou timeout bloqueia. Checking
interrompido exige pause/reconciliação explícitos antes de resume. Pausa de
infraestrutura/check retém contadores; pausa por revisão consome uma correção ao
resume. Resume do controlador **não** retoma um run Pi e vice-versa.

Integração recusa origem que avançou: não rebase/reset/override a base. Se houve
interrupção após fast-forward, o controlador pode reconhecer origem já na revisão
aceita e concluir idempotentemente. Não altere o HEAD depois de check/review/accept:
novos commits/diff invalidam evidências. Origem/lane divergente requer decisão humana.

## Time adaptativo e execução nativa

| Perfil folha | Quando usar / limite |
| --- | --- |
| evolution-product | Requisitos ambíguos, recorte e prioridade; leitura, sem autorização. |
| evolution-investigator | Comportamento/bug/evidência local; leitura, sem execução de checks. |
| evolution-implementer | Um escritor por cwd/caminhos aprovados; implementação, teste e commit local. |
| evolution-qa | Auditar reprodução/cobertura/recibos por critério; leitura, não aceite. |
| evolution-reviewer | Revisão final independente no HEAD exato; leitura, bash só para Git de inspeção. |

O pai é coordenador, nunca filho recursivo. Selecione só os papéis necessários;
um ajuste simples pode usar apenas escritor + revisor. Contexto fresh por padrão,
modelos herdados/configuráveis sem IDs fixados. Não impor budgets rígidos de
ferramentas a escritores; prefira escopo estreito e checkpoint seguro.

Cada execução coordenada usa exatamente **um workflow assíncrono de topo por fase**,
com `options: {globalConcurrencyLimit: 3, context: "fresh"}`. Não crie um segundo
workflow de topo enquanto o primeiro não estiver reconciliado. Lifecycle/checks
precisam do pai via bash **entre** fases; JS não lê estado do controlador, não tem
filesystem/shell e não chama host. Um único script não pode implementar esses gates.

Toda chamada runs.run/runs.all precisa de key única estável, label verbo+comportamento,
brief de cold start, output binding nativo e outputSchema com status/verdict
explícito. Aguarde/retorne o resultado e confira structuredOutput além de ok.
Não defina async:true no filho se precisa do resultado final. Outputs de leitura
são persistidos pelo runtime, sem dar write ao revisor. Retorne runId e referências
reais; paths citados em texto não substituem `output`. Copie evidências necessárias
para armazenamento durável antes da retenção nativa removê-las.

Workflows entregues (não fazem aprovação, escrita de fontes ou chamadas host):

- `.pi/workflows/evolution-discover.js`: args `{demand: "..."}`, um investigador,
  status completed|blocked e até cinco candidatos; o pai sintetiza proposta/backlog.
- `.pi/workflows/evolution-review.js`: args `{packetPath, checksPath, revision,
  acceptance}`; caminhos reais retornados por status, SHA completo e lista exata de
  critérios. Um revisor independente. Retorna status e `report` no formato do
  controlador, vinculando reviewer_run_id ao resultado nativo, não ao texto do agente.
  O pai ainda verifica proveniência, copia report para FILE fora do checkout e usa
  review. A cópia nativa do filho antecede essa vinculação; preserve também o retorno
  do workflow e o recibo. Nenhum retorno autoriza aceite.

Exemplo de chamada pelo pai (notação da ferramenta, não comando shell):

```js
subagent({
  workflow: ".pi/workflows/evolution-discover.js",
  cwd: "/caminho/absoluto/do/repositorio",
  args: { demand: "Investigar uma mensagem com entradas sintéticas" },
  async: true,
  options: { globalConcurrencyLimit: 3, context: "fresh" }
});
```

Para fase escritora, o pai monta um workflow curto com `await runs.run`, perfil
evolution-implementer, key estável por tentativa (`implement-0`, `correct-1`,
`correct-2`), label, cwd absoluto da lane, worktree:false, output nativo e schema
com status completed|blocked, SHA, caminhos/checks/limitações. Inclua pacote congelado,
aprovação, base, caminhos exclusivos e critérios no brief. Para não confundir
aceitação nativa com a do ciclo, pode explicitar no item
`acceptance: {level: "none", reason: "Gates de commit/check/review/aceite pertencem ao controlador; relatório do escritor é evidência."}`.
Isso desliga gates **nativos**, não os do controlador; confira o status estruturado,
diff real e no-staged-files, atribua o runId real retornado e só então check/review.
Se usar checked nativo, siga também seu acceptance-report e verifique a política
report/outputSchema da versão instalada; isso não substitui review do controlador.

O pai aguarda conclusão nativa antes de trabalho dependente, registra `assign` com
o runId do **filho escritor**, não o do workflow, e verifica se o revisor é outra
execução que não pertence a **nenhuma** identidade do histórico de escritores.
Ao trocar escritor, use assign com --reconciled só depois de confirmar término/posse
do anterior; a reatribuição invalida checks/review existentes. IDs em JSON não provam a independência por
si sós. Use `subagent({action:"status", id: RUN_ID})` para inspeção dos runs reais.

## Relatório de revisão e limite de correção

Formato JSON aceito por review (valores abaixo são ilustrativos, não atestações):

```json
{
  "reviewer_run_id": "ID-NATIVO-REAL-DO-REVISOR",
  "revision": "SHA-COMPLETO-DO-HEAD-REVISADO",
  "verdict": "block",
  "findings": [
    {"severity": "P1", "evidence": "arquivo:linha; reprodução sintética", "summary": "Critério sem prova"}
  ],
  "acceptance": [
    {"criterion": "STRING EXATA DO PACOTE", "status": "pending", "evidence": "Log ausente no HEAD solicitado"}
  ]
}
```

Cada critério do pacote aparece **exatamente uma vez**, com passed|pending|failed e
evidência concreta. verdict é pass|block, severidade P0|P1|P2. Qualquer P0/P1,
critério não passed ou verdict block bloqueia; P2 deve ser documentado e pode não
bloquear. Não reduza a primeira revisão a “só bloqueadores”. QA é complementar.

Há uma revisão inicial e **no máximo duas revisões corretivas**: inicial →
correção 1/check/revisão → correção 2/check/revisão. Se ainda bloquear, pare e leve
ao operador. Resume não reinicia orçamento; criar outro ciclo não é atalho para
contornar o limite. Alteração de escopo exige nova decisão/proposta explícita.

## Recuperação, aceite e evidência durável

Use /evoluir-status antes de retomar. Compare estado do controlador, runs ativos,
cwd/branch/base/HEAD, diff parcial, checks e contadores. Nunca start de novo nem
redispare escritor às cegas. Falha de workflow/launch/modelo/ferramenta é bloqueio
de infraestrutura: capture erro exato e IDs/caminhos, confirme lane limpa ou
preserve diff parcial; reconcilie/pare filhos antes de pause. Para encerrar um ciclo
não terminal, peça decisão humana explícita e use `cancel ID --approval TEXT`:
worktree/branch/commits/logs ficam preservados. Cancelar não para filhos nem autoriza
limpeza; não cancele para contornar orçamento sem nova decisão de escopo. Sem retry automático,
fallback CLI/foreground ou troca de modelo/runner. Peça decisão antes de uma nova
tentativa explícita no protocolo; retome a lane existente sem apagar trabalho.
O runtime nativo pode retomar workflows após reload/reabrir sessão: isso não é nova
aprovação. Descubra runs já retomados antes de qualquer despacho manual; os JS
entregues são somente leitura. Não altere settings automaticamente para recuperação.

Em ready, apresente pacote/hash/base, SHA limpo, logs, revisão independente, critérios
e riscos. Pergunte **aceite desta revisão?** Só então accept com referência real à
resposta. Depois pergunte **autoriza integrar localmente?** Só então `integrate ID --approval TEXT`, referenciando essa segunda resposta.
A segunda decisão pode ser negada e o ciclo permanece accepted. Sem push/cleanup.
O controlador registra a autorização de integração; preserve também sua referência
humana real. A flag é atestação, não autenticação da decisão. Não confunda grant publish com
aceite/integração; publicação continua fora deste fluxo inicial.

Pacotes, resumos de entrega autorizados e esta configuração podem ser versionados;
logs/recibos/aprovações do ciclo ficam locais no common dir. Commitar resumos antes
dos checks finais. Não suje a origem nem mude o HEAD aceito para adicionar decisões.
Nunca inclua segredos ou bases reais em pacotes, briefs, relatórios ou args de JS
(args são persistidos pelo runtime). `.gitignore` libera apenas os nomes entregues
em .pi; settings, extensions, skills, outros perfis/prompts e runtime ficam privados.

## Gates de teste e limites da validação

O pacote precisa aprovar checks concretos antes de executar. Para evolução de código:

1. Check focado sintético do comportamento/bug e casos negativos.
2. Regressão Python completa (`python -m pytest -q`) com intérprete aprovado e
   dependências **já disponíveis**, sem importar acidentalmente src da origem.
3. Quando tocar web/frontend/contrato relevante, build e Playwright sintéticos
   (`npm --prefix frontend run build`, `npm --prefix frontend run test:e2e`), se
   tooling/browser já disponíveis e execução explicitamente aprovada no pacote.
   Playwright pode iniciar servidor local de teste: é gate condicional, não faz
   parte do piloto sem serviços; aprovar essa execução offline separadamente no
   escopo/checks. Não baixar browser/dependências nem iniciar serviço real.

`.venv` e node_modules ignorados não aparecem automaticamente na lane. Use caminho
explícito aprovado para intérprete/ferramenta já existente; PYTHONPATH deve apontar
para lane/src (o controlador o fixa). Não trate `npm ci`, instalação de browser,
coleta live ou acesso à base Bronze como setup implícito. Gate indisponível é
blocked/pending, não pass. Saídas geradas devem estar ignoradas; não commitá-las
automaticamente. Não acrescente checks novos após aprovação congelada.

O piloto do controlador usa repositórios Git temporários e atestações falsas locais
identificadas como sintéticas: recusa pré-aprovação, grants/limpeza/base/pacote,
worktree/restart/concorrência, falhas/timeouts, HEAD dirty/stale, identidades,
pendências, duas correções, aceite separado da integração, origem movida e conclusão
idempotente. Isso valida encanamento determinístico, **não** obediência de LLM,
autenticação de aprovação, isolamento host/rede, dados de compras ou aceitação live.

Para esta interface: validar discovery/parser nativo de perfis/prompts, estrutura
Markdown/JSON, ignore seletivo e parser nativo de workflow sem lançar filhos.
`subagent({action:"validate", workflow:".pi/workflows/evolution-review.js", cwd: ROOT})`
valida sintaxe/estrutura estaticamente decidíveis, não funcionalidade do agente.
Um smoke LLM somente leitura é gate separado e só é cabível se chamadas ao provedor
forem explicitamente permitidas; não foi executado nesta lane sem APIs. Testes de
controlador/regressões pertencem à lane de controlador e à integração; não alegue
resultado deles a partir de validação documental. Nenhuma validação aqui atesta
compras reais ou atende a pendência de coleta live descrita em WEB_PLAN.
