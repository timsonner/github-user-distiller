---
name: copilot-sdk-python-distilled
description: Use when building Python agents with the GitHub Copilot SDK, especially for programmatic agent creation, skills, goals, tools, hooks, and MCP integration.
---

# GitHub Copilot SDK for Python (distilled)

Use this skill when you need to create Copilot-powered Python agents programmatically, attach tools, assign skills, encode goals, and orchestrate multi-agent workflows.

## Core concepts

- The GitHub Copilot SDK exposes a production-tested agent runtime behind the Copilot CLI.
- In Python, the main entry points are `CopilotClient`, `create_session()`, and a session object with `send_and_wait()`, `send()`, `on()`, and lifecycle helpers.
- The SDK supports tools, hooks, MCP servers, custom agents, skills, streaming events, memory, providers, and telemetry.

## Installation

```bash
pip install github-copilot-sdk
```

Optional telemetry support:

```bash
pip install "github-copilot-sdk[telemetry]"
```

## Authentication and runtime

Basic client example:

```python
import asyncio
from copilot import CopilotClient
from copilot.session import PermissionHandler

async def main():
    client = CopilotClient()
    await client.start()

    session = await client.create_session(
        on_permission_request=PermissionHandler.approve_all,
        model="gpt-5",
    )

    response = await session.send_and_wait("What is 2 + 2?")
    print(response.data.content)

    await client.stop()

asyncio.run(main())
```

## Streaming events

```python
from copilot import CopilotClient
from copilot.session_events import SessionEventType

client = CopilotClient()
await client.start()

session = await client.create_session(
    on_permission_request=PermissionHandler.approve_all,
    model="gpt-5",
    streaming=True,
)


def handle_event(event):
    if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
        print(event.data.delta_content, end="", flush=True)
    elif event.type == SessionEventType.SESSION_IDLE:
        print()

session.on(handle_event)
await session.send_and_wait("Tell me a short joke")
await client.stop()
```

## Tools

```python
from pydantic import BaseModel, Field
from copilot import CopilotClient, define_tool
from copilot.session import PermissionHandler

class LookupIssueParams(BaseModel):
    id: str = Field(description="Issue identifier")

@define_tool(description="Fetch issue details from our tracker")
async def lookup_issue(params: LookupIssueParams) -> str:
    return f"Issue {params.id} resolved"

async def main():
    async with CopilotClient() as client:
        async with await client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model="gpt-5",
            tools=[lookup_issue],
        ) as session:
            await session.send("Look up issue #123")

asyncio.run(main())
```

## Hooks

```python
async def on_pre_tool_use(input_data, invocation):
    print(f"About to run tool: {input_data['toolName']}")
    return {"permissionDecision": "allow"}

session = await client.create_session(
    on_permission_request=PermissionHandler.approve_all,
    model="gpt-5",
    hooks={"on_pre_tool_use": on_pre_tool_use},
)
```

## MCP servers

MCP servers can be attached to a session either as a remote HTTP endpoint or as a local stdio process. Pick the form that matches where your server runs.

Remote HTTP example:

```python
session = await client.create_session(
    on_permission_request=PermissionHandler.approve_all,
    model="gpt-5",
    mcp_servers={
        "github": {
            "type": "http",
            "url": "https://api.githubcopilot.com/mcp/",
            "tools": ["*"],
        }
    },
)
```

Local stdio example:

```python
session = await client.create_session(
    on_permission_request=PermissionHandler.approve_all,
    model="gpt-5",
    mcp_servers={
        "local-tools": {
            "type": "stdio",
            "command": "python",
            "args": ["-m", "my_mcp_server"],
            "tools": ["read_file", "write_file"],
        }
    },
)
```

Use the smallest tool list that you need, and pass any required auth, environment variables, or startup arguments through the server configuration.

## Custom agents

```python
session = await client.create_session(
    on_permission_request=PermissionHandler.approve_all,
    model="gpt-4.1",
    custom_agents=[
        {
            "name": "researcher",
            "display_name": "Research Agent",
            "description": "Explores codebases and answers questions using read-only tools",
            "tools": ["grep", "glob", "view"],
            "prompt": "You are a research assistant. Analyze code and answer questions. Do not modify any files.",
        },
        {
            "name": "editor",
            "display_name": "Editor Agent",
            "description": "Makes targeted code changes",
            "tools": ["view", "edit", "bash"],
            "prompt": "You are a code editor. Make minimal, surgical changes to files as requested.",
        },
    ],
)
```

## Skills

Skills are reusable prompt modules loaded from directories containing `SKILL.md` files.

```python
session = await client.create_session(
    on_permission_request=PermissionHandler.approve_all,
    model="gpt-4.1",
    skill_directories=["./skills"],
)
```

Assign skills to agents with `skills`:

```python
session = await client.create_session(
    on_permission_request=PermissionHandler.approve_all,
    model="gpt-4.1",
    skill_directories=["./skills"],
    custom_agents=[
        {
            "name": "security-auditor",
            "description": "Security-focused code reviewer",
            "prompt": "Focus on OWASP Top 10 vulnerabilities.",
            "skills": ["security-scan", "dependency-check"],
        }
    ],
)
```

## Goals and goal-driven agents

The SDK does not define a special `goal` field. Encode goals in the agent prompt or in `system_message`.

```python
async def build_agent(goal: str, tools: list | None = None):
    client = CopilotClient()
    await client.start()
    session = await client.create_session(
        on_permission_request=PermissionHandler.approve_all,
        model="gpt-4.1",
        system_message={
            "mode": "append",
            "content": f"You are a goal-driven agent. Goal: {goal}",
        },
        tools=tools or [],
    )
    return client, session
```

## Programmatic agent factory pattern

```python
async def make_specialist_agent(name: str, goal: str, skills: list[str] | None = None):
    client = CopilotClient()
    await client.start()

    session = await client.create_session(
        on_permission_request=PermissionHandler.approve_all,
        model="gpt-4.1",
        skill_directories=["./skills"],
        system_message={
            "mode": "append",
            "content": f"Goal: {goal}",
        },
        custom_agents=[
            {
                "name": name,
                "display_name": name.replace("-", " ").title(),
                "description": f"Specialist agent for: {goal}",
                "prompt": f"You are a specialist agent focused on {goal}.",
                "skills": skills or [],
            }
        ],
        agent=name,
    )
    return client, session
```

## Practical guidance

- Keep each agent focused on one responsibility.
- Restrict tools with `tools=[...]` to enforce least privilege.
- Assign skills explicitly.
- Encode goals in the prompt or system message.
- Use hooks for auditing and approval.
- Prefer custom agents over one giant monolithic session when roles differ.
