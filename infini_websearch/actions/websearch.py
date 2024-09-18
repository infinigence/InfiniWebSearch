import json
from typing import Callable, Dict, Generator, List, Optional

import requests
from transformers import AutoTokenizer

from infini_websearch.actions.base_action import BaseAction


class GoogleSearch(BaseAction):
    def __init__(
        self,
        server_url: str,
        summary_prompt_template: str,
        observation_prompt_template: str,
        num_search_webpages: int = 5,
        webpage_summary_max_input_tokens: int = 2048,
        webpage_load_timetout: float = 10.0,
        proxies: Optional[Dict] = None,
    ) -> None:
        self.server_url = server_url
        self.summary_prompt_template = summary_prompt_template
        self.observation_prompt_template = observation_prompt_template
        self.num_search_webpages = num_search_webpages
        self.webpage_summary_max_input_tokens = webpage_summary_max_input_tokens
        self.webpage_load_timetout = webpage_load_timetout
        if proxies is None:
            proxies = {"http": None, "https": None}
        self.proxies = proxies

    @property
    def function_defination(self) -> Optional[Dict]:
        return {
            "name": "googleWebSearch",
            "description": (
                "A Google Search Engine. "
                "Useful when you need to search information you don't know such as weather, "
                "exchange rate, current events."
                "Never ever use this tool when user want to translate"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Content that users want to search for, such as 'weather', 'current events', etc."
                            "If special characters such as '\n' appear in the search, "
                            "these special characters must be ignored."
                        ),
                    }
                },
                "required": ["query"],
            },
        }

    def run(
        self,
        user_question: str,
        arguments: Dict,
        llm_completion_funcion: Callable,
        tokenizer: AutoTokenizer,
        return_webpage_details: bool,
    ) -> Generator[Dict, None, None]:
        if "query" not in arguments:
            return {"observation": "调用工具失败, 缺乏必要输入参数, 请重试"}

        # get webpage content
        webpage_detail_list = []
        try:
            for webpage_detail in self.streaming_fetch_search_results(
                self.server_url,
                {
                    "query": arguments["query"],
                    "num_search_pages": self.num_search_webpages,
                },
                self.proxies,
            ):
                webpage_detail_list.append(webpage_detail)
                if return_webpage_details:
                    yield webpage_detail
        except Exception as e:
            print(e)
            yield {"observation": '输出"websearch server发生错误, 请重试"'}
            return

        webpage_texts = [
            webpage_detail["html_content"] for webpage_detail in webpage_detail_list
        ]

        no_webpages_loaded = True
        for webpage_text in webpage_texts:
            if webpage_text != "搜索页面加载超时, 请重试":
                no_webpages_loaded = False
                break

        # all web pages are timing out when loading
        if no_webpages_loaded:
            summaries = webpage_texts
            yield {"observation": "搜索页面加载超时, 请重试"}
        else:
            summary_prompts = self.make_summary_tasks(
                query=arguments["query"],
                webpage_texts=webpage_texts,
                summary_prompt_template=self.summary_prompt_template,
                tokenizer=tokenizer,
                webpage_summary_max_input_tokens=self.webpage_summary_max_input_tokens,
            )
            response_message = llm_completion_funcion(messages=summary_prompts)
            summaries = [choice.text for choice in response_message.choices]
            context = "\n".join(
                [
                    f"[[citation:{str(i+1)}]]\n{summary}"
                    for i, summary in enumerate(summaries)
                ]
            )
            yield {
                "observation": self.observation_prompt_template.format(
                    context=context, question=user_question, keywords=arguments["query"]
                )
            }
        return

    @staticmethod
    def make_summary_tasks(
        query: str,
        webpage_texts: List[str],
        summary_prompt_template: str,
        tokenizer: AutoTokenizer,
        webpage_summary_max_input_tokens: int = 2048,
    ) -> List[str]:
        messages_all = []
        for webpage_text in webpage_texts:
            if len(webpage_text) > 0:
                webpage_tokens = tokenizer.encode(webpage_text)
                webpage_text = tokenizer.decode(
                    webpage_tokens[:webpage_summary_max_input_tokens]
                )
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {
                    "role": "user",
                    "content": summary_prompt_template.format(
                        question=query, context=webpage_text
                    ),
                },
            ]
            messages_all.append(
                tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
            )
        return messages_all

    @staticmethod
    def streaming_fetch_search_results(
        url: str, content: Dict, proxies: Dict
    ) -> Generator[Dict, None, str]:
        try:
            with requests.post(
                url, json=content, stream=True, proxies=proxies
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        yield json.loads(line)
        except requests.exceptions.HTTPError as error:
            print(f"HTTP error occurred: {error}")
            return "网页加载超时"
