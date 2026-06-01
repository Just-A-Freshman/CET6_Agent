import openai
from openai.types.chat import ChatCompletionMessageParam
from runtime import Args
from typings.LLM_call.LLM_call import Input, Output
from typings.LLM_call.LLM_call import Thinking_info
from typing import Optional, Dict, Tuple, Any


def call_llm(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    base_url: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    enable_thinking: bool = False,
) -> Tuple[str, Thinking_info]:
    
    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url if base_url else "https://api.openai.com/v1",
    )

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    if enable_thinking:
        thinking_param = {"type": "enabled"}
    else:
        thinking_param = {"type": "disabled"}

    extra_body: Dict[str, Any] = {"thinking": thinking_param}

    params: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "extra_body": extra_body,
    }
    if reasoning_effort is not None:
        params["reasoning_effort"] = reasoning_effort

    response = client.chat.completions.create(**params)

    choice = response.choices[0]
    content = choice.message.content

    reasoning_content: Optional[str] = ""
    reasoning_tokens: Optional[int] = 0
    note: Optional[str] = ""
    
    msg = choice.message
    if hasattr(msg, "reasoning_content"):
        reasoning_content = msg.reasoning_content
    elif hasattr(msg, "thinking"):
        thinking_data = msg.thinking
        reasoning_content = str(thinking_data) if thinking_data else ""

    if response.usage and response.usage.completion_tokens_details:
        details = response.usage.completion_tokens_details
        if hasattr(details, "reasoning_tokens"):
            reasoning_tokens = details.reasoning_tokens

    if reasoning_content == "" and reasoning_tokens == 0:
        note = "No explicit thinking info in response."

    thinking_info = Thinking_info(
        reasoning_content=reasoning_content if reasoning_content else "",
        reasoning_tokens=reasoning_tokens if reasoning_tokens else 0,
        note=note,
    )

    return content, thinking_info


def handler(args: Args[Input]) -> Output:
    content, thinking_info = call_llm(
        api_key=args.input.api_key,
        model=args.input.model,
        system_prompt=args.input.system_prompt,
        user_prompt=args.input.user_prompt,
        temperature=getattr(args.input, "temperature", 0.7),
        max_tokens=getattr(args.input, "max_tokens", None),
        base_url=getattr(args.input, "base_url", None),
        reasoning_effort=getattr(args.input, "reasoning_effort", None),
        enable_thinking=getattr(args.input, "enable_thinking", False),
    )
    return Output(content=content, thinking_info=thinking_info)