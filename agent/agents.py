# -*- coding: utf-8 -*-
"""Builds the AgentScope ReAct agent that powers Exhibit."""

from __future__ import annotations

from agentscope.agent import Agent, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.model import OpenAIChatModel
from agentscope.tool import Toolkit

from .config import Config
from .prompt_loader import get_system_prompt
from .tools import build_fs_tools, build_git_tools


def build_agent(
    task: str,
    config: Config,
    model_name: str | None = None,
) -> Agent:
    """Create an Exhibit agent bound to the given task and model backend.

    Args:
        task: One of the task names in ``agent.protocol.TASKS``.
        config: The runtime configuration.
        model_name: Optional model override, defaults to ``config.model``.
    """
    credential = OpenAICredential(
        api_key=config.api_key,
        base_url=config.base_url,
    )
    model = OpenAIChatModel(
        credential=credential,
        model=model_name or config.model,
        stream=True,
    )
    toolkit = Toolkit(tools=[*build_fs_tools(), *build_git_tools()])
    return Agent(
        name="Exhibit",
        system_prompt=get_system_prompt(task),
        model=model,
        toolkit=toolkit,
        react_config=ReActConfig(max_iters=config.max_iters),
    )
