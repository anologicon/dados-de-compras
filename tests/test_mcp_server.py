from __future__ import annotations

import asyncio
from datetime import timedelta
import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("mcp", reason='Install the optional extra with pip install -e ".[mcp]"')

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from compras_crawler import cli, mcp_server
from compras_crawler.project_access import ProjectAccess


@pytest.mark.parametrize("entrypoint,args", [(mcp_server.main, []), (cli.main, ["mcp"])])
def test_entrypoints_use_stdio(monkeypatch, tmp_path: Path, capsys, entrypoint, args):
    captured = {}

    class DummyServer:
        def run(self, **kwargs):
            captured.update(kwargs)

    def fake_create_server(db_path, ops_db_path, project_root):
        captured.update(db_path=db_path, ops_db_path=ops_db_path, project_root=project_root)
        return DummyServer()

    monkeypatch.setattr(mcp_server, "create_server", fake_create_server)
    monkeypatch.setattr(cli, "load_dotenv", lambda **kwargs: pytest.fail("MCP must not load .env"))
    assert entrypoint([*args, "--db-path", str(tmp_path / "data.duckdb"), "--project-root", str(tmp_path)]) == 0
    assert captured["transport"] == "stdio"
    assert captured["db_path"] == tmp_path / "data.duckdb"
    assert captured["project_root"] == tmp_path
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("with_data", [True, False])
def test_real_stdio_protocol(project_access: ProjectAccess, tmp_path: Path, with_data: bool):
    db_path = project_access.db_path if with_data else tmp_path / "missing.duckdb"
    ops_path = project_access.ops_db_path if with_data else tmp_path / "missing.sqlite"

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m", "compras_crawler.mcp_server",
                "--db-path", str(db_path),
                "--ops-db-path", str(ops_path),
                "--project-root", str(project_access.project_root),
            ],
            cwd=str(tmp_path),
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as session:
                result = await session.initialize()
                assert result.serverInfo.name == "compras-crawler"
                tools = (await session.list_tools()).tools
                assert {tool.name for tool in tools} == {
                    "get_project_info", "read_document", "list_operations", "get_database_schema",
                    "list_entities", "search_records", "get_record", "list_sync_runs",
                    "list_checkpoints", "list_sync_errors",
                }
                assert all(tool.annotations.readOnlyHint for tool in tools)
                assert all(tool.annotations.openWorldHint is False for tool in tools)
                assert all(tool.inputSchema["type"] == "object" for tool in tools)
                info = await session.call_tool("get_project_info", {})
                assert not info.isError
                assert info.structuredContent["read_only"] is True
                if not with_data:
                    assert info.structuredContent["warehouse"]["exists"] is False
                    missing = await session.call_tool("list_entities", {})
                    assert missing.isError
                    assert "--db-path" in missing.content[0].text
                    docs = await session.call_tool("read_document", {"document": "readme"})
                    assert not docs.isError
                    assert not (await session.call_tool("list_operations", {})).isError
                    assert not db_path.exists()
                    assert not ops_path.exists()
                    return
                search = await session.call_tool("search_records", {"entity_name": "uasg", "query": "Paulo"})
                assert not search.isError
                assert search.structuredContent["items"][0]["payload"]["codigoUasg"] == 1
                assert search.structuredContent["items"][0]["source_page"] == 1
                for name in ("list_operations", "get_database_schema", "list_entities", "list_sync_runs", "list_checkpoints", "list_sync_errors"):
                    response = await session.call_tool(name, {})
                    assert not response.isError, response
                record = await session.call_tool("get_record", {"entity_name": "uasg", "record_key": "missing"})
                assert record.structuredContent == {"record": None}
                invalid = await session.call_tool("search_records", {"entity_name": "uasg", "limit": 101})
                assert invalid.isError
                forbidden = await session.call_tool("read_document", {"document": "../.env"})
                assert forbidden.isError
                # A tool error does not terminate the MCP session.
                document = await session.call_tool("read_document", {"document": "readme", "line_count": 1})
                assert document.structuredContent["next_line"] == 2
                resources = (await session.list_resources()).resources
                assert {str(resource.uri) for resource in resources} == {
                    "compras://project/readme", "compras://project/api-reference",
                    "compras://project/schema", "compras://project/operations",
                }
                for resource in resources:
                    read_result = await session.read_resource(resource.uri)
                    assert read_result.contents
                    if resource.mimeType == "application/json":
                        json.loads(read_result.contents[0].text)

    asyncio.run(asyncio.wait_for(exercise(), timeout=30))
