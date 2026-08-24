from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from shutil import get_terminal_size
from textwrap import wrap
from typing import Callable, TextIO
import shlex
import sys

from .manifest import build_historical_manifest, build_operation_catalog, default_date_window

InputFunc = Callable[[], str]

DEFAULT_BASE_URL = "https://dadosabertos.compras.gov.br"
DEFAULT_DB_PATH = "compras.duckdb"


@dataclass(frozen=True)
class MenuChoice:
    value: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class MenuScreen:
    title: str
    step: str
    purpose: str
    hints: tuple[str, ...] = ()


class InteractiveSyncMenu:
    """Guided dependency-free TUI wizard that builds argv for `compras-crawler sync`."""

    def __init__(self, *, input_func: InputFunc | None = None, stream: TextIO | None = None):
        self.input_func = input_func or input
        self.stream = stream or sys.stdout
        self._last_sync_argv: list[str] | None = None

    def collect_sync_argv(self) -> list[str] | None:
        self._last_sync_argv = None
        self._screen(
            MenuScreen(
                title="Boas-vindas",
                step="1/7",
                purpose="Assistente guiado para montar um sync do Compras.gov.br sem decorar flags.",
                hints=(
                    "Enter aceita o padrão marcado com * ou entre colchetes.",
                    "Digite ? em qualquer campo para ver ajuda contextual.",
                ),
            )
        )
        action = self._select(
            "O que você quer fazer?",
            [
                MenuChoice("run", "Configurar e executar sync", "abre telas guiadas para destino, período, filtros e UI"),
                MenuChoice("list", "Listar operações disponíveis", "mostra o catálogo de operationIds da API"),
                MenuChoice("quit", "Sair", "fecha o menu sem executar nada"),
            ],
            default="run",
            help_text="Escolha 1 para montar uma execução, 2 para ver o catálogo, ou 3/q para sair.",
        )
        if action == "quit":
            self._write("Saindo sem executar.")
            return None
        if action == "list":
            argv = ["--list-operations"]
            self._last_sync_argv = argv
            self._screen(
                MenuScreen(
                    title="Catálogo de operações",
                    step="2/2",
                    purpose="O comando gerado lista as operações disponíveis sem alterar os bancos.",
                    hints=("Use esse modo quando quiser descobrir operationIds antes de montar um sync filtrado.",),
                )
            )
            self._render_command_preview(argv)
            return argv

        self._screen(
            MenuScreen(
                title="Fluxo de coleta",
                step="2/7",
                purpose="Escolha o tipo de pergunta que o assistente fará nas próximas telas.",
                hints=(
                    "Histórico usa as operações padrão da API e aceita filtro opcional por UF.",
                    "Município/PNCP é o caminho mais curto para compras de uma cidade específica.",
                ),
            )
        )
        mode = self._select(
            "Tipo de fluxo",
            [
                MenuChoice("historical", "Histórico / operações da API", "sincroniza uma ou mais operações por janela de data"),
                MenuChoice("municipality", "Compras por município (PNCP)", "pede UF, código IBGE e modalidades PNCP"),
            ],
            default="historical",
            help_text="Se você tem um município em mente, escolha PNCP. Para catálogo amplo ou UASG/licitações, escolha histórico.",
        )

        default_start, default_end = default_date_window()
        argv: list[str] = []

        self._screen(
            MenuScreen(
                title="Destino e conexão",
                step="3/7",
                purpose="Defina onde os dados serão gravados e qual API será consultada.",
                hints=(
                    "O DuckDB guarda páginas brutas e registros normalizados.",
                    "O SQLite operacional guarda runs, erros e checkpoints de retomada.",
                ),
            )
        )
        db_path = self._text(
            "DuckDB de destino",
            default=DEFAULT_DB_PATH,
            help_text="Arquivo .duckdb que receberá as tabelas bronze_pages e silver_records. Ex.: compras.duckdb",
        )
        argv.extend(["--db-path", db_path])
        ops_db_path = self._text(
            "SQLite de operações/checkpoints (vazio = automático)",
            default="",
            help_text="Deixe vazio para criar automaticamente <nome_do_duckdb>_ops.sqlite ao lado do DuckDB.",
        )
        if ops_db_path:
            argv.extend(["--ops-db-path", ops_db_path])
        base_url = self._text(
            "Base URL da API",
            default=DEFAULT_BASE_URL,
            help_text="Use HTTPS. Com token, por segurança, a execução fica restrita a dadosabertos.compras.gov.br.",
        )
        argv.extend(["--base-url", base_url])

        self._screen(
            MenuScreen(
                title="Período, paginação e escopo",
                step="4/7",
                purpose="Informe a janela de coleta e como a execução aparecerá nos metadados.",
                hints=(
                    "Datas usam o formato YYYY-MM-DD.",
                    "Tamanho de página vazio mantém o padrão de cada endpoint.",
                ),
            )
        )
        start_date, end_date = self._date_range(
            start_prompt="Data inicial",
            end_prompt="Data final",
            default_start=default_start,
            default_end=default_end,
        )
        argv.extend(["--start-date", start_date, "--end-date", end_date])
        page_size = self._optional_int(
            "Tamanho de página (vazio = padrão da API)",
            help_text="Informe um inteiro positivo, como 100 ou 500. Nem todos os endpoints aceitam esse parâmetro.",
            minimum=1,
        )
        if page_size is not None:
            argv.extend(["--page-size", str(page_size)])
        default_scope = "municipality-purchases" if mode == "municipality" else "historical"
        scope = self._text(
            "Rótulo de escopo",
            default=default_scope,
            help_text="Texto livre para identificar a execução nas tabelas ops_runs/ops_errors. Ex.: brusque-pncp-janeiro.",
        )
        argv.extend(["--scope", scope])

        self._screen(
            MenuScreen(
                title="Filtros da coleta",
                step="5/7",
                purpose="Agora informe os filtros específicos do fluxo escolhido.",
                hints=(
                    "Para histórico, Enter nas operações significa usar o manifesto histórico padrão.",
                    "Para PNCP, código IBGE do município e modalidade são obrigatórios.",
                ),
            )
        )
        if mode == "historical":
            self._configure_historical(argv)
        else:
            self._configure_municipality(argv)

        self._screen(
            MenuScreen(
                title="Execução e feedback",
                step="6/7",
                purpose="Escolha retomada, nível de log e experiência visual durante o sync.",
                hints=(
                    "Retomar checkpoints evita refazer páginas já persistidas.",
                    "A TUI ocupa a tela inteira; console é melhor para logs redirecionados.",
                ),
            )
        )
        resume = self._confirm("Retomar a partir dos checkpoints?", default=True)
        if not resume:
            argv.append("--no-resume")

        log_level = self._select(
            "Nível de log",
            [
                MenuChoice("DEBUG", "DEBUG", "mais verboso, útil para diagnosticar requisições"),
                MenuChoice("INFO", "INFO", "progresso operacional resumido"),
                MenuChoice("WARNING", "WARNING", "padrão: mostra alertas e erros"),
                MenuChoice("ERROR", "ERROR", "somente erros"),
                MenuChoice("CRITICAL", "CRITICAL", "somente falhas críticas"),
            ],
            default="WARNING",
            help_text="WARNING é o padrão seguro. Use DEBUG quando estiver investigando comportamento da API.",
        )
        argv.extend(["--log-level", log_level])

        ui_mode = self._select(
            "Interface de progresso",
            [
                MenuChoice("auto", "auto — TUI no terminal, console em pipe/teste", "recomendado para uso normal"),
                MenuChoice("tui", "tui — forçar tela cheia", "painel em tela inteira com progresso e eventos"),
                MenuChoice("console", "console — saída linear clássica", "bom para copiar logs ou rodar em CI"),
                MenuChoice("none", "none — sem UI de progresso", "útil quando outro processo coleta logs"),
            ],
            default="auto",
            help_text="Use auto na dúvida. Se o terminal ficar estranho, rode novamente com --ui console.",
        )
        argv.extend(["--ui", ui_mode])

        self._last_sync_argv = list(argv)
        self._screen(
            MenuScreen(
                title="Revisão",
                step="7/7",
                purpose="Confira o comando antes de executar. Nada foi chamado ainda.",
                hints=("Se algum campo estiver errado, cancele na confirmação e rode o menu novamente.",),
            )
        )
        self._render_command_preview(argv)
        return argv

    def confirm_run(self) -> bool:
        self._screen(
            MenuScreen(
                title="Confirmação final",
                step="final",
                purpose="Execute agora ou volte sem alterar dados.",
                hints=("Se responder não, nenhum sync é iniciado; o comando equivalente fica impresso no terminal.",),
            )
        )
        return self._confirm("Executar agora?", default=True)

    def _configure_historical(self, argv: list[str]) -> None:
        state_uf = self._state_uf(
            "UF opcional para filtrar quando suportado (vazio = todas)",
            required=False,
            help_text="Sigla de 2 letras, como SC, SP ou RJ. Hoje o filtro é aplicado onde o manifesto suporta UF.",
        )
        if state_uf:
            argv.extend(["--state-uf", state_uf])

        selected_operations = self._operation_selection()
        for operation_id in selected_operations:
            argv.extend(["--operation", operation_id])

        if "consultarContratacoes_PNCP_14133" in selected_operations:
            modalidade_codes = self._int_list(
                "Códigos de modalidade PNCP",
                default=(8,),
                required=True,
                help_text="Informe uma lista de códigos PNCP separados por vírgula. Ex.: 8 ou 8,10.",
            )
            for code in modalidade_codes:
                argv.extend(["--pncp-modalidade-code", str(code)])
            municipality_code = self._optional_int(
                "Código IBGE do município para PNCP (vazio = todos na UF/filtro)",
                help_text="Código IBGE de 7 dígitos. Ex.: 4202909 para Brusque/SC, 3550308 para São Paulo/SP.",
                minimum=1,
            )
            if municipality_code is not None:
                if not state_uf:
                    state_uf = self._state_uf(
                        "UF obrigatória quando informar município",
                        required=True,
                        help_text="A UF evita ambiguidades e é exigida pelo validador quando há município.",
                    )
                    argv.extend(["--state-uf", state_uf])
                argv.extend(["--municipality-code", str(municipality_code)])

    def _configure_municipality(self, argv: list[str]) -> None:
        state_uf = self._state_uf(
            "UF do município",
            required=True,
            help_text="Sigla de 2 letras do estado do município. Ex.: SC.",
        )
        municipality_code = self._required_int(
            "Código IBGE do município",
            help_text="Código IBGE de 7 dígitos. Ex.: 4202909 para Brusque/SC.",
        )
        modalidade_codes = self._int_list(
            "Códigos de modalidade PNCP",
            default=(8,),
            required=True,
            help_text="Lista de códigos PNCP separados por vírgula. Ex.: 8 ou 8,10.",
        )
        argv.extend(["--state-uf", state_uf, "--municipality-code", str(municipality_code), "--source", "pncp"])
        for code in modalidade_codes:
            argv.extend(["--pncp-modalidade-code", str(code)])

    def _operation_selection(self) -> list[str]:
        default_start, default_end = default_date_window()
        catalog = build_operation_catalog(build_historical_manifest(default_start, default_end))
        choices = [
            MenuChoice(
                spec.operation_id,
                spec.operation_id,
                f"entidade={spec.entity_name} · jobs={','.join(spec.job_names)} · aceita={','.join(spec.accepts)}",
            )
            for spec in catalog
        ]
        choices.append(
            MenuChoice(
                "consultarContratacoes_PNCP_14133",
                "consultarContratacoes_PNCP_14133",
                "entidade=pncp_contratacao · exige código de modalidade PNCP",
            )
        )
        self._write("")
        self._write("Operações disponíveis")
        self._write("  Enter/todas = manifesto histórico padrão, sem PNCP.")
        self._write("  Aceita números, operationIds, listas com vírgula e intervalos. Ex.: 1,3-5")
        return self._multi_select(
            "Escolha operações por número ou operationId",
            choices,
            help_text="Enter roda todas as operações históricas padrão. Para PNCP, selecione consultarContratacoes_PNCP_14133.",
        )

    def _screen(self, screen: MenuScreen) -> None:
        width = self._terminal_width()
        inner = max(30, width - 4)
        self._write("")
        self._write("╭" + "─" * (width - 2) + "╮")
        title = f"{screen.step} · {screen.title}" if screen.step else screen.title
        self._box_line(title, inner)
        self._box_line("", inner)
        for line in self._wrap(screen.purpose, inner):
            self._box_line(line, inner)
        if screen.hints:
            self._box_line("", inner)
            for hint in screen.hints:
                for line in self._wrap(f"• {hint}", inner):
                    self._box_line(line, inner)
        self._write("╰" + "─" * (width - 2) + "╯")

    def _box_line(self, text: str, inner: int) -> None:
        self._write("│ " + text[:inner].ljust(inner) + " │")

    def _wrap(self, text: str, width: int) -> list[str]:
        if not text:
            return [""]
        return wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or [""]

    def _terminal_width(self) -> int:
        columns = get_terminal_size(fallback=(88, 24)).columns
        return min(max(columns, 64), 100)

    def _write(self, text: str) -> None:
        print(text, file=self.stream, flush=True)

    def _prompt(self, prompt: str, *, help_text: str | None = None) -> str:
        while True:
            print(prompt, end="", file=self.stream, flush=True)
            try:
                raw = self.input_func().strip()
            except EOFError:
                return ""
            if raw == "?" and help_text:
                self._write_help(help_text)
                continue
            return raw

    def _write_help(self, text: str) -> None:
        self._write("Ajuda:")
        for line in self._wrap(text, self._terminal_width() - 4):
            self._write(f"  {line}")

    def _select(self, prompt: str, choices: list[MenuChoice], *, default: str, help_text: str | None = None) -> str:
        default_index = next((index for index, choice in enumerate(choices, start=1) if choice.value == default), 1)
        while True:
            self._write("")
            self._write(prompt)
            for index, choice in enumerate(choices, start=1):
                marker = "*" if index == default_index else " "
                self._write(f"  {index}){marker} {choice.label}")
                if choice.description:
                    self._write(f"      {choice.description}")
            raw = self._prompt(f"> [{default_index}] ", help_text=help_text)
            if not raw:
                return choices[default_index - 1].value
            if raw.isdigit():
                index = int(raw)
                if 1 <= index <= len(choices):
                    return choices[index - 1].value
            normalized = raw.lower()
            if normalized in {"q", "quit", "sair", "0"} and any(choice.value == "quit" for choice in choices):
                return "quit"
            for choice in choices:
                if normalized in {choice.value.lower(), choice.label.lower()}:
                    return choice.value
            self._write("Opção inválida. Digite ? para ajuda ou tente novamente.")

    def _multi_select(self, prompt: str, choices: list[MenuChoice], *, help_text: str | None = None) -> list[str]:
        for index, choice in enumerate(choices, start=1):
            self._write(f"  {index:>2}) {choice.label}")
            if choice.description:
                self._write(f"      {choice.description}")
        while True:
            raw = self._prompt(f"{prompt} [Enter = todas padrão]: ", help_text=help_text)
            if not raw or raw.lower() in {"all", "todos", "todas", "*"}:
                return []
            selected: list[str] = []
            failed: list[str] = []
            tokens = [token.strip() for token in raw.replace(";", ",").split(",") if token.strip()]
            for token in tokens:
                values = self._resolve_choice_token(token, choices)
                if values is None:
                    failed.append(token)
                    continue
                for value in values:
                    if value not in selected:
                        selected.append(value)
            if selected and not failed:
                return selected
            self._write(f"Seleção inválida: {', '.join(failed) if failed else raw}. Tente novamente.")

    def _resolve_choice_token(self, token: str, choices: list[MenuChoice]) -> list[str] | None:
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            if start_text.strip().isdigit() and end_text.strip().isdigit():
                start = int(start_text)
                end = int(end_text)
                if start > end:
                    start, end = end, start
                if 1 <= start <= len(choices) and 1 <= end <= len(choices):
                    return [choices[index - 1].value for index in range(start, end + 1)]
                return None
        if token.isdigit():
            index = int(token)
            if 1 <= index <= len(choices):
                return [choices[index - 1].value]
            return None
        match = next((choice for choice in choices if choice.value.lower() == token.lower()), None)
        if match is None:
            return None
        return [match.value]

    def _text(self, prompt: str, *, default: str, help_text: str | None = None) -> str:
        suffix = f" [{default}]" if default else ""
        raw = self._prompt(f"{prompt}{suffix}: ", help_text=help_text)
        return raw or default

    def _date(self, prompt: str, *, default: str) -> str:
        while True:
            value = self._text(
                prompt,
                default=default,
                help_text="Use o formato ISO YYYY-MM-DD. Ex.: 2024-01-31.",
            )
            try:
                date.fromisoformat(value)
            except ValueError:
                self._write("Data inválida. Use YYYY-MM-DD.")
                continue
            return value

    def _date_range(self, *, start_prompt: str, end_prompt: str, default_start: str, default_end: str) -> tuple[str, str]:
        while True:
            start = self._date(start_prompt, default=default_start)
            end = self._date(end_prompt, default=default_end)
            if date.fromisoformat(start) <= date.fromisoformat(end):
                return start, end
            self._write("Período inválido. A data inicial deve ser menor ou igual à data final.")

    def _confirm(self, prompt: str, *, default: bool) -> bool:
        default_hint = "S/n" if default else "s/N"
        while True:
            raw = self._prompt(
                f"{prompt} [{default_hint}]: ",
                help_text="Responda s/sim para confirmar ou n/não para cancelar.",
            ).lower()
            if not raw:
                return default
            if raw in {"s", "sim", "y", "yes"}:
                return True
            if raw in {"n", "nao", "não", "no"}:
                return False
            self._write("Responda com s ou n.")

    def _state_uf(self, prompt: str, *, required: bool, help_text: str | None = None) -> str | None:
        while True:
            raw = self._prompt(f"{prompt}{' *' if required else ''}: ", help_text=help_text).upper()
            if not raw and not required:
                return None
            if len(raw) == 2 and raw.isalpha():
                return raw
            self._write("UF inválida. Informe a sigla com 2 letras, ex.: SC.")

    def _optional_int(self, prompt: str, *, help_text: str | None = None, minimum: int | None = None) -> int | None:
        while True:
            raw = self._prompt(f"{prompt}: ", help_text=help_text)
            if not raw:
                return None
            try:
                value = int(raw)
            except ValueError:
                self._write("Número inválido. Tente novamente.")
                continue
            if minimum is not None and value < minimum:
                self._write(f"Número inválido. Informe valor maior ou igual a {minimum}.")
                continue
            return value

    def _required_int(self, prompt: str, *, help_text: str | None = None) -> int:
        while True:
            value = self._optional_int(f"{prompt} *", help_text=help_text, minimum=1)
            if value is not None:
                return value
            self._write("Campo obrigatório.")

    def _int_list(self, prompt: str, *, default: tuple[int, ...], required: bool, help_text: str | None = None) -> list[int]:
        default_text = ",".join(str(item) for item in default)
        while True:
            raw = self._prompt(f"{prompt}{' *' if required else ''} [{default_text}]: ", help_text=help_text)
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
            if any(value < 1 for value in values):
                self._write("Lista inválida. Use apenas códigos positivos.")
                continue
            if values or not required:
                return values
            self._write("Informe ao menos um código.")

    def _render_command_preview(self, argv: list[str]) -> None:
        command = ["compras-crawler", "sync", *argv]
        self._write("")
        self._write("Comando gerado:")
        self._write(f"  {shlex.join(command)}")
        self._write("")
        self._write("Resumo visual:")
        for key, value in self._summarize_argv(argv):
            self._write(f"  {key:<18} {value}")

    def _summarize_argv(self, argv: list[str]) -> list[tuple[str, str]]:
        multi: dict[str, list[str]] = {}
        flags: set[str] = set()
        index = 0
        while index < len(argv):
            token = argv[index]
            if token.startswith("--"):
                if index + 1 < len(argv) and not argv[index + 1].startswith("--"):
                    multi.setdefault(token, []).append(argv[index + 1])
                    index += 2
                    continue
                flags.add(token)
            index += 1
        rows = [
            ("DuckDB", self._one(multi, "--db-path", "-")),
            ("Ops SQLite", self._one(multi, "--ops-db-path", "automático")),
            ("Base URL", self._one(multi, "--base-url", DEFAULT_BASE_URL)),
            ("Período", f"{self._one(multi, '--start-date', '-')} → {self._one(multi, '--end-date', '-')}"),
            ("Escopo", self._one(multi, "--scope", "historical")),
            ("UF", self._one(multi, "--state-uf", "todas")),
            ("Município", self._one(multi, "--municipality-code", "-")),
            ("Operações", ", ".join(multi.get("--operation", [])) or "manifesto padrão"),
            ("Modalidades PNCP", ", ".join(multi.get("--pncp-modalidade-code", [])) or "-"),
            ("Retomada", "não" if "--no-resume" in flags else "sim"),
            ("Log/UI", f"{self._one(multi, '--log-level', 'WARNING')} / {self._one(multi, '--ui', 'auto')}"),
        ]
        if "--source" in multi:
            rows.insert(8, ("Fonte", ", ".join(multi["--source"])))
        if "--page-size" in multi:
            rows.insert(5, ("Página", self._one(multi, "--page-size", "padrão")))
        return rows

    def _one(self, values: dict[str, list[str]], key: str, default: str) -> str:
        return values.get(key, [default])[-1]
