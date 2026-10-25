---
description: Descobrir demanda e propor ciclo com backlog priorizado, sem implementação
argument-hint: "[demanda]"
---

Atue como coordenador do fluxo supervisionado. Leia integralmente
`docs/evolution/README.md`, `docs/evolution/decisions.md` e o backlog existente.
Demanda: $@

1. Recupere `status` do controlador e runs nativos antes de abrir outro trabalho.
   Se não houver demanda, faça descoberta local limitada, usando WEB_PLAN apenas
   como insumo revisável. Sem fontes escritas, rede, bases reais ou segredos.
2. Escolha o menor time adaptativo: investigador; produto só se precisar delimitar
   valor/escopo. No máximo três filhos simultâneos, folhas sem delegação, contexto
   fresh. Use exatamente um workflow assíncrono de topo por fase coordenada com
   `options.globalConcurrencyLimit: 3`, labels verbo+comportamento, keys estáveis e
   outputs nativos. O JS evolution-discover.js é opcional. Confira structuredOutput,
   não apenas ok. Não relance após falha de infraestrutura.
3. Sintetize até cinco candidatos no modelo de backlog, priorizados por impacto,
   evidência, risco e esforço. Diferencie fatos/hipóteses, critérios e checks.
   Mostre o pacote proposto e permissões protegidas. Pergunte o necessário.
4. Salve proposta fora do checkout original e, se suficientemente definida, use
   somente `propose --packet FILE`; isso não aprova nem inicia escrita. Sem mudança
   de código ou WEB_PLAN. Backlog/rascunhos pré-aprovação ficam em artefato local;
   versionamento só numa lane autorizada. Termine com ID, evidências e próxima
   decisão humana. Nunca aprove a própria proposta ou inicie implementação aqui.
