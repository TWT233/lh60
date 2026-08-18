from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class McpClient:
    def __init__(self, binary: Path, config: Path) -> None:
        self.process = subprocess.Popen(
            [str(binary), "--config", str(config)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
        )
        self.next_id = 1
        self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "lh60-production", "version": "1"},
            },
        )
        self.notify("notifications/initialized")

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        if not self.process.stdin or not self.process.stdout:
            raise RuntimeError("Konnect stdio is unavailable")
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()
        while line := self.process.stdout.readline():
            response = json.loads(line)
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise RuntimeError(response["error"])
            return response["result"]
        raise RuntimeError("Konnect closed stdout")

    def notify(self, method: str) -> None:
        if not self.process.stdin:
            raise RuntimeError("Konnect stdin is unavailable")
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.process.stdin.flush()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            text = result.get("content", [{}])[0].get("text", result)
            raise RuntimeError(f"{name} failed: {text}")
        return result

    @staticmethod
    def result_json(result: dict[str, object]) -> dict[str, object]:
        if result.get("isError"):
            raise RuntimeError(result)

        for block in result.get("content", []):
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            try:
                value = json.loads(block["text"])
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise RuntimeError("tool result text block is not valid JSON") from error
            if isinstance(value, dict):
                return value
            raise RuntimeError("tool result text block is not a JSON object")

        raise RuntimeError("tool result has no JSON object text block")

    def call_tool_json(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.result_json(self.call_tool(name, arguments))

    def tool_schemas(self, toolset: str) -> dict[str, dict[str, Any]]:
        self.call_tool("load_toolset", {"name": toolset})
        tools = self.request("tools/list", {})["tools"]
        return {tool["name"]: tool["inputSchema"] for tool in tools}

    def close(self) -> None:
        self.process.terminate()
        self.process.wait(timeout=5)

    def __enter__(self) -> "McpClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
