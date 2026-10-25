# Backlog supervisionado

Este arquivo é o modelo versionado, não autorização de implementação. Nenhum item
de produto foi aprovado nesta entrega de infraestrutura. WEB_PLAN é insumo
revisável; não copie sua lista inteira automaticamente para um ciclo.

Antes de aprovação, mantenha candidatos em artefato local fora do checkout
original. Atualize o backlog versionado somente numa lane com escopo autorizado;
não suje a origem para salvar propostas. Relacione o ID gerado por propose quando
houver pacote. Não confunda item priorizado com pacote aprovado.

## Modelo de item

- ID / título / demanda de origem:
- Estado: candidato | proposto | aprovado | em execução | bloqueado | ready |
  aceito | integrado | cancelado (resumo; status do controlador é a fonte operacional).
- Problema/valor esperado e comportamento atual:
- Evidências locais (arquivo:linha, revisão completa, log; distinguir hipóteses):
- Prioridade e justificativa (impacto, evidência/confiança, risco, esforço):
- Dependências e por que cabe num ciclo pequeno:
- In scope / out of scope (caminhos e comportamento):
- Critérios observáveis de aceitação:
- Reprodução sintética/offline e checks argv + timeout:
- Riscos e permissões protegidas solicitadas:
- Questões/decisões humanas pendentes:
- Cycle ID / pacote hash / base / lane / branch / dono exclusivo:
- Runs nativos reais, commits e caminhos de evidência:
- Resultado e limitações (não inferir aceite de um relatório):
- Próxima ação / responsável:

## Resumo de entrega por ciclo

Na lane, o escritor pode criar `docs/evolution/cycles/<id>/summary.md` quando o
pacote autorizar: objetivo, escopo executado, arquivos, critérios, checks de
trabalho, limitações e próximo passo. Commitar resumo e packet.json **antes** dos
checks finais. O SHA final, recibos, revisão e decisões humanas ficam no estado
local do controlador; não altere o HEAD revisado para acrescentá-los depois.
Uma consolidação versionada posterior precisa de escopo próprio autorizado.
