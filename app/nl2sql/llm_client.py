"""
Provider-agnostic structured-output LLM call.

Both providers are driven through their native tool/function-calling
mechanism rather than "please respond with JSON" prompting — that's what
makes `sql`/`confidence`/`answerable` reliably parseable instead of
occasionally wrapped in prose or markdown fences.
"""
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings


class LLMError(RuntimeError):
    """Raised when the LLM call fails or returns something we can't parse."""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def generate_structured(
    system_prompt: str,
    user_prompt: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        return _generate_anthropic(
            settings, system_prompt, user_prompt, tool_name, tool_description, input_schema
        )
    return _generate_openai(
        settings, system_prompt, user_prompt, tool_name, tool_description, input_schema
    )


def _generate_anthropic(
    settings, system_prompt, user_prompt, tool_name, tool_description, input_schema
) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.llm_model_anthropic,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": input_schema,
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    raise LLMError(f"Anthropic response had no '{tool_name}' tool_use block: {response.content}")


def _generate_openai(
    settings, system_prompt, user_prompt, tool_name, tool_description, input_schema
) -> dict[str, Any]:
    import json

    import openai

    client = openai.OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.llm_model_openai,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_description,
                    "parameters": input_schema,
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": tool_name}},
    )
    message = response.choices[0].message
    if not message.tool_calls:
        raise LLMError(f"OpenAI response had no tool call: {message.content}")
    call = message.tool_calls[0]
    if call.function.name != tool_name:
        raise LLMError(f"OpenAI called unexpected tool {call.function.name!r}")
    return json.loads(call.function.arguments)
