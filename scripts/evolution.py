#!/usr/bin/env python3
"""Supervised local evolution lifecycle. Operational controls, NOT a sandbox.

Only the parent coordinator records human decisions. Commands never launch agents,
install dependencies, query procurement APIs, push, stash, reset or delete lanes.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import uuid


class WorkflowError(Exception):
    pass


PERMISSIONS = {"real-data", "live-collection", "migration", "production-dependencies", "new-source", "publish"}
TERMINAL = {"integrated", "cancelled"}
MAX_CORRECTIONS = 2


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def text(value):
    return isinstance(value, str) and bool(value.strip()) and "\0" not in value


def require(condition, message):
    if not condition:
        raise WorkflowError(message)


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowError(f"JSON indisponível/inválido: {path}: {exc}") from exc


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    require(result.returncode == 0, f"Git recusou {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def clean(root):
    require(not git(root, "status", "--porcelain=v1", "--untracked-files=all"),
            f"Árvore suja: {root}. Não farei commit, stash ou reset das suas alterações.")


def validate_packet(packet):
    keys = {"title", "objective", "evidence", "in_scope", "out_of_scope", "acceptance", "risks", "checks", "permissions"}
    require(isinstance(packet, dict) and set(packet) == keys, f"Campos do pacote devem ser exatamente: {sorted(keys)}")
    for key in ("title", "objective"):
        require(text(packet[key]), f"{key} deve ser texto não vazio")
    for key in ("evidence", "in_scope", "out_of_scope", "acceptance", "risks", "permissions"):
        values = packet[key]
        require(isinstance(values, list) and all(text(v) for v in values), f"{key} deve ser uma lista de textos")
        require(len(values) == len(set(values)), f"{key} contém duplicatas")
        if key not in ("risks", "permissions"):
            require(bool(values), f"{key} não pode estar vazio")
    require(set(packet["permissions"]) <= PERMISSIONS, "Permissão desconhecida")
    checks = packet["checks"]
    require(isinstance(checks, list) and checks, "Defina pelo menos uma verificação executável")
    names = []
    for check in checks:
        require(isinstance(check, dict) and set(check) == {"name", "argv", "timeout_seconds"}, "Formato de check inválido")
        require(text(check["name"]), "Check sem nome")
        require(isinstance(check["argv"], list) and check["argv"] and all(text(a) for a in check["argv"]),
                "argv deve ser uma lista não vazia, nunca um comando shell")
        require(type(check["timeout_seconds"]) is int and 1 <= check["timeout_seconds"] <= 7200, "Timeout inválido")
        names.append(check["name"])
    require(len(names) == len(set(names)), "Nomes de checks duplicados")
    require(len(canonical(packet)) <= 65536, "Pacote excede 64 KiB; não inclua logs ou segredos")
    return packet


class Workflow:
    def __init__(self, repo):
        self.repo = Path(git(Path(repo).resolve(), "rev-parse", "--show-toplevel")).resolve()
        common = Path(git(self.repo, "rev-parse", "--git-common-dir"))
        self.common = (self.repo / common).resolve()
        self.root = self.common / "evolution"

    @contextmanager
    def lock(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.root / ".lock").open("a") as handle:
            os.chmod(handle.name, 0o600)
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise WorkflowError("Outro comando de evolução está em andamento; consulte status.") from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def directory(self, cycle_id):
        require(bool(re.fullmatch(r"evo-[0-9a-f]{12}", cycle_id)), "ID de lote inválido")
        return self.root / "cycles" / cycle_id

    def load(self, cycle_id):
        state = load_json(self.directory(cycle_id) / "state.json")
        require(state.get("version") == 1 and state.get("id") == cycle_id, "Estado desconhecido/corrompido")
        packet = validate_packet(state["packet"])
        require(digest(packet) == state["packet_hash"], "Pacote foi alterado: nova proposta e aprovação são necessárias")
        require(Path(state["source"]).resolve() == self.repo, "Use --repo com a árvore de origem registrada no lote")
        if state.get("approval"):
            require(state["approval"]["packet_hash"] == state["packet_hash"] and
                    state["approval"]["base"] == state["base"], "Aprovação não corresponde ao pacote/base")
        return state

    def save(self, state, event):
        state["updated_at"] = now()
        state.setdefault("history", []).append({"at": now(), "event": event, "status": state["status"]})
        atomic_json(self.directory(state["id"]) / "state.json", state)
        return state

    def status(self, cycle_id=None):
        if cycle_id:
            return self.load(cycle_id)
        return [self.load(p.parent.name) for p in sorted((self.root / "cycles").glob("*/state.json"))]

    def propose(self, packet):
        packet = validate_packet(packet)
        clean(self.repo)
        branch = git(self.repo, "symbolic-ref", "--short", "HEAD")
        cycle_id = "evo-" + uuid.uuid4().hex[:12]
        return self.save(dict(version=1, id=cycle_id, status="proposed", source=str(self.repo), source_branch=branch,
                              base=git(self.repo, "rev-parse", "HEAD"), packet=packet, packet_hash=digest(packet),
                              correction_rounds=0, review_count=0, created_at=now()), "proposed")

    def approve(self, state, approval, permissions):
        require(state["status"] == "proposed", "Apenas propostas podem ser aprovadas")
        require(text(approval), "Registre a decisão humana explícita, nunca aprovação presumida")
        require(set(permissions) == set(state["packet"]["permissions"]), "Permissões sensíveis exigem autorizações explícitas --allow")
        self.source_at_base(state)
        state["approval"] = dict(decision=approval, at=now(), packet_hash=state["packet_hash"], base=state["base"],
                                 permissions=sorted(permissions))
        state["status"] = "approved"
        return self.save(state, "approved-by-operator")

    def source_at_base(self, state):
        clean(self.repo)
        require(git(self.repo, "symbolic-ref", "--short", "HEAD") == state["source_branch"], "Branch de origem mudou")
        require(git(self.repo, "rev-parse", "HEAD") == state["base"], "Base mudou: replaneje e peça nova aprovação")

    def lane(self, state, *, committed=False):
        require(state.get("worktree") and state.get("branch"), "Lote ainda não possui worktree")
        lane = Path(state["worktree"])
        require(lane.is_dir(), "Worktree ausente; reconcilie manualmente, sem recriar ou descartar trabalho")
        require(Path(git(lane, "rev-parse", "--show-toplevel")).resolve() == lane.resolve(), "Caminho deixou de ser a worktree registrada")
        common = Path(git(lane, "rev-parse", "--git-common-dir"))
        require((lane / common).resolve() == self.common, "Worktree pertence a outro repositório")
        require(git(lane, "symbolic-ref", "--short", "HEAD") == state["branch"], "Branch da worktree mudou")
        require(git(lane, "merge-base", "--is-ancestor", state["base"], "HEAD") == "", "Histórico divergiu da base aprovada")
        if committed:
            clean(lane)
            packet_path = lane / "docs" / "evolution" / "cycles" / state["id"] / "packet.json"
            require(digest(load_json(packet_path)) == state["packet_hash"], "Pacote versionado diverge da aprovação")
        return lane

    def start(self, state):
        require(state["status"] == "approved" and state.get("approval"), "Execução exige aprovação humana do pacote")
        self.source_at_base(state)
        for other in self.status():
            require(other["id"] == state["id"] or not other.get("worktree") or other["status"] in TERMINAL,
                    f"Outro lote mantém a faixa de escrita: {other['id']}; reconcilie antes de iniciar")
        lane = self.repo.parent / "worktrees" / self.repo.name / state["id"]
        require(not lane.exists() and not lane.resolve().is_relative_to(self.repo), "Caminho de worktree indisponível/inseguro")
        state.update(worktree=str(lane), branch=f"evolution/{state['id']}", status="allocating")
        self.save(state, "allocation-intent")
        try:
            lane.parent.mkdir(parents=True, exist_ok=True)
            git(self.repo, "worktree", "add", "-b", state["branch"], str(lane), state["base"])
            atomic_json(lane / "docs" / "evolution" / "cycles" / state["id"] / "packet.json", state["packet"])
        except (WorkflowError, OSError) as exc:
            state.update(status="blocked", blocked_kind="allocation", reason=str(exc))
            self.save(state, "allocation-uncertain-preserved")
            raise
        state["status"] = "running"
        return self.save(state, "started")

    def assign(self, state, implementer, reconciled=False):
        require(state["status"] == "running" and text(implementer), "Atribuição exige execução ativa e identidade real")
        require(not state.get("implementer") or state["implementer"] == implementer or reconciled,
                "Reconcilie o escritor anterior e registre --reconciled antes de substituir")
        if state.get("implementer") != implementer:
            state.update(checks=None, review=None)
            state.setdefault("implementers", []).append(implementer)
        state["implementer"] = implementer
        return self.save(state, "writer-assigned-after-reconciliation" if reconciled else "writer-assigned")

    def pause(self, state, reason):
        require(state["status"] in {"running", "checking", "ready", "allocating"} and text(reason), "Pausa exige lote ativo e motivo")
        state.update(status="blocked", blocked_kind="checkpoint", reason=reason)
        return self.save(state, "paused-after-child-reconciliation")

    def resume(self, state):
        require(state["status"] == "blocked", "Somente lotes bloqueados podem retomar")
        require(state.get("approval"), "Aprovação ausente")
        require(state.get("blocked_kind") != "allocation", "Alocação incerta: preserve o estado e reconcilie antes de outro lote")
        self.lane(state)
        if state["blocked_kind"] == "review":
            require(state["correction_rounds"] < MAX_CORRECTIONS, "Limite de duas rodadas corretivas atingido; decisão humana e novo lote necessários")
            state["correction_rounds"] += 1
        state.update(status="running", checks=None, review=None)
        return self.save(state, "resumed-no-agent-dispatched")

    def cancel(self, state, approval):
        require(state["status"] not in TERMINAL and text(approval), "Cancelamento exige decisão humana e lote não terminal")
        state.update(status="cancelled", cancellation=dict(decision=approval, at=now()))
        return self.save(state, "cancelled-worktree-preserved")

    def check(self, state):
        require(state["status"] == "running" and state.get("implementer"), "Checks exigem lote ativo e escritor atribuído")
        lane = self.lane(state, committed=True)
        revision = git(lane, "rev-parse", "HEAD")
        state.update(status="checking", checks=None, review=None)
        self.save(state, "checks-started")
        receipts = []
        # This removes accidental credential inheritance, not access to host files/network.
        env = {k: v for k, v in os.environ.items() if not re.search(r"TOKEN|SECRET|PASSWORD|API_KEY|AUTH", k, re.I)}
        env["PYTHONPATH"] = str(lane / "src")
        env.pop("PYTHONHOME", None)
        check_dir = self.directory(state["id"]) / "checks" / uuid.uuid4().hex
        check_dir.mkdir(parents=True, mode=0o700)
        try:
            for index, command in enumerate(state["packet"]["checks"]):
                log = check_dir / f"{index}.log"
                receipt = dict(name=command["name"], argv=command["argv"], log=str(log), started_at=now())
                with log.open("xb") as output:
                    os.chmod(log, 0o600)
                    process = subprocess.Popen(command["argv"], cwd=lane, env=env, stdout=output,
                                               stderr=subprocess.STDOUT, start_new_session=True)
                    try:
                        code = process.wait(timeout=command["timeout_seconds"])
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                        code = -1
                        receipt["timed_out"] = True
                receipt.update(exit_code=code, finished_at=now(), log_hash=hashlib.sha256(log.read_bytes()).hexdigest())
                receipts.append(receipt)
                require(code == 0, f"Verificação falhou: {command['name']}; consulte {log}")
            self.lane(state, committed=True)
            require(git(lane, "rev-parse", "HEAD") == revision, "HEAD mudou durante as verificações")
        except (WorkflowError, OSError) as exc:
            state.update(status="blocked", blocked_kind="checks", reason=str(exc),
                         checks=dict(passed=False, revision=revision, packet_hash=state["packet_hash"], commands=receipts))
            self.save(state, "checks-blocked")
            raise WorkflowError(str(exc)) from exc
        state.update(status="running", checks=dict(passed=True, revision=revision, packet_hash=state["packet_hash"], commands=receipts))
        return self.save(state, "checks-passed")

    def evidence_at_head(self, state):
        lane = self.lane(state, committed=True)
        revision = git(lane, "rev-parse", "HEAD")
        checks = state.get("checks") or {}
        require(checks.get("passed") and checks.get("revision") == revision and checks.get("packet_hash") == state["packet_hash"],
                "Verificações ausentes ou obsoletas; execute check no HEAD atual")
        for command in checks["commands"]:
            log = Path(command["log"])
            require(log.is_file() and hashlib.sha256(log.read_bytes()).hexdigest() == command["log_hash"], "Log de verificação ausente/alterado")
        return revision

    def review(self, state, report):
        require(state["status"] == "running", "Revisão exige lote ativo")
        revision = self.evidence_at_head(state)
        require(isinstance(report, dict) and set(report) == {"reviewer_run_id", "revision", "verdict", "findings", "acceptance"}, "Formato de revisão inválido")
        require(text(report["reviewer_run_id"]) and report["reviewer_run_id"] not in state.get("implementers", []), "Revisor deve ser independente do escritor")
        require(report["revision"] == revision and report["verdict"] in {"pass", "block"}, "Revisão obsoleta/veredito inválido")
        findings = report["findings"]
        require(isinstance(findings, list), "Achados devem ser lista")
        for finding in findings:
            require(isinstance(finding, dict) and set(finding) == {"severity", "evidence", "summary"} and
                    finding["severity"] in {"P0", "P1", "P2"} and text(finding["evidence"]) and text(finding["summary"]), "Achado sem evidência válida")
        acceptance = report["acceptance"]
        require(isinstance(acceptance, list), "Aceite deve ser lista")
        for item in acceptance:
            require(isinstance(item, dict) and set(item) == {"criterion", "status", "evidence"} and
                    item["status"] in {"passed", "pending", "failed"} and text(item["evidence"]) and text(item["criterion"]), "Critério sem status/evidência")
        require(len(acceptance) == len(state["packet"]["acceptance"]) and
                {i["criterion"] for i in acceptance} == set(state["packet"]["acceptance"]), "Revisão deve cobrir cada critério exatamente uma vez")
        require(state["review_count"] <= MAX_CORRECTIONS, "Orçamento de revisão esgotado")
        state["review_count"] += 1
        path = self.directory(state["id"]) / f"review-{state['review_count']}.json"
        atomic_json(path, report)
        blocked = (report["verdict"] == "block" or any(f["severity"] in {"P0", "P1"} for f in findings)
                   or any(i["status"] != "passed" for i in acceptance))
        state.update(review=dict(revision=revision, packet_hash=state["packet_hash"], passed=not blocked,
                                 path=str(path), hash=digest(report), reviewer_run_id=report["reviewer_run_id"]),
                     status="blocked" if blocked else "ready")
        if blocked:
            state.update(blocked_kind="review", reason="Revisão bloqueante ou aceite pendente; nenhuma aprovação funcional presumida")
        return self.save(state, "review-blocked" if blocked else "review-passed")

    def ready_revision(self, state):
        revision = self.evidence_at_head(state)
        review = state.get("review") or {}
        require(review.get("passed") and review.get("revision") == revision and review.get("packet_hash") == state["packet_hash"], "Revisão ausente/obsoleta")
        require(digest(load_json(review["path"])) == review["hash"], "Relatório de revisão mudou")
        return revision

    def accept(self, state, approval):
        require(state["status"] == "ready" and text(approval), "Aceite exige lote pronto e decisão humana explícita")
        revision = self.ready_revision(state)
        state.update(status="accepted", acceptance=dict(revision=revision, decision=approval, at=now()))
        return self.save(state, "accepted-by-operator-not-integrated")

    def integrate(self, state, approval):
        require(state["status"] in {"accepted", "integrated"} and text(approval), "Integração exige aceite e autorização humana separada")
        revision = self.ready_revision(state)
        require(revision == state["acceptance"]["revision"], "HEAD difere do aceite humano")
        clean(self.repo)
        require(git(self.repo, "symbolic-ref", "--short", "HEAD") == state["source_branch"], "Branch de origem mudou")
        source_head = git(self.repo, "rev-parse", "HEAD")
        require(source_head in {state["base"], revision}, "Origem avançou; não farei rebase/merge sem nova validação e aprovação")
        if source_head != revision:
            git(self.repo, "merge", "--ff-only", state["branch"])
        require(git(self.repo, "rev-parse", "HEAD") == revision, "Integração não confirmada")
        state.update(status="integrated", integration=dict(decision=approval, revision=revision, at=now()))
        return self.save(state, "integrated-locally-no-push")


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--repo", default=".", help="Árvore de origem (não a lane); decisões são registradas somente pelo coordenador")
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("propose").add_argument("--packet", required=True)
    commands.add_parser("status").add_argument("id", nargs="?")
    for name in ("approve", "start", "assign", "pause", "resume", "cancel", "check", "review", "accept", "integrate"):
        sub = commands.add_parser(name)
        sub.add_argument("id")
        if name in {"approve", "accept", "cancel", "integrate"}:
            sub.add_argument("--approval", required=True)
        if name == "approve":
            sub.add_argument("--allow", action="append", default=[], choices=sorted(PERMISSIONS))
        if name == "assign":
            sub.add_argument("--implementer", required=True)
            sub.add_argument("--reconciled", action="store_true", help="Coordenador reconciliou a posse do escritor anterior")
        if name == "pause":
            sub.add_argument("--reason", required=True)
        if name == "review":
            sub.add_argument("--report", required=True)
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        workflow = Workflow(args.repo)
        if args.command == "status":
            result = workflow.status(args.id)
        else:
            with workflow.lock():
                if args.command == "propose":
                    result = workflow.propose(load_json(args.packet))
                else:
                    state = workflow.load(args.id)
                    extra = {
                        "approve": lambda: (args.approval, args.allow), "assign": lambda: (args.implementer, args.reconciled),
                        "pause": lambda: (args.reason,), "cancel": lambda: (args.approval,),
                        "review": lambda: (load_json(args.report),), "accept": lambda: (args.approval,),
                        "integrate": lambda: (args.approval,),
                    }
                    result = getattr(workflow, args.command)(state, *extra.get(args.command, lambda: ())())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (WorkflowError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
