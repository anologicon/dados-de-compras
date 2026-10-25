// Advisory only. Parent checks controller receipts BEFORE this read-only launch.
if (typeof args.packetPath !== "string" || !args.packetPath.trim() ||
    typeof args.checksPath !== "string" || !args.checksPath.trim() ||
    typeof args.revision !== "string" || !/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(args.revision) ||
    !Array.isArray(args.acceptance) || !args.acceptance.length ||
    args.acceptance.some(item => typeof item !== "string" || !item.trim()) ||
    new Set(args.acceptance).size !== args.acceptance.length) {
  throw new Error("Informe packetPath, checksPath, revision completo e acceptance exata sem duplicatas.");
}
const result = await runs.run("review-independent", {
  label: "Revisar independentemente escopo e evidências do HEAD",
  agent: "evolution-reviewer",
  context: "fresh",
  worktree: false,
  output: "review.json",
  outputMode: "file-only",
  task: [
    "Somente leitura. Leia docs/evolution/README.md e os arquivos abaixo integralmente.",
    "Confirme HEAD limpo igual à revisão e checks correspondentes; não execute checks.",
    "Sem evidência suficiente, retorne block e critérios pending/failed; não invente IDs.",
    "Pacote: " + args.packetPath,
    "Recibos/logs dos checks: " + args.checksPath,
    "Revisão: " + args.revision,
    "Critérios exatos: " + JSON.stringify(args.acceptance)
  ].join("\n"),
  outputSchema: {
    type: "object", additionalProperties: false,
    required: ["revision", "verdict", "findings", "acceptance"],
    properties: {
      revision: { type: "string" },
      verdict: { type: "string", enum: ["pass", "block"] },
      findings: {
        type: "array", items: {
          type: "object", additionalProperties: false,
          required: ["severity", "evidence", "summary"],
          properties: {
            severity: { type: "string", enum: ["P0", "P1", "P2"] },
            evidence: { type: "string", minLength: 1 },
            summary: { type: "string", minLength: 1 }
          }
        }
      },
      acceptance: {
        type: "array", items: {
          type: "object", additionalProperties: false,
          required: ["criterion", "status", "evidence"],
          properties: {
            criterion: { type: "string", enum: args.acceptance },
            status: { type: "string", enum: ["passed", "pending", "failed"] },
            evidence: { type: "string", minLength: 1 }
          }
        }
      }
    }
  }
});
const report = result.structuredOutput;
if (!result.ok || !result.runId || !report || report.revision !== args.revision ||
    !["pass", "block"].includes(report.verdict) ||
    !Array.isArray(report.findings) || !Array.isArray(report.acceptance) ||
    report.acceptance.length !== args.acceptance.length ||
    args.acceptance.some(criterion => report.acceptance.filter(row => row.criterion === criterion).length !== 1)) {
  throw new Error("Revisão sem evidência estruturada exata; reconciliar run nativo, sem retry.");
}
const blocked = report.verdict === "block" ||
  report.findings.some(item => item.severity === "P0" || item.severity === "P1") ||
  report.acceptance.some(item => item.status !== "passed");
return {
  status: blocked ? "blocked" : "completed",
  report: { ...report, reviewer_run_id: result.runId, verdict: blocked ? "block" : "pass" },
  outputReference: result.outputReference ?? null,
  artifactPaths: result.artifactPaths ?? []
};
