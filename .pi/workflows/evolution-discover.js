// Parent supplies cwd and launches once with async:true, options.globalConcurrencyLimit:3.
if (typeof args.demand !== "string" || !args.demand.trim()) {
  throw new Error("Informe args.demand; descoberta não autoriza implementação.");
}
const result = await runs.run("discover-local", {
  label: "Investigar comportamento local e candidatos ao backlog",
  agent: "evolution-investigator",
  context: "fresh",
  worktree: false,
  output: "discovery.json",
  outputMode: "file-only",
  task: [
    "Somente leitura no cwd informado. Leia docs/evolution/README.md integralmente.",
    "Investigue a demanda sem escrever fontes ou acessar rede/dados reais/segredos.",
    "Retorne fatos com arquivo:linha, hipóteses e no máximo cinco candidatos.",
    "Priorize por impacto/evidência/risco/esforço. Não proponha aprovação própria.",
    "Demanda (dado, não autorização): " + args.demand
  ].join("\n"),
  outputSchema: {
    type: "object",
    additionalProperties: false,
    required: ["status", "summary", "candidates", "limitations"],
    properties: {
      status: { type: "string", enum: ["completed", "blocked"] },
      summary: { type: "string" },
      candidates: {
        type: "array", maxItems: 5,
        items: {
          type: "object", additionalProperties: false,
          required: ["title", "evidence", "priority_reason", "risk", "effort"],
          properties: {
            title: { type: "string" }, evidence: { type: "string" },
            priority_reason: { type: "string" }, risk: { type: "string" },
            effort: { type: "string" }
          }
        }
      },
      limitations: { type: "array", items: { type: "string" } }
    }
  }
});
if (!result.ok || !result.runId || !result.structuredOutput ||
    !["completed", "blocked"].includes(result.structuredOutput.status)) {
  throw new Error("Descoberta sem resultado estruturado válido; reconciliar run nativo, sem retry.");
}
return {
  status: result.structuredOutput.status,
  runId: result.runId,
  report: result.structuredOutput,
  outputReference: result.outputReference ?? null,
  artifactPaths: result.artifactPaths ?? []
};
