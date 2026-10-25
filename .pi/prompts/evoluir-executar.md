---
description: Executar pacote aprovado em lane isolada, checar e revisar até ready
argument-hint: "<ID>"
---

Ciclo solicitado: $1. Argumentos adicionais: ${@:2}
Atue apenas como coordenador, seguindo integralmente `docs/evolution/README.md`
e `docs/evolution/decisions.md`. Falta ID ou diverge contrato/CLI? Pare e esclareça.

1. Consulte `status ID`, pacote imutável, base/hash, permissões, cwd/branch e runs
   nativos. Mostre objetivo, limites, todos os argv de checks e riscos ao operador.
   Se proposed, entreviste explicitamente para aprovação do escopo/base/hash e
   permissões exatas. Só a resposta humana autoriza `approve ID --approval TEXT`
   com `--allow` para cada permissão solicitada. Não fabrique referência de decisão.
2. Se approved e preflight válido, use `start ID` uma única vez. Se já iniciado,
   reconcilie lane/run; nunca chame start de novo ou redispare escritor às cegas.
   Não escreva no checkout original nem copie .env, dados ou dependências.
3. Dispare um implementador nativo na lane persistente retornada, `worktree:false`
   explícito (não alocar worktree gerenciada/efêmera). Cwd absoluto, posse exclusiva,
   pacote, base, critérios e limites no handoff. Um workflow de topo assíncrono por
   fase, concorrência global 3, fresh, key estável, label verbo+comportamento,
   output nativo e status estruturado completed|blocked. Aguarde resultado real;
   não use async:true no filho quando precisa do resultado. Registre identidade
   real com `assign ID --implementer RUN_ID` antes de check/review, atualizando-a
   após escritor corretivo. Troca de identidade exige `--reconciled` somente após
   confirmar término/posse do escritor anterior; invalida checks/review e mantém
   histórico de todos os escritores. Pai escritor usa parent:<session> real.
4. Confira SHA, diff, commit e ausência de staged/dirty; execute `check ID` somente
   via controlador, exatamente checks aprovados. QA opcional audita recibos, não
   concede aceite. No HEAD limpo com checks válidos, lance revisor independente
   fresh somente leitura (evolution-review.js opcional). Confira structuredOutput,
   revisor fora de todo o histórico de escritores, cada critério exato e
   proveniência; copie relatório
   durável e envie `review ID --report FILE`.
5. Revisão inicial + até duas rodadas corretivas, nunca resetar orçamento. Em block,
   reconcilie/pare filhos antes de `resume ID`; só bloqueio de revisão consome rodada
   corretiva. Repita escritor/check/revisão na mesma lane, sem ampliar pacote.
   Limite esgotado, dúvida, check falho ou infraestrutura: preserve tudo, registre
   `pause ID --reason TEXT` quando cabível e reporte. Cancelamento exige decisão
   humana explícita e `cancel ID --approval TEXT`, só após reconciliar/parar filhos;
   preserva worktree/branch/commits/logs. Sem retry/fallback/limpeza automáticos.
6. Pare em ready e mostre evidências e limitações. Implementar não autoriza aceitar
   ou integrar: encaminhe para /evoluir-aceitar ID. Sem push, limpeza ou publicação.
