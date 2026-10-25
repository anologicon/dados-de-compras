"""Configuration/recipe regression tests; no models, network or procurement data."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
AGENTS = {"product", "investigator", "implementer", "qa", "reviewer"}
PROMPTS = {"evoluir", "evoluir-executar", "evoluir-status", "evoluir-aceitar"}
WORKFLOWS = {"discover", "review"}
REVISION = "a" * 40


def test_leaf_profiles_and_prompts_are_explicit_and_model_portable():
    for role in AGENTS:
        content = (ROOT / f".pi/agents/evolution-{role}.md").read_text()
        assert content.startswith("---\n")
        header = content.split("---", 2)[1]
        fields = dict(line.split(":", 1) for line in header.splitlines() if ":" in line)
        assert fields["name"].strip() == f"evolution-{role}"
        assert fields["defaultContext"].strip() == "fresh"
        assert "model" not in fields
        assert "subagent" not in fields["tools"]
        assert fields["acceptanceRole"].strip() == ("writer" if role == "implementer" else "read-only")
    for prompt in PROMPTS:
        content = (ROOT / f".pi/prompts/{prompt}.md").read_text()
        assert content.startswith("---\n")
        assert "description:" in content.split("---", 2)[1]
        assert "docs/evolution/" in content


def test_only_exact_delivered_pi_files_are_unignored(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
    public = [f".pi/agents/evolution-{r}.md" for r in AGENTS]
    public += [f".pi/prompts/{p}.md" for p in PROMPTS]
    public += [f".pi/workflows/evolution-{w}.js" for w in WORKFLOWS]
    private = [".pi/settings.json", ".pi/mcp.json", ".pi/extensions/local.ts", ".pi/skills/local/SKILL.md",
               ".pi/subagents/artifacts/report.json", ".pi/agents/private.md", ".pi/agents/evolution-other.md",
               ".pi/prompts/evoluir-other.md", ".pi/workflows/evolution-other.js", ".env", ".compras-web/app.sqlite"]
    for path in public + private:
        result = subprocess.run(["git", "-C", str(tmp_path), "check-ignore", "--no-index", "-q", path])
        assert result.returncode == (0 if path in private else 1), path


def test_example_packet_matches_actual_controller_without_executing_it():
    spec = importlib.util.spec_from_file_location("evolution_packet_validator", ROOT / "scripts/evolution.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    packet = json.loads((ROOT / "docs/evolution/packet.example.json").read_text())
    module.validate_packet(packet)
    assert packet["permissions"] == []


@pytest.fixture
def recipe():
    if not NODE:
        pytest.skip("Node unavailable: recipe-execution validation pending; no model/API calls used")

    def run(name, args, result):
        # Emulate only runs.run; this is not a replacement for native sandbox validation.
        harness = """
const fs = require('node:fs');
const config = JSON.parse(process.argv[1]);
const source = fs.readFileSync(config.path, 'utf8');
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
let launches = [];
const runs = {run: async (key, options) => { launches.push({key, options}); return config.result; }};
(async () => {
  try { const value = await new AsyncFunction('runs', 'args', source)(runs, config.args);
    console.log(JSON.stringify({ok:true, value, launches}));
  } catch (error) { console.log(JSON.stringify({ok:false, error:String(error.message), launches})); }
})();
"""
        config = dict(path=str(ROOT / f".pi/workflows/evolution-{name}.js"), args=args, result=result)
        process = subprocess.run([NODE, "-e", harness, json.dumps(config)], capture_output=True, text=True, timeout=10)
        assert process.returncode == 0, process.stderr
        return json.loads(process.stdout)
    return run


def child_result(report, **kwargs):
    return dict(ok=True, runId="actual-native-child-id", structuredOutput=report, **kwargs)


def review_report(**kwargs):
    result = dict(revision=REVISION, verdict="pass", findings=[],
                  acceptance=[dict(criterion="synthetic criterion", status="passed", evidence="synthetic receipt")])
    result.update(kwargs)
    return result


def review_args():
    return dict(packetPath="/synthetic/packet.json", checksPath="/synthetic/state.json",
                revision=REVISION, acceptance=["synthetic criterion"])


@pytest.mark.parametrize("status", ["completed", "blocked"])
def test_discovery_preserves_explicit_status_without_authorizing_work(recipe, status):
    result = recipe("discover", {"demand": "only synthetic configuration evidence"},
                    child_result(dict(status=status, summary="synthetic", candidates=[], limitations=[])))
    assert result["ok"]
    assert result["value"]["status"] == status
    assert result["value"]["runId"] == "actual-native-child-id"
    launch = result["launches"][0]["options"]
    assert launch["agent"] == "evolution-investigator"
    assert launch["context"] == "fresh" and launch["worktree"] is False
    assert launch["label"] and launch["outputSchema"]
    assert "async" not in launch


def test_discovery_rejects_blank_demand_before_dispatch(recipe):
    result = recipe("discover", {"demand": " "}, {})
    assert not result["ok"] and not result["launches"]


def test_native_launch_success_without_completed_output_is_not_evidence(recipe):
    result = recipe("discover", {"demand": "synthetic"}, dict(ok=True, runId="receipt-only", output=""))
    assert not result["ok"]


def test_review_binds_real_native_run_identity_not_agent_text(recipe):
    result = recipe("review", review_args(), child_result(review_report(reviewer_run_id="forged-text-id")))
    assert result["ok"] and result["value"]["status"] == "completed"
    assert result["value"]["report"]["reviewer_run_id"] == "actual-native-child-id"
    assert result["launches"][0]["options"]["agent"] == "evolution-reviewer"


@pytest.mark.parametrize("change", [
    {"verdict": "block"},
    {"findings": [dict(severity="P1", evidence="synthetic repro", summary="blocked finding")]},
    {"acceptance": [dict(criterion="synthetic criterion", status="pending", evidence="not verified")]},
])
def test_review_does_not_promote_pending_criteria_or_findings_to_pass(recipe, change):
    result = recipe("review", review_args(), child_result(review_report(**change)))
    assert result["ok"]
    assert result["value"]["status"] == "blocked"
    assert result["value"]["report"]["verdict"] == "block"


@pytest.mark.parametrize("change", [{"revision": "b" * 40}, {"acceptance": []}])
def test_review_rejects_stale_or_incomplete_structured_reports(recipe, change):
    result = recipe("review", review_args(), child_result(review_report(**change)))
    assert not result["ok"]


def test_review_rejects_launch_receipt_before_completion(recipe):
    result = recipe("review", review_args(), dict(ok=False, runId="still-running", state="running", output=""))
    assert not result["ok"]
