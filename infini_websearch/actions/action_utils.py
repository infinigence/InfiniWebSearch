import json
import re
from typing import Dict, List, Optional, Tuple, Union


def parse_function_call_from_model_ouput(
    output: str,
    registered_function_names: Optional[List[str]],
    speical_tokens_map: Optional[Dict],
) -> Tuple[Optional[str], Union[Dict, Optional[str]]]:
    if speical_tokens_map is None:
        speical_tokens_map = dict(
            function_start_token="<|function_start|>",
            function_end_token="<|function_end|>",
        )

    function_name, function_arguments = None, None
    function_call_texts = re.findall(
        f'{re.escape(speical_tokens_map["function_start_token"])}(.*?){re.escape(speical_tokens_map["function_end_token"])}',  # noqa: E501
        output,
        re.DOTALL,
    )
    if len(function_call_texts) > 0:
        # support only one action per turn, choose the first one
        function_call_text = function_call_texts[0].strip()
        try:
            function_call_dict = json.loads(function_call_text)
            function_name = function_call_dict["name"]
            function_arguments = function_call_dict["arguments"]
        except Exception as e:
            print(e)
            function_name = None
            print("function call json输入格式错误")
            print(function_call_text)

    if function_name is not None and function_name not in registered_function_names:
        function_arguments = f"{function_name}不在可以使用的工具列表中"
        function_name = None
    return function_name, function_arguments
