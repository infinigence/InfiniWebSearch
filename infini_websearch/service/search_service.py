import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Generator, Optional, Tuple, Union

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

parser = argparse.ArgumentParser()
parser.add_argument("--chrome", type=str)
parser.add_argument("--chromedriver", type=str)
parser.add_argument("--port", type=int)

args = parser.parse_args()

app = FastAPI()

SERPER_API_KEY = os.environ.get("SERPER_API_KEY")


def get_webpage_content(url: str, chrome_path: str, chromedriver_path: str) -> str:
    """
    Load the content of web pages by chromedriver.
    """
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--headless")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-browser-side-navigation")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-application-cache")
    options.add_argument("--dns-prefetch-disable")
    options.add_argument("--no-proxy-server")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--enable-http2")
    options.add_argument("--disable-quic")
    options.binary_location = chrome_path
    options.page_load_strategy = "eager"
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
        "download_restrictions": 3,
    }
    options.add_experimental_option("prefs", prefs)
    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(options=options, service=service)
    try:
        timeout = 10
        start = time.time()
        driver.set_page_load_timeout(timeout)
        try:
            driver.get(url)
        except TimeoutException:
            print(f"页面加载超时（{timeout}秒）")
            return "搜索页面加载超时, 请重试"
        end = time.time()
        print(f"读取网页内容耗时: {end - start}s")
        content = driver.execute_script("return document.body.innerText;")
        return content
    except Exception as e:
        print(e)
        return ""
    finally:
        driver.quit()


def serper_search(
    search_term: str, search_type: Optional[str] = "search", timeout: int = 5, **kwargs
) -> Tuple[int, Union[Dict, str]]:
    """
    Get google search results by serper api (https://serper.dev/).
    """
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    params = {
        "q": search_term,
        "gl": "cn",  # country
        "sort": "date",
        "hl": "zh-CN",
        **{key: value for key, value in kwargs.items() if value is not None},
    }
    try:
        response = requests.post(
            f"https://google.serper.dev/{search_type}",
            headers=headers,
            params=params,
            proxies=None,
            timeout=timeout,
        )
    except Exception as e:
        return -1, str(e)
    return response.status_code, response.json()


def streaming_fetch_webpage_content(
    results: dict, num_search_pages: int, chrome_path: str, chromedriver_path: str
) -> Generator[Tuple[str, str], None, None]:
    url_infos = results["organic"][:num_search_pages]

    with ThreadPoolExecutor(max_workers=len(url_infos)) as executor:
        future_to_url = {
            executor.submit(
                get_webpage_content, url_info["link"], chrome_path, chromedriver_path
            ): url_info
            for url_info in url_infos
        }
        for future in as_completed(future_to_url):
            url_info = future_to_url[future]
            try:
                result = future.result()
                yield url_info, result
            except Exception as exc:
                print(f'{url_info["link"]} generated an exception: {exc}')
                yield url_info, ""


@app.post("/search")
async def search(request: Request):
    data = await request.json()
    print(data)

    start = time.time()
    status_code, response = serper_search(data["query"], timeout=10)
    end = time.time()
    print(f"搜索网页耗时: {end - start}s")

    if status_code != 200:
        raise HTTPException(status_code=500, detail="搜索网页超时, 请重试")

    def html_docs_text_generator():
        start = time.time()
        for url_info, content in streaming_fetch_webpage_content(
            response,
            num_search_pages=data["num_search_pages"],
            chrome_path=args.chrome,
            chromedriver_path=args.chromedriver,
        ):
            yield json.dumps(
                {
                    "search_status_code": status_code,
                    "search_response": response,
                    "url_info": url_info,
                    "html_content": content,
                },
                ensure_ascii=False,
            ) + "\n"
        end = time.time()
        print(f"解析网页耗时: {end - start}s")

    return StreamingResponse(html_docs_text_generator(), media_type="application/json")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("search_service:app", host="0.0.0.0", port=args.port, reload=True)
