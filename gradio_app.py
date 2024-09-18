import argparse
import os
from typing import Dict, Generator, List, Optional, Tuple

import gradio as gr
from gradio_toggle import Toggle
from transformers import AutoTokenizer

from infini_websearch.actions import GoogleSearch, parse_function_call_from_model_ouput
from infini_websearch.configs import (
    AGENT_MAX_OUTPUT_TOKENS,
    AGENT_TEMPERATURE,
    CHAT_MAX_OUTPUT_TOKENS,
    CHAT_TEMPERATURE,
    CSS_STYLE,
    FUNCTION_CALLING_PROMPT_TEMPLATE,
    FUNCTION_END_TOKEN,
    FUNCTION_START_TOKEN,
    MAX_ACTION_TURNS,
    MODEL_NAME,
    MODEL_SERVER_URL,
    NUM_SEARCH_WEBPAGES,
    OBSERVATION_PROMPT_TEMPLATE,
    PROXIES,
    ROLE_PROMPT,
    SEARCH_SERVER_URL,
    SESSION_MAX_INPUT_TOKENS,
    SESSION_WINDOW_SIZE,
    STOP_TOKENS,
    SUMMARY_PROMPT_TEMPLATE,
    TIME_PROMPT_TEMPLATE,
    WEBPAGE_LOAD_TIMETOUT,
    WEBPAGE_SUMMARY_MAX_INPUT_TOKENS,
    WEBPAGE_SUMMARY_MAX_OUTPUT_TOKENS,
)
from infini_websearch.model import (
    get_vllm_model_output_function,
    include_special_tokens,
    split_text_by_special_token,
)
from infini_websearch.utils import (
    extract_citations,
    format_search_results,
    functions2str,
    get_datetime_now,
)

parser = argparse.ArgumentParser()
parser.add_argument("--model-path", "-m", type=str)
parser.add_argument("--port", type=int, default=7860)

args = parser.parse_args()

MODEL_PATH = args.model_path
SERVER_PORT = args.port

# tokenizer
os.environ["TOKENIZERS_PARALLELISM"] = "false"
TOKENIZER = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)


# function name -> action
ACTIONS_MAP = {
    "googleWebSearch": GoogleSearch(
        server_url=SEARCH_SERVER_URL,
        num_search_webpages=NUM_SEARCH_WEBPAGES,
        summary_prompt_template=SUMMARY_PROMPT_TEMPLATE,
        observation_prompt_template=OBSERVATION_PROMPT_TEMPLATE,
        webpage_summary_max_input_tokens=WEBPAGE_SUMMARY_MAX_INPUT_TOKENS,
        webpage_load_timetout=WEBPAGE_LOAD_TIMETOUT,
        proxies=PROXIES,
    ),
}
# tool -> function name
TOOLS_TO_ACTION_NAMES = {
    "websearch": "googleWebSearch",
}


def get_system_prompt(functions: Optional[List] = None) -> str:
    """
    Get system prompt for current conversation.
    """
    if functions is None:
        functions = []
    current_time, weekday = get_datetime_now()
    time_info = TIME_PROMPT_TEMPLATE.format(current_time=current_time, weekday=weekday)
    system_prompt = ROLE_PROMPT + "\n" + time_info
    if len(functions) > 0:
        system_prompt += "\n" + FUNCTION_CALLING_PROMPT_TEMPLATE.format(
            functions=functions2str(functions)
        )
    return system_prompt


def user(
    user_message: str, history: List[Dict], session_state: gr.State
) -> Tuple[str, List[Dict], gr.State]:
    """
    Add user input message to history.
    """
    session_state["messages"] += [{"role": "user", "content": user_message}]
    return "", history + [{"role": "user", "content": user_message}], session_state


