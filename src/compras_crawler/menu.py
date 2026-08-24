from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, TextIO
import sys

from .manifest import build_historical_manifest, build_operation_catalog, default_date_window

InputFunc = Callable[[], str]

DEFAULT_BASE_URL = "https://dadosabertos.compras.gov.br"
DEFAULT_DB_PATH = "compras.duckdb"


@dataclass(frozen=True)
class MenuChoice:
    value: str
    label: str


class InteractiveSyncMenu:
    """Small dependency-free menu that builds argv for `compras-crawler sync`."""

    def __init__(self, *, input_func: InputFunc | None = None, stream: TextIO | None = None):
        self.input_func = input_func or input
        self.stream = stream or sys.stdout

    def collect_sync_argv(self) -> list[str] | None:
        self._heading("compras-crawler")
        action = self._select(
            "O que você quer fazer?",
            [
                MenuChoice("run", "Configurar e executar sync"),
                MenuChoice("list", "Listar operações disponíveis"),
                MenuChoice("quit", "Sair"),
            ],
            default="run",
        )
        if action == "quit":
            self._write("Saindo sem executar.")
            return None
        if action == "list":
            return ["--list-operations"]

        mode = self._select(
            "Tipo de fluxo",
            [
                MenuChoice("historical", "Histórico / operações da API"),
                MenuChoice("municipality", "Compras por município (PNCP)"),
            ],
            default="historical",
        )

        default_start, default_end = default_date_window()
        argv: list[str] = []
        db_path = self._text("DuckDB de destino", default=DEFAULT_DB_PATH)
        argv.extend(["--db-path", db_path])
        ops_db_path = self._text("SQLite de operações/checkpoints (vazio = automático)", default="")
        if ops_db_path:
            argv.extend(["--ops-db-path", ops_db_path])
        base_url = self._text("Base URL da API", default=DEFAULT_BASE_URL)
        argv.extend(["--base-url", base_url])
        start_date = self._date("Data inicial", default=default_start)
        end_date = self._date("Data final", default=default_end)
        argv.extend(["--start-date", start_date, "--end-date", end_date])
        page_size = self._optional_int("Tamanho de página (vazio = padrão da API)")
        if page_size is not None:
            argv.extend(["--page-size", str(page_size)])
        default_scope = "municipality-purchases" if mode == "municipality" else "historical"
        scope = self._text("Rótulo de escopo", default=default_scope)
        argv.extend(["--scope", scope])

        if mode == "historical":
            self._configure_historical(argv)
        else:
            self._configure_municipality(argv)

        resume = self._confirm("Retomar a partir dos checkpoints?", default=True)
        if not resume:
            argv.append("--no-resume")

        log_level = self._select(
            "Nível de log",
            [
                MenuChoice("DEBUG", "DEBUG"),
                MenuChoice("INFO", "INFO"),
                MenuChoice("WARNING", "WARNING"),
                MenuChoice("ERROR", "ERROR"),
                MenuChoice("CRITICAL", "CRITICAL"),
            ],
            default="WARNING",
        )
        argv.extend(["--log-level", log_level])

        ui_mode = self._select(
            "Interface de progresso",
            [
                MenuChoice("auto", "auto — TUI no terminal, console em pipe/teste"),
                MenuChoice("tui", "tui — forçar tela cheia"),
                MenuChoice("console", "console — saída linear clássica"),
                MenuChoice("none", "none — sem UI de progresso"),
            ],
            default="auto",
        )
        argv.extend(["--ui", ui_mode])
        return argv

    def confirm_run(self) -> bool:
        return self._confirm("Executar agora?", default=True)

    def _configure_historical(self, argv: list[str]) -> None:
        state_uf = self._state_uf("UF opcional para filtrar quando suportado (vazio = todas)", required=False)
        if state_uf:
            argv.extend(["--state-uf", state_uf])

        selected_operations = self._operation_selection()
        for operation_id in selected_operations:
            argv.extend(["--operation", operation_id])

        if "consultarContratacoes_PNCP_14133" in selected_operations:
            modalidade_codes = self._int_list("Códigos de modalidade PNCP", default=(8,), required=True)
            for code in modalidade_codes:
                argv.extend(["--pncp-modalidade-code", str(code)])
            municipality_code = self._optional_int("Código IBGE do município para PNCP (vazio = todos na UF/filtro)")
            if municipality_code is not None:
                if not state_uf:
                    state_uf = self._state_uf("UF obrigatória quando informar município", required=True)
                    argv.extend(["--state-uf", state_uf])
                argv.extend(["--municipality-code", str(municipality_code)])

    def _configure_municipality(self, argv: list[str]) -> None:
        state_uf = self._state_uf("UF do município", required=True)
        municipality_code = self._required_int("Código IBGE do município")
        modalidade_codes = self._int_list("Códigos de modalidade PNCP", default=(8,), required=True)
        argv.extend(["--state-uf", state_uf, "--municipality-code", str(municipality_code), "--source", "pncp"])
        for code in modalidade_codes:
            argv.extend(["--pncp-modalidade-code", str(code)])

    def _operation_selection(self) -> list[str]:
        default_start, default_end = default_date_window()
        catalog = build_operation_catalog(build_historical_manifest(default_start, default_end))
        choices = [
            MenuChoice(spec.operation_id, f"{spec.operation_id} · {spec.entity_name} · jobs={','.join(spec.job_names)}")
            for spec in catalog
        ]
        choices.append(
            MenuChoice(
                "consultarContratacoes_PNCP_14133",
                "consultarContratacoes_PNCP_14133 · pncp_contratacao · exige código de modalidade",
            )
        )
        self._write("")
        self._write("Operações: Enter = todas as operações históricas padrão, sem PNCP.")
        return self._multi_select("Escolha operações por número ou operationId", choices)

    def _heading(self, title: str) -> None:
        self._write("")
        self._write(f"=== {title} ===")

    def _write(self, text: str) -> None:
        print(text, file=self.stream, flush=True)

    def _prompt(self, prompt: str) -> str:
        print(prompt, end="", file=self.stream, flush=True)
        try:
            return self.input_func().strip()
        except EOFError:
            return ""

    def _select(self, prompt: str, choices: list[MenuChoice], *, default: str) -> str:
        default_index = next((index for index, choice in enumerate(choices, start=1) if choice.value == default), 1)
        while True:
            self._write("")
            self._write(prompt)
            for index, choice in enumerate(choices, start=1):
                marker = "*" if index == default_index else " "
                self._write(f"  {index}){marker} {choice.label}")
            raw = self._prompt(f"> [{default_index}] ")
            if not raw:
                return choices[default_index - 1].value
            if raw.isdigit():
                index = int(raw)
                if 1 <= index <= len(choices):
                    return choices[index - 1].value
            normalized = raw.lower()
            for choice in choices:
                if normalized in {choice.value.lower(), choice.label.lower()}:
                    return choice.value
            self._write("Opção inválida. Tente novamente.")

    def _multi_select(self, prompt: str, choices: list[MenuChoice]) -> list[str]:
        for index, choice in enumerate(choices, start=1):
            self._write(f"  {index}) {choice.label}")
        while True:
            raw = self._prompt(f"{prompt} [Enter = todas padrão]: ")
            if not raw or raw.lower() in {"all", "todos", "todas", "*"}:
                return []
            selected: list[str] = []
            failed: list[str] = []
            tokens = [token.strip() for token in raw.replace(";", ",").split(",") if token.strip()]
            for token in tokens:
                if token.isdigit():
                    index = int(token)
                    if 1 <= index <= len(choices):
                        value = choices[index - 1].value
                    else:
                        failed.append(token)
                        continue
                else:
                    match = next((choice for choice in choices if choice.value.lower() == token.lower()), None)
                    if match is None:
                        failed.append(token)
                        continue
                    value = match.value
                if value not in selected:
                    selected.append(value)
            if selected and not failed:
                return selected
            self._write(f"Seleção inválida: {', '.join(failed) if failed else raw}. Tente novamente.")

    def _text(self, prompt: str, *, default: str) -> str:
        suffix = f" [{default}]" if default else ""
        raw = self._prompt(f"{prompt}{suffix}: ")
        return raw or default

    def _date(self, prompt: str, *, default: str) -> str:
        while True:
            value = self._text(prompt, default=default)
            try:
                date.fromisoformat(value)
            except ValueError:
                self._write("Data inválida. Use YYYY-MM-DD.")
                continue
            return value

    def _confirm(self, prompt: str, *, default: bool) -> bool:
        default_hint = "S/n" if default else "s/N"
        while True:
            raw = self._prompt(f"{prompt} [{default_hint}]: ").lower()
            if not raw:
                return default
            if raw in {"s", "sim", "y", "yes"}:
                return True
            if raw in {"n", "nao", "não", "no"}:
                return False
            self._write("Responda com s ou n.")

    def _state_uf(self, prompt: str, *, required: bool) -> str | None:
        while True:
            raw = self._prompt(f"{prompt}{' *' if required else ''}: ").upper()
            if not raw and not required:
                return None
            if len(raw) == 2 and raw.isalpha():
                return raw
            self._write("UF inválida. Informe a sigla com 2 letras, ex.: SC.")

    def _optional_int(self, prompt: str) -> int | None:
        while True:
            raw = self._prompt(f"{prompt}: ")
            if not raw:
                return None
            try:
                return int(raw)
            except ValueError:
                self._write("Número inválido. Tente novamente.")

    def _required_int(self, prompt: str) -> int:
        while True:
            value = self._optional_int(f"{prompt} *")
            if value is not None:
                return value
            self._write("Campo obrigatório.")

    def _int_list(self, prompt: str, *, default: tuple[int, ...], required: bool) -> list[int]:
        default_text = ",".join(str(item) for item in default)
        while True:
            raw = self._prompt(f"{prompt}{' *' if required else ''} [{default_text}]: ")
            if not raw:
                if default:
                    return list(default)
                if not required:
                    return []
            tokens = [token for token in raw.replace(";", ",").replace(" ", ",").split(",") if token]
            try:
                values = [int(token) for token in tokens]
            except ValueError:
                self._write("Lista inválida. Use números separados por vírgula, ex.: 8,10.")
                continue
            if values or not required:
                return values
            self._write("Informe ao menos um código.")
