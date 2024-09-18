from functools import partial
from typing import Callable, Dict, Generator, List, Union

import openai


def get_vllm_model_output_function(
    url: str,
    model_name: str,
    chat_mode: bool,
    model_config: Dict,
    stream: bool,
    buffer_size: int = 20,
    timeout: int = 60,
) -> Callable:
    """
    Get model generate function: streaming/non-streaming
    """
    data = {
        "model": model_name,
        "stream": stream,
        **model_config,
    }

    openai.api_key = "EMPTY"
    openai.base_url = url
    openai.proxy = ""
    chat_func = (
        openai.chat.completions.create
        if chat_mode is True
        else openai.completions.create
    )

    if stream is True:
        return partial(
            get_model_streaming_output,
            llm_function=chat_func,
            model_config=data,
            chat_mode=chat_mode,
            buffer_size=buffer_size,
            timeout=timeout,
        )
    else:
        return partial(
            get_model_output,
            llm_function=chat_func,
            model_config=data,
            chat_mode=chat_mode,
            timeout=timeout,
        )


def get_model_streaming_output(
    messages: List[Union[Dict, str]],
    model_config: Dict,
    llm_function: Callable,
    chat_mode: bool,
    buffer_size: int,
    timeout: int,
) -> Generator[str, None, None]:
    if chat_mode is True:
        model_config["messages"] = messages
    else:
        model_config["prompt"] = messages
    buffer = ""
    for chunk in llm_function(**model_config, timeout=timeout):
        if chunk.choices[0].delta.content:
            buffer += chunk.choices[0].delta.content
            if len(buffer) >= buffer_size:
                # '[citation:x]' has been truncated?
                if buffer.rfind("]") < buffer.rfind("["):
                    yield buffer[: buffer.rfind("[")]
                    buffer = buffer[buffer.rfind("[") :]  # noqa: E203
                else:
                    yield buffer
                    buffer = ""
    if buffer:
        yield buffer


def get_model_output(
    messages: List[Union[Dict, str]],
    model_config: Dict,
    llm_function: Callable,
    chat_mode: bool,
    timeout: int,
) -> str:
    if chat_mode is True:
        model_config["messages"] = messages
    else:
        model_config["prompt"] = messages
    response = llm_function(**model_config, timeout=timeout)
    return response
