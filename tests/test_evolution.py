"""Offline pilot: disposable Git repositories, synthetic data and review attestations.

These tests verify lifecycle plumbing, not model obedience or real API coverage.
"""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evolution.py"
spec = importlib.util.spec_from_file_location("evolution_controller", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Workflow, WorkflowError = module.Workflow, module.WorkflowError


def git(root, *args):
    return module.git(root, *args)


def commit(root, message="synthetic change"):
    git(root, "add", ".")
    git(root, "commit", "-m", message)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def workflow(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Offline pilot")
    git(repo, "config", "user.email", "pilot@example.invalid")
    (repo / ".gitignore").write_text(".pi/\n__pycache__/\n")
    (repo / "sample.txt").write_text("synthetic\n")
    commit(repo, "fixture")
    return Workflow(repo)


@pytest.fixture
def packet():
    return dict(title="Synthetic workflow pilot", objective="Verify lifecycle, not procurement coverage",
                evidence=["Temporary Git fixture"], in_scope=["Synthetic file"], out_of_scope=["Real APIs and data"],
                acceptance=["The synthetic file remains readable"], risks=[], permissions=[],
                checks=[dict(name="offline check", argv=[sys.executable, "-c", "from pathlib import Path; assert Path('sample.txt').read_text()"], timeout_seconds=10)])


def started(workflow, packet):
    state = workflow.propose(packet)
    workflow.approve(state, "operator explicitly approved this synthetic scope", packet["permissions"])
    workflow.start(state)
    workflow.assign(state, "native-writer-1")
    lane = Path(state["worktree"])
    commit(lane, "synthetic packet and implementation")
    return state


def report(workflow, state, *, verdict="pass", severity=None, acceptance="passed", reviewer="native-reviewer-1"):
    return dict(reviewer_run_id=reviewer, revision=git(state["worktree"], "rev-parse", "HEAD"), verdict=verdict,
                findings=[] if severity is None else [dict(severity=severity, evidence="sample.txt:1, temporary fixture", summary="synthetic finding")],
                acceptance=[dict(criterion=c, status=acceptance, evidence="Synthetic read check log and sample.txt:1") for c in state["packet"]["acceptance"]])


def ready(workflow, packet):
    state = started(workflow, packet)
    workflow.check(state)
    workflow.review(state, report(workflow, state))
    return state


def test_complete_offline_pilot_approval_restart_checks_review_accept_integrate(workflow, packet):
    base = git(workflow.repo, "rev-parse", "HEAD")
    state = started(workflow, packet)
    cycle_id = state["id"]
    assert git(workflow.repo, "rev-parse", "HEAD") == base
    assert Path(state["worktree"]) != workflow.repo
    assert not (Path(state["worktree"]) / ".env").exists()
    # A new coordinator process can recover all state without the chat history.
    reopened = Workflow(workflow.repo)
    state = reopened.load(cycle_id)
    reopened.check(state)
    assert state["checks"]["commands"][0]["exit_code"] == 0
    reopened.review(state, report(reopened, state))
    assert state["status"] == "ready"
    with pytest.raises(WorkflowError):
        reopened.integrate(state, "not yet accepted")
    reopened.accept(state, "operator accepted exact synthetic revision")
    assert git(workflow.repo, "rev-parse", "HEAD") == base
    reopened.integrate(state, "operator separately authorized local integration")
    assert git(workflow.repo, "rev-parse", "HEAD") == state["acceptance"]["revision"]
    assert state["status"] == "integrated"
    reopened.integrate(state, "explicit idempotent retry")
    assert Path(state["worktree"]).exists()  # no destructive cleanup
    assert git(workflow.repo, "remote") == ""  # no remote/push involved


@pytest.mark.parametrize("action", ["start", "check", "accept", "integrate"])
def test_cannot_skip_approval(workflow, packet, action):
    state = workflow.propose(packet)
    with pytest.raises(WorkflowError):
        getattr(workflow, action)(state, "not approved") if action in {"accept", "integrate"} else getattr(workflow, action)(state)
    assert workflow.load(state["id"])["status"] == "proposed"


def test_sensitive_permissions_require_exact_explicit_grant(workflow, packet):
    packet["permissions"] = ["live-collection"]
    state = workflow.propose(packet)
    with pytest.raises(WorkflowError, match="autorizações explícitas"):
        workflow.approve(state, "scope approved", [])
    workflow.approve(state, "separately authorized this exact live action (synthetic attestation)", ["live-collection"])
    assert state["approval"]["permissions"] == ["live-collection"]


def test_dirty_source_and_moved_base_refused_without_stash(workflow, packet):
    state = workflow.propose(packet)
    dirty = workflow.repo / "mine.txt"
    dirty.write_text("user changes")
    with pytest.raises(WorkflowError, match="Árvore suja"):
        workflow.approve(state, "decision", [])
    assert dirty.read_text() == "user changes"
    commit(workflow.repo)
    with pytest.raises(WorkflowError, match="Base mudou"):
        workflow.approve(state, "decision", [])


def test_scope_tampering_and_unsafe_cycle_id_fail_closed(workflow, packet):
    state = workflow.propose(packet)
    path = workflow.directory(state["id"]) / "state.json"
    changed = deepcopy(state)
    changed["packet"]["objective"] = "different scope"
    module.atomic_json(path, changed)
    with pytest.raises(WorkflowError, match="Pacote foi alterado"):
        workflow.load(state["id"])
    with pytest.raises(WorkflowError, match="ID de lote inválido"):
        workflow.load("../../outside")


def test_single_active_lane_and_no_double_start(workflow, packet):
    first = started(workflow, packet)
    with pytest.raises(WorkflowError):
        workflow.start(first)
    second = workflow.propose(packet)
    workflow.approve(second, "approved second proposal", [])
    with pytest.raises(WorkflowError, match="faixa de escrita"):
        workflow.start(second)
    workflow.cancel(first, "operator stopped writer and abandoned lane")
    workflow.start(second)
    assert Path(first["worktree"]).exists()
    assert Path(second["worktree"]).exists()


def test_pause_resume_preserves_partial_work_and_lane(workflow, packet):
    state = started(workflow, packet)
    partial = Path(state["worktree"]) / "partial.txt"
    partial.write_text("not committed, must survive")
    workflow.pause(state, "native writer stopped at safe boundary")
    recovered = Workflow(workflow.repo).load(state["id"])
    workflow.resume(recovered)
    assert recovered["worktree"] == state["worktree"]
    assert recovered["correction_rounds"] == 0
    assert partial.read_text() == "not committed, must survive"
    with pytest.raises(WorkflowError, match="Árvore suja"):
        workflow.check(recovered)


def test_crashed_check_requires_explicit_reconciliation(workflow, packet):
    state = started(workflow, packet)
    state["status"] = "checking"
    workflow.save(state, "simulated process exit")
    with pytest.raises(WorkflowError):
        workflow.resume(state)
    workflow.pause(state, "old native child and checker processes confirmed stopped")
    workflow.resume(state)
    assert state["status"] == "running"


@pytest.mark.parametrize("code,timeout,expected", [("raise SystemExit(4)", 10, 4), ("import time; time.sleep(10)", 1, -1)])
def test_failed_or_timed_out_command_blocks_and_retains_evidence(workflow, packet, code, timeout, expected):
    packet["checks"][0].update(argv=[sys.executable, "-c", code], timeout_seconds=timeout)
    state = started(workflow, packet)
    with pytest.raises(WorkflowError, match="Verificação falhou"):
        workflow.check(state)
    recovered = workflow.load(state["id"])
    assert recovered["status"] == "blocked"
    assert recovered["checks"]["commands"][0]["exit_code"] == expected
    assert Path(recovered["checks"]["commands"][0]["log"]).is_file()
    with pytest.raises(WorkflowError):
        workflow.accept(recovered, "not ready")


def test_check_env_does_not_inherit_secrets_or_main_source_path(workflow, packet, monkeypatch):
    monkeypatch.setenv("COMPRAS_GOV_TOKEN", "must-not-leak")
    monkeypatch.setenv("OTHER_API_KEY", "must-not-leak")
    monkeypatch.setenv("PYTHONPATH", "/wrong/main/src")
    code = "import os; from pathlib import Path; assert 'COMPRAS_GOV_TOKEN' not in os.environ; assert 'OTHER_API_KEY' not in os.environ; assert os.environ['PYTHONPATH'] == str(Path.cwd() / 'src')"
    packet["checks"][0]["argv"] = [sys.executable, "-c", code]
    state = started(workflow, packet)
    workflow.check(state)
    assert state["checks"]["passed"]


def test_check_cannot_mutate_working_tree_and_claim_success(workflow, packet):
    packet["checks"][0]["argv"] = [sys.executable, "-c", "from pathlib import Path; Path('untracked.txt').write_text('changed')"]
    state = started(workflow, packet)
    with pytest.raises(WorkflowError, match="Árvore suja"):
        workflow.check(state)
    assert state["status"] == "blocked"


def test_self_review_and_missing_checks_rejected(workflow, packet):
    state = started(workflow, packet)
    with pytest.raises(WorkflowError, match="Verificações ausentes"):
        workflow.review(state, report(workflow, state))
    workflow.check(state)
    with pytest.raises(WorkflowError, match="independente"):
        workflow.review(state, report(workflow, state, reviewer="native-writer-1"))
    workflow.assign(state, "resumed-writer-2", reconciled=True)
    workflow.check(state)
    with pytest.raises(WorkflowError, match="independente"):
        workflow.review(state, report(workflow, state, reviewer="native-writer-1"))


def test_reassignment_requires_explicit_ownership_reconciliation(workflow, packet):
    state = started(workflow, packet)
    workflow.check(state)
    with pytest.raises(WorkflowError, match="Reconcilie"):
        workflow.assign(state, "other-writer")
    workflow.assign(state, "resumed-writer", reconciled=True)
    assert state["checks"] is None
    assert state["implementers"] == ["native-writer-1", "resumed-writer"]


@pytest.mark.parametrize("kwargs", [{"severity": "P0"}, {"severity": "P1"}, {"acceptance": "pending"}, {"acceptance": "failed"}, {"verdict": "block"}])
def test_findings_and_incomplete_acceptance_block(workflow, packet, kwargs):
    state = started(workflow, packet)
    workflow.check(state)
    workflow.review(state, report(workflow, state, **kwargs))
    assert state["status"] == "blocked"
    with pytest.raises(WorkflowError):
        workflow.accept(state, "cannot waive gate")


def test_two_corrective_rounds_do_not_reset_after_restart(workflow, packet):
    state = started(workflow, packet)
    for round_number in range(3):  # initial review, then two corrective reviews
        workflow.check(state)
        workflow.review(state, report(workflow, state, severity="P1"))
        state = Workflow(workflow.repo).load(state["id"])
        assert state["correction_rounds"] == round_number
        if round_number < 2:
            workflow.resume(state)
    with pytest.raises(WorkflowError, match="duas rodadas"):
        workflow.resume(state)
    assert state["review_count"] == 3


def test_report_must_cover_every_criterion_exactly_once(workflow, packet):
    state = started(workflow, packet)
    workflow.check(state)
    missing = report(workflow, state)
    missing["acceptance"] = []
    with pytest.raises(WorkflowError, match="cada critério"):
        workflow.review(state, missing)


def test_p2_notes_do_not_waive_acceptance_or_block_ready(workflow, packet):
    state = started(workflow, packet)
    workflow.check(state)
    workflow.review(state, report(workflow, state, severity="P2"))
    assert state["status"] == "ready"
    assert "acceptance" not in state


def test_stale_head_and_dirty_lane_invalidate_acceptance(workflow, packet):
    state = ready(workflow, packet)
    lane = Path(state["worktree"])
    (lane / "new.txt").write_text("not reviewed")
    with pytest.raises(WorkflowError, match="Árvore suja"):
        workflow.accept(state, "stale")
    commit(lane)
    with pytest.raises(WorkflowError, match="obsoletas"):
        workflow.accept(state, "stale")


def test_changed_packet_or_deleted_log_cannot_be_accepted(workflow, packet):
    state = ready(workflow, packet)
    log = Path(state["checks"]["commands"][0]["log"])
    log.write_text("replaced log")
    with pytest.raises(WorkflowError, match="Log de verificação"):
        workflow.accept(state, "not valid")
    lane = Path(state["worktree"])
    packet_path = lane / "docs" / "evolution" / "cycles" / state["id"] / "packet.json"
    altered = deepcopy(packet)
    altered["objective"] = "unapproved"
    module.atomic_json(packet_path, altered)
    commit(lane)
    with pytest.raises(WorkflowError, match="Pacote versionado"):
        workflow.accept(state, "not valid")


def test_moved_main_is_not_silently_merged(workflow, packet):
    state = ready(workflow, packet)
    workflow.accept(state, "operator accepted")
    (workflow.repo / "other.txt").write_text("unrelated source work")
    new_base = commit(workflow.repo)
    with pytest.raises(WorkflowError, match="Origem avançou"):
        workflow.integrate(state, "integration permission cannot override moved source")
    assert git(workflow.repo, "rev-parse", "HEAD") == new_base


def test_lock_is_shared_and_status_read_is_available(workflow, packet):
    state = workflow.propose(packet)
    second = Workflow(workflow.repo)
    with workflow.lock():
        assert second.status(state["id"])["status"] == "proposed"
        with pytest.raises(WorkflowError, match="Outro comando"):
            with second.lock():
                pytest.fail("must not acquire concurrent mutation lock")


def test_cli_persists_across_processes_and_rejects_integration_without_decision(workflow, packet, tmp_path):
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet))
    command = [sys.executable, str(SCRIPT), "--repo", str(workflow.repo)]
    result = subprocess.run(command + ["propose", "--packet", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    status = subprocess.run(command + ["status", state["id"]], capture_output=True, text=True)
    assert json.loads(status.stdout)["packet_hash"] == state["packet_hash"]
    refused = subprocess.run(command + ["start", state["id"]], capture_output=True, text=True)
    assert refused.returncode == 1
    assert "aprovação humana" in refused.stderr
    incomplete = subprocess.run(command + ["integrate", state["id"]], capture_output=True, text=True)
    assert incomplete.returncode != 0
    assert "--approval" in incomplete.stderr


@pytest.mark.parametrize("change", [
    lambda p: p.update(unexpected="field"),
    lambda p: p.update(acceptance=[]),
    lambda p: p.update(permissions=["all"]),
    lambda p: p["checks"][0].update(argv="echo unsafe shell"),
    lambda p: p["checks"][0].update(timeout_seconds=True),
])
def test_invalid_packets_are_rejected(packet, change):
    change(packet)
    with pytest.raises(WorkflowError):
        module.validate_packet(packet)


def test_allocation_failure_is_journaled_and_not_retried(workflow, packet):
    state = workflow.propose(packet)
    workflow.approve(state, "operator approval", [])
    # A foreign pre-existing branch must not be overwritten or deleted.
    git(workflow.repo, "branch", f"evolution/{state['id']}")
    with pytest.raises(WorkflowError, match="Git recusou"):
        workflow.start(state)
    recovered = workflow.load(state["id"])
    assert recovered["status"] == "blocked"
    assert recovered["blocked_kind"] == "allocation"
    assert recovered["worktree"]
    with pytest.raises(WorkflowError, match="Alocação incerta"):
        workflow.resume(recovered)
    assert git(workflow.repo, "rev-parse", f"evolution/{state['id']}") == state["base"]


def test_report_tampering_and_wrong_lane_branch_refused(workflow, packet):
    state = ready(workflow, packet)
    path = Path(state["review"]["path"])
    stored = module.load_json(path)
    stored["verdict"] = "block"
    module.atomic_json(path, stored)
    with pytest.raises(WorkflowError, match="Relatório de revisão mudou"):
        workflow.accept(state, "must not accept altered evidence")
    git(state["worktree"], "checkout", "-b", "foreign-branch")
    with pytest.raises(WorkflowError, match="Branch da worktree mudou"):
        workflow.accept(state, "must not accept foreign lane")


def test_cli_happy_path_is_a_real_process_restart_pilot(workflow, packet, tmp_path):
    packet_path = tmp_path / "packet-cli.json"
    module.atomic_json(packet_path, packet)
    base = git(workflow.repo, "rev-parse", "HEAD")
    prefix = [sys.executable, str(SCRIPT), "--repo", str(workflow.repo)]

    def call(*args):
        result = subprocess.run(prefix + list(args), text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    state = call("propose", "--packet", str(packet_path))
    cycle_id = state["id"]
    call("approve", cycle_id, "--approval", "human approved synthetic pilot")
    state = call("start", cycle_id)
    call("assign", cycle_id, "--implementer", "native-pilot-writer")
    commit(state["worktree"])
    call("pause", cycle_id, "--reason", "simulated safe interruption; native child reconciled")
    state = call("resume", cycle_id)
    state = call("check", cycle_id)
    report_path = tmp_path / "independent-report.json"
    module.atomic_json(report_path, report(workflow, state, reviewer="native-pilot-reviewer"))
    state = call("review", cycle_id, "--report", str(report_path))
    assert state["status"] == "ready"
    call("accept", cycle_id, "--approval", "human accepted synthetic revision")
    assert git(workflow.repo, "rev-parse", "HEAD") == base
    state = call("integrate", cycle_id, "--approval", "human separately authorized local ff integration")
    assert state["status"] == "integrated"
    assert call("status", cycle_id)["integration"]["revision"] == git(workflow.repo, "rev-parse", "HEAD")


def test_ignored_packet_absent_from_commit_cannot_pass_checks(workflow, packet):
    (workflow.repo / ".gitignore").write_text("docs/evolution/\n__pycache__/\n")
    commit(workflow.repo, "ignore packet directory")
    state = workflow.propose(packet)
    workflow.approve(state, "synthetic approval", [])
    workflow.start(state)
    workflow.assign(state, "native-writer")
    git(state["worktree"], "commit", "--allow-empty", "-m", "synthetic empty implementation")
    assert not git(state["worktree"], "ls-files", f"docs/evolution/cycles/{state['id']}/packet.json")
    with pytest.raises(WorkflowError, match="Pacote versionado ausente"):
        workflow.check(state)
    assert state.get("checks") is None


def test_integration_uses_frozen_accepted_sha_when_lane_branch_races(workflow, packet, monkeypatch):
    state = ready(workflow, packet)
    workflow.accept(state, "operator accepted this exact revision")
    accepted = state["acceptance"]["revision"]
    original = module.git

    def race(root, *args):
        if args[:2] == ("merge", "--ff-only"):
            assert args[2] == accepted
            (Path(state["worktree"]) / "unaccepted.txt").write_text("not reviewed")
            commit(state["worktree"], "unaccepted concurrent commit")
        return original(root, *args)

    monkeypatch.setattr(module, "git", race)
    workflow.integrate(state, "operator authorized accepted SHA only")
    assert git(workflow.repo, "rev-parse", "HEAD") == accepted
    assert not (workflow.repo / "unaccepted.txt").exists()
    assert state["status"] == "integrated"


def test_check_log_setup_failure_is_blocked_not_falsely_running(workflow, packet):
    state = started(workflow, packet)
    (workflow.directory(state["id"]) / "checks").write_text("filesystem obstruction")
    with pytest.raises(WorkflowError):
        workflow.check(state)
    recovered = workflow.load(state["id"])
    assert recovered["status"] == "blocked"
    assert recovered["blocked_kind"] == "checks"
    assert recovered["reason"]
    assert recovered["checks"]["commands"] == []
    assert not recovered["checks"]["passed"]