def bot(
    history: List[Dict],
    websearch: bool,
    session_state: gr.State,
) -> Generator[List[Dict], None, None]:
    """
    Main workflow.
    """
    # get registered tools
    registered_tools = []
    if websearch is True:
        registered_tools.append("websearch")
        temperature = AGENT_TEMPERATURE
        max_gen_length = AGENT_MAX_OUTPUT_TOKENS
    else:
        temperature = CHAT_TEMPERATURE
        max_gen_length = CHAT_MAX_OUTPUT_TOKENS
    registered_function_names = [
        TOOLS_TO_ACTION_NAMES[tool] for tool in registered_tools
    ]
    registered_functions = [
        ACTIONS_MAP[function_name] for function_name in registered_function_names
    ]
    functions = [
        function.function_defination
        for function in registered_functions
        if function.function_defination is not None
    ]

    # get system prompt
    system_prompt = get_system_prompt(functions=functions)
    # get model streaming output function
    llm_streaming_output_func = get_vllm_model_output_function(
        url=MODEL_SERVER_URL,
        model_name=MODEL_NAME,
        chat_mode=True,
        stream=True,
        model_config={
            "temperature": temperature,
            "max_tokens": max_gen_length,
            "stop": STOP_TOKENS,
        },
    )

    input_dict = {
        "temperature": temperature,
        "max_gen_length": max_gen_length,
        "use_websearch": "websearch" in registered_tools,
        "MODEL_NAME": MODEL_NAME,
    }

    for _ in range(MAX_ACTION_TURNS * 2):
        # ASSISTANT answers two times per action turn
        # answer1: <|function_start|>xxx<|function_end|>
        # answer2: observation -> final answer

        """
        retain SESSION_WINDOW_SIZE turns (max_sequence_length is short -> 4096)
        """
        messages_truncated = truncate_messages(
            messages=session_state["messages"],
            tokenizer=TOKENIZER,
            session_window_size=SESSION_WINDOW_SIZE,
            max_input_tokens=SESSION_MAX_INPUT_TOKENS,
            system_prompt=system_prompt,
        )

        messages_input = [
            {"role": "system", "content": system_prompt}
        ] + messages_truncated
        input_dict.update(dict(messages=messages_input))
        # print input prompt
        print(
            TOKENIZER.apply_chat_template(
                messages_input, tokenize=False, add_generation_prompt=True
            )
        )

        response_raw = ""
        response_gradio = ""
        """
        streaming output status:
            1. [chat]: generating chat message
            2. [function start]: start generating function calling information ([chat] -> [function])
            3. [function]: generating function calling information
            4. [function end]: end generating function calling information ([function] -> [chat])
        """
        # in [function] status?
        function_status = False
        chunk_buffer = ""
        for chunk in llm_streaming_output_func(messages=input_dict["messages"]):
            chunk_buffer += chunk
            # '<|function_start|>' and '<|function_end|>' appear to be truncated ?
            if chunk_buffer.rfind("|>") < chunk_buffer.rfind("<|"):
                continue
            # [function start] status: ([chat] -> [function])
            if function_status is False and include_special_tokens(
                chunk_buffer, [FUNCTION_START_TOKEN]
            ):
                function_status = True
                chat_part, tool_part = split_text_by_special_token(
                    chunk_buffer, FUNCTION_START_TOKEN
                )
                tool_part = FUNCTION_START_TOKEN + tool_part
                # add chat message to history
                if len(response_gradio + chat_part) > 0:
                    history.append(
                        {"role": "assistant", "content": response_gradio + chat_part}
                    )
                response_gradio = tool_part
                response_raw += chat_part + tool_part
                chunk_buffer = ""
                yield history + [
                    {
                        "role": "assistant",
                        "content": response_gradio,
                        "metadata": {"title": "tool parameters"},
                    }
                ]
            # [function end] status: ([function] -> [chat])
            elif function_status is True and include_special_tokens(
                chunk_buffer, [FUNCTION_END_TOKEN]
            ):
                chat_part, _ = split_text_by_special_token(
                    chunk_buffer, FUNCTION_END_TOKEN
                )
                response_gradio += chat_part + FUNCTION_END_TOKEN
                response_raw += chat_part + FUNCTION_END_TOKEN
                chunk_buffer = ""
                history.append(
                    {
                        "role": "assistant",
                        "content": response_gradio,
                        "metadata": {"title": "tool parameters"},
                    }
                )
                yield history
                break
            # [function] status
            elif function_status is True:
                response_gradio += chunk_buffer
                response_raw += chunk_buffer
                chunk_buffer = ""
                yield history + [
                    {
                        "role": "assistant",
                        "content": response_gradio,
                        "metadata": {"title": "tool parameters"},
                    }
                ]
            # [chat] status
            elif function_status is False:
                citations = extract_citations(chunk_buffer)
                if len(citations) > 0 and len(session_state["url_infos"]) > 0:
                    chunk_new = chunk_buffer
                    for citation in citations:
                        url_ind = int(citation) - 1
                        # hardcoding for out-of-bounds
                        if url_ind < 0:
                            url_ind = 0
                        elif url_ind >= len(session_state["url_infos"]):
                            url_ind = len(session_state["url_infos"]) - 1
                        # Add a space before the <a> tag to prevent rendering
                        # errors when multiple <a></a> tags are adjacent to
                        # each other.
                        chunk_new = chunk_new.replace(
                            f"[citation:{citation}]",
                            f' <a href="{session_state["url_infos"][url_ind]["link"]}" class="circle-link">{citation}</a>',  # noqa: E501
                        )
                    response_gradio += chunk_new
                else:
                    response_gradio += chunk_buffer
                response_raw += chunk_buffer

                chunk_buffer = ""
                yield history + [{"role": "assistant", "content": response_gradio}]

                if session_state["stop_generation"] is True:
                    session_state["stop_generation"] = False
                    break

        # if streaming ends with [chat] status, add response to history
        if not include_special_tokens(response_gradio, FUNCTION_END_TOKEN):
            history.append({"role": "assistant", "content": response_gradio})

        session_state["messages"].append({"role": "assistant", "content": response_raw})

        # no tool registered, end this turn
        if len(registered_tools) == 0:
            break

        function_name, function_arguments = parse_function_call_from_model_ouput(
            response_raw,
            registered_function_names,
            speical_tokens_map=dict(
                function_start_token=FUNCTION_START_TOKEN,
                function_end_token=FUNCTION_END_TOKEN,
            ),
        )

        # no tool use this turn, end this turn
        if function_arguments is None:
            break

        # something is wrong, use function_arguments as observation (error
        # message)
        if function_name is None and isinstance(function_arguments, str):
            history.append({"role": "observation", "content": function_arguments})
            session_state["messages"].append(
                {"role": "observation", "content": function_arguments}
            )
            continue

        url_infos, html_contents = [], []
        latest_tool_response = None
        action = ACTIONS_MAP[function_name]
        observation = None
        if function_name == "googleWebSearch":
            observation_genrator = action.run(
                user_question=session_state["messages"][-2]["content"],
                arguments=function_arguments,
                llm_completion_funcion=get_vllm_model_output_function(
                    url=MODEL_SERVER_URL,
                    model_name=MODEL_NAME,
                    chat_mode=False,
                    stream=False,
                    model_config={
                        "temperature": temperature,
                        "max_tokens": WEBPAGE_SUMMARY_MAX_OUTPUT_TOKENS,
                        "stop": STOP_TOKENS,
                    },
                ),
                tokenizer=TOKENIZER,
                return_webpage_details=True,
            )
            for item in gr.Progress().tqdm(observation_genrator, desc="summarizing..."):
                if isinstance(item, dict):
                    if "observation" in item:
                        observation = item["observation"]
                        break
                    url_infos.append(item["url_info"])
                    html_contents.append(item["html_content"])
                    yield history + [
                        {
                            "role": "assistant",
                            "content": format_search_results(url_infos),
                            "metadata": {"title": "tool results"},
                        }
                    ]
                # error message
                elif isinstance(item, str):
                    latest_tool_response = item
                    yield history + [
                        {
                            "role": "assistant",
                            "content": latest_tool_response,
                            "metadata": {"title": "tool results"},
                        }
                    ]
                else:
                    raise NotImplementedError

            if len(url_infos) > 0:
                history.append(
                    {
                        "role": "assistant",
                        "content": format_search_results(url_infos),
                        "metadata": {"title": "tool results"},
                    }
                )
            else:
                history.append(
                    {
                        "role": "assistant",
                        "content": latest_tool_response,
                        "metadata": {"title": "tool results"},
                    }
                )

            # update url_infos
            session_state["url_infos"] = url_infos
        else:
            observation = action.run(function_arguments)

        assert observation is not None
        history.append({"role": "observation", "content": observation})
        session_state["messages"].append(
            {"role": "observation", "content": observation}
        )


