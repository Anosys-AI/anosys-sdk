"""
AnoSys + Claude Agent SDK example.

    pip install anosys-sdk-claude-agents
    export ANOSYS_API_KEY=... ANTHROPIC_API_KEY=...
    python anosys_claude_agent.py
"""

import asyncio

from anosys_sdk_claude_agents import AnosysClaudeAgentsLogger

# Initialize once, before importing query
AnosysClaudeAgentsLogger(agent_name="repo_explorer")

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query  # noqa: E402


async def main():
    options = ClaudeAgentOptions(allowed_tools=["Bash", "Read", "Glob"], max_turns=5)
    async for message in query(prompt="How many Python files are in this folder?", options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)
        elif isinstance(message, ResultMessage):
            print(f"Done in {message.num_turns} turns, ${message.total_cost_usd or 0:.4f}")


asyncio.run(main())
