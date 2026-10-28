# -*- coding: utf-8 -*-
"""Builds the AgentScope ReAct agent that powers Exhibit."""

from __future__ import annotations

from agentscope.agent import Agent, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.model import OpenAIChatModel
from agentscope.permission import PermissionBehavior, PermissionRule
from agentscope.tool import Toolkit

from .config import Config
from .permissions import FileEditor
from .prompt_loader import get_chat_prompt, get_system_prompt
from .tools import build_edit_tools, build_fs_tools, build_git_tools
from .session import Session

# Edit tools only stage a preview; ``FileEditor`` asks the user before writing.
STAGED_EDIT_TOOLS = ("write_file", "replace_in_file", "create_directory")


def _allow_staged_edits(agent: Agent) -> None:
    """Let staged edit tools run; Exhibit confirms through ``FileEditor``.

    AgentScope asks for confirmation on every non-read-only tool by default,
    which parks the reply on ``REQUIRE_USER_CONFIRM`` before the tool body
    runs. Exhibit already gates writes in ``FileEditor``, so the framework
    prompt would otherwise leave edits permanently unexecuted.
    """
    context = agent.state.permission_context
    for name in STAGED_EDIT_TOOLS:
        context.allow_rules.setdefault(name, []).append(
            PermissionRule(
                tool_name=name,
                rule_content=None,
                behavior=PermissionBehavior.ALLOW,
                source="exhibit",
            )
        )


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
        parameters=OpenAIChatModel.Parameters(
            max_tokens=config.max_output_tokens,
        ),
    )
    toolkit = Toolkit(tools=[*build_fs_tools(), *build_git_tools()])
    return Agent(
        name="Exhibit",
        system_prompt=get_system_prompt(task),
        model=model,
        toolkit=toolkit,
        react_config=ReActConfig(max_iters=config.max_iters),
    )


def build_chat_agent(
    config: Config,
    history: list[dict[str, str]],
    *,
    mode: str = "agent",
    editor: FileEditor | None = None,
    session: Session | None = None,
) -> Agent:
    """Create a chat agent whose context is supplied for this turn."""
    credential = OpenAICredential(
        api_key=config.api_key,
        base_url=config.base_url,
    )
    model = OpenAIChatModel(
        credential=credential,
        model=config.model,
        stream=True,
        parameters=OpenAIChatModel.Parameters(
            max_tokens=config.max_output_tokens,
        ),
    )
    context = "\n\n".join(
        f"{item['role']}: {item['content']}" for item in history[-20:]
    )
    on_read = session.record_read if session is not None else None
    fs_tools = build_fs_tools(on_read=on_read)
    toolkit = Toolkit(tools=[*fs_tools, *build_git_tools()])
    if mode == "agent" and editor is not None:
        toolkit = Toolkit(
            tools=[
                *fs_tools,
                *build_git_tools(),
                *build_edit_tools(editor),
            ]
        )
    system_prompt = get_chat_prompt(mode=mode, context=context)
    agent = Agent(
        name="Exhibit",
        system_prompt=system_prompt,
        model=model,
        toolkit=toolkit,
        react_config=ReActConfig(max_iters=config.max_iters),
    )
    if mode == "agent" and editor is not None:
        _allow_staged_edits(agent)
    return agent
