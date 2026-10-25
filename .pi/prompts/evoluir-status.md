---
description: Recuperar estado do ciclo e runs nativos sem relançar trabalho
argument-hint: "[ID]"
---

Leia integralmente `docs/evolution/README.md`. Consulte somente `status` ou
`status ID` do controlador para: $@
Recupere pacote/hash/base, aprovação, fase, lane/cwd/branch/HEAD, escritor, contadores,
checks e revisão; use os caminhos retornados, não presuma nomes de arquivos internos.
Confira status dos runs nativos reais conhecidos, inclusive possíveis filhos ainda
vivos após reload. IDs declarados num relatório não autenticam proveniência.

Resuma fato verificado, evidência ausente, limites e próximo comando permitido.
Compare controller e runtime: `pause/resume` do controlador não para/retoma agente.
Checking interrompido exige reconciliação explícita e pause antes de resume.
Se cancelled, informe que o ciclo terminou mas worktree/branch/artefatos continuam
preservados; isso não prova que filhos foram parados nem autoriza retomada/limpeza.
Se o operador quiser abandonar um ciclo não terminal, apresente como próximo passo
reconciliar/parar filhos e obter decisão humana explícita antes de o coordenador
usar `cancel ID --approval TEXT`. Este comando de status não cancela por si só.
Não escreva fontes/estado manualmente, não faça start/resume/assign/check, não
relance workflow ou filho automaticamente, não limpe worktrees nem aceite trabalho.
Se houver divergência ou dono desconhecido, marque pendência e peça decisão humana.