def truncate_messages(
    messages: List[Dict],
    tokenizer: AutoTokenizer,
    session_window_size: int,
    max_input_tokens: int,
    system_prompt: str,
) -> List[Dict]:
    """
    truncate messages for model input by session_window_size and max_input_tokens
    """
    # get parts for each turn
    turn_start_inds = []
    for ind, message in enumerate(messages):
        if message["role"] == "user":
            turn_start_inds.append(ind)
    # only latest turns are used as input
    turn_start_inds_used = turn_start_inds[-session_window_size:]
    messages_parts = []
    for i in range(len(turn_start_inds_used)):
        turn_start_ind = turn_start_inds_used[i]
        turn_end_ind = (
            len(messages)
            if i + 1 >= len(turn_start_inds_used)
            else turn_start_inds_used[i + 1]
        )
        messages_parts.append(messages[turn_start_ind:turn_end_ind])
    # truncate by max_input_tokens
    messages_truncated = []
    for i, messages_part in enumerate(reversed(messages_parts)):
        if (
            i == 0
            or len(
                tokenizer.apply_chat_template(
                    [{"role": "system", "content": system_prompt}]
                    + messages_truncated
                    + messages_part,
                    tokenize=True,
                )
            )
            < max_input_tokens
        ):
            messages_truncated = messages_part + messages_truncated
        else:
            break
    return messages_truncated


