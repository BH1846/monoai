"""MCP tool-argument firewall rules (Phase 4): a distinct, simpler rule
shape from core/policy's SpanLabel-keyed Policy -- here an action is
assigned per (tool_name, arg_name) pair directly:

    tools:
      bash:
        args:
          command: BLOCK
      web_search:
        args:
          query: REVERSIBLE

core/detect still does the actual scanning (scanner.py); this module
only answers "what action applies to this tool's this argument."
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

ToolAction = Literal["BLOCK", "REVERSIBLE", "PRESERVE"]

# Fail-open for any (tool, arg) pair not explicitly listed -- an
# unconfigured tool shouldn't silently become unusable, and PRESERVE
# still gets scanned (see scanner.py) so it's visible in audit, just
# never blocks or rewrites.
DEFAULT_ACTION: ToolAction = "PRESERVE"


class ToolArgsConfig(BaseModel):
    args: dict[str, ToolAction] = Field(default_factory=dict)


class ToolFirewallConfig(BaseModel):
    tools: dict[str, ToolArgsConfig] = Field(default_factory=dict)

    def action_for(self, tool_name: str, arg_name: str) -> ToolAction:
        tool_cfg = self.tools.get(tool_name)
        if tool_cfg is None:
            return DEFAULT_ACTION
        return tool_cfg.args.get(arg_name, DEFAULT_ACTION)

    @classmethod
    def load(cls, path: str | Path) -> "ToolFirewallConfig":
        raw = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        return cls(**data)

    @classmethod
    def empty(cls) -> "ToolFirewallConfig":
        return cls()
