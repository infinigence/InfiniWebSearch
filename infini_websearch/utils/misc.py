import json
import re
from datetime import datetime


def functions2str(functions: list) -> str:
    return "\n\n".join(
        [json.dumps(function, ensure_ascii=False, indent=4) for function in functions]
    )


def get_datetime_now():
    current_date = datetime.now()
    formatted_time = current_date.strftime("%Y-%m-%d %H:%M:%S")
    weekday_id = current_date.weekday()
    weekday_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    return formatted_time, weekday_names[weekday_id]


def format_search_results(url_infos: dict):
    return "\n".join(
        f"[{url_info['title']}]({url_info['link']})" for url_info in url_infos
    )


def extract_citations(text):
    citations1 = re.findall(r"\[citation:(\d+)\]", text)
    citations2 = re.findall(r"\[ citation:(\d+)\]", text)
    return citations1 or citations2
