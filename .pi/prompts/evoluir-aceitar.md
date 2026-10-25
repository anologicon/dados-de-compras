---
description: Solicitar aceite humano da revisão exata e, separadamente, integração local
argument-hint: "<ID>"
---

Ciclo: $1. Leia integralmente `docs/evolution/README.md` e
`docs/evolution/decisions.md`. Só o coordenador chama comandos do controlador.

Consulte status ID e evidências no HEAD limpo exato: pacote/hash/base aprovados,
SHA completo, packet.json versionado aprovado, checks reais/logs com hashes,
relatório independente com runId real fora de todo o histórico dos escritores,
todos os critérios e riscos/limitações. Não trate ok nativo, exit zero,
proposta ou parecer como autorização. Se não ready (ou já accepted/integrated),
explique a fase e siga somente a transição válida, sem repetir trabalho.

Em ready, entreviste o operador: aceita expressamente esta revisão e seus limites?
Sem resposta humana afirmativa, pare. Registre referência não vazia à decisão com
`accept ID --approval TEXT`; aceite NÃO integra. Em accepted, apresente novamente
SHA aceito, base da origem e riscos; peça autorização SEPARADA para integração local
fast-forward. Só com essa resposta execute `integrate ID --approval TEXT`, com
referência à autorização humana separada. Se recusada/pendente,
retenha accepted sem integrar. Origem movida ou evidência stale: pare, sem rebase,
reset, merge alternativo ou alteração de aprovação. Nunca push, publicação, acesso
real ou limpeza. Registre decisões e resumo durável sem segredos; não modifique o
HEAD após checks/revisão/aceite. Mostre estado final e próximo passo humano.
