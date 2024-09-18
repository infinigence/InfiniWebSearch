from typing import List, Tuple


def include_special_tokens(text: str, tokens: List[str]) -> bool:
    include_all_tokens = True
    for token in tokens:
        if token not in text:
            include_all_tokens = False
            break
    return include_all_tokens


def split_text_by_special_token(text: str, token: str) -> Tuple[str, str]:
    assert token in text, f"{token} not found in {text}"
    parts = text.split(token)
    return parts[0], parts[1]
