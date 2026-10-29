"""
AnoSys + Anthropic (Claude) client SDK example.

    pip install anosys-sdk-anthropic
    export ANOSYS_API_KEY=... ANTHROPIC_API_KEY=...
    python anosys_claude_chat.py
"""

import anthropic
from anosys_sdk_anthropic import AnosysAnthropicLogger

# Initialize once, before creating clients
AnosysAnthropicLogger()

client = anthropic.Anthropic()

# A plain call
message = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=512,
    system="You are a concise assistant.",
    messages=[{"role": "user", "content": "Give me three facts about the Moon."}],
)
print(message.content[0].text)

# A streamed call (captured with its final usage)
with client.messages.stream(
    model="claude-sonnet-4-5",
    max_tokens=256,
    messages=[{"role": "user", "content": "Write a haiku about observability."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
print()
