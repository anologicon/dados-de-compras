# Decisões de política aprovadas

Estas são as regras da entrega inicial supervisionada, não aprovação de um futuro
pacote de produto. Decisões específicas de ciclo exigem entrevista humana e ficam
nos recibos locais do controlador com referência à resposta real, nunca texto
inventado por agente.

| Decisão | Política |
| --- | --- |
| Entrega inicial | Fluxo reutilizável + piloto inteiramente sintético/offline; não evolução do produto. |
| Autoridade | Pai coordena, sintetiza e registra decisões. Propostas, backlog, QA e revisão são evidência, não autorização. |
| Escopo | Nenhuma escrita de fontes antes da aprovação exata de pacote/base/hash/checks/permissões. WEB_PLAN é entrada revisável. |
| Time | Até cinco papéis folha, escolhidos adaptativamente; no máximo três filhos simultâneos; fresh por padrão, sem filhos de filhos. |
| Escrita | Lane persistente externa ao checkout original, cwd/branch e caminhos exclusivos; múltiplos componentes exigem lanes separadas e um dono de integração. |
| Modelos | Herdados/configuráveis por execução, sem IDs de provedor fixados; sem fallback ou retry automático após falha de infraestrutura. |
| Revisão | Inicial + até duas revisões corretivas. Revisor não pode pertencer a nenhuma identidade do histórico de escritores; QA não o substitui. Pendência ou P0/P1 bloqueia; reatribuição reconciliada invalida checks/review. |
| Riscos protegidos | real-data, live-collection, migration, production-dependencies, new-source, publish exigem solicitação explícita e grants exatos. O piloto não usa nenhum. |
| Aceite | Pedido para implementar não concede aceite. Operador aceita revisão exata após evidência; integração local exige decisão separada. |
| Integração | Somente fast-forward local, origem limpa na base aprovada; integrate --approval registra autorização humana separada do aceite. Sem push, publicação ou limpeza automática. |
| Cancelamento | cancel --approval só após decisão humana e reconciliação/parada de filhos; preserva toda a lane/branch/commits/logs, sem limpeza. |
| Persistência | Configuração/modelos de docs e resumos autorizados versionados; estado, recibos e logs locais no Git common dir. Sem segredos em nenhum relatório. |
| Confiança | Prompts cooperativos, não sandbox nem autenticação. Worktree não isola host/rede; budget financeiro não é imposto. |

## Registro humano de ciclo (modelo de referência local)

- ID, SHA completo do pacote, base/revisão completa e data:
- Pergunta exibida ao operador (incluindo argv, riscos e permissões):
- Resposta explícita e referência à mensagem/entrevista real:
- Aprovação de escopo + grants exatos:
- Aceite da revisão exata (decisão distinta):
- Permissão para integrar localmente (decisão distinta):
- Estado resultante, recibos e limitações:

Não grave esse registro alterando manualmente os arquivos de estado; use
approve/accept/integrate/cancel com --approval e preserve referências às decisões
humanas reais como evidência local do coordenador. Não edite o commit após checagem/revisão para anexar decisões tardias.