def stop_response(session_state: gr.State) -> gr.State:
    session_state["stop_generation"] = True
    return session_state


def clear(history: List[Dict], session_state: gr.State) -> Tuple[List[Dict], gr.State]:
    session_state["messages"] = []
    session_state["url_infos"] = []
    session_state["stop_generation"] = False
    return [], session_state


def toggle_change(session_state: gr.State) -> gr.State:
    session_state["messages"] = []
    return session_state


with gr.Blocks(
    css=CSS_STYLE, fill_height=True, elem_classes="canvas", theme=gr.themes.Monochrome()
) as demo:
    # chatbot interface
    with gr.Row(equal_height=False, variant="compact"):
        with gr.Column(scale=1.0, elem_classes="fullheight"):
            chatbot = gr.Chatbot(
                type="messages", elem_classes="chatbot", label="infini-websearch"
            )

    # conversation state vars
    session_state = gr.State(
        dict(
            messages=[],
            url_infos=[],
            stop_generation=False,
        )
    )
    toggle_is_interactive = gr.State(value=True)

    # bottom bar
    with gr.Group(elem_classes="bottom-bar") as bottom_bar:
        msg = gr.Textbox(label="question")
        with gr.Row():
            clear_btn = gr.Button("Clear")
            stop_btn = gr.Button("Stop")

    # toggle
    with gr.Group() as toggle_group:
        websearch = Toggle(
            label="websearch",
            value=True,
            interactive=True,
        )

    websearch.change(toggle_change, [session_state], [session_state])
    msg.submit(
        user, [msg, chatbot, session_state], outputs=[msg, chatbot, session_state]
    ).then(
        bot,
        [chatbot, websearch, session_state],
        outputs=[chatbot],
        concurrency_limit=2,
    )
    clear_btn.click(clear, [chatbot, session_state], outputs=[chatbot, session_state])
    stop_btn.click(stop_response, [session_state], outputs=[session_state], queue=False)


if __name__ == "__main__":
    demo.launch(share=False, server_port=SERVER_PORT)
