import argparse
import json
import os
from typing import TypedDict
import time

import requests

from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import JsonLexer

from openai_pilot import OpenAIError

Config = TypedDict(
    "Config",
    {
        "API_KEY": str,
        "URL_BASE": str,
        "PROD_COMPLETIONS_API_KEY": str,
        "ENV": str,
        "PROD_ORG_ID": str,
    },
)


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-input",
        dest="no_input",
        default=True,
        help="Whether or not to run through the demo without any input from the user",
        action="store_true",
    )

    return parser


def get_config(args):
    config: Config = {
        "API_KEY": "",
        "URL_BASE": "https://api.openai.com",
    }

    return config

def pretty_print_json_obj(json_obj, json_print_redact_path=None):
    if json_print_redact_path is None:
        json_print_redact_path = []

    def redact_keys(obj, path=""):
        if not json_print_redact_path:
            return obj
        if isinstance(obj, dict):
            return {
                key: (
                    redact_keys(value, f"{path}.{key}" if path else f".{key}")
                    if (f"{path}.{key}" if path else f".{key}") not in json_print_redact_path
                    else "... (skipped)"
                )
                for key, value in obj.items()
            }
        elif isinstance(obj, list):
            return [redact_keys(item, f"{path}[{index}]") for index, item in enumerate(obj)]
        else:
            return obj

    redacted_obj = redact_keys(json_obj, path="")
    json_str = json.dumps(redacted_obj, indent=4, sort_keys=True)
    json_str = json_str.replace("\\n", "\n")
    print(highlight(json_str, JsonLexer(), TerminalFormatter()))


def make_req(
    method,
    url,
    body,
    step_name,
    config: Config,
    wait_for_final_input=True,
    suppress_input=False,
    base_url=None,
    json_print_redact_path=None,
):
    if json_print_redact_path is None:
        json_print_redact_path = []
    request_url = f"{base_url}{url}" if base_url else f"{config['URL_BASE']}{url}"
    print(f"-----{step_name}-----\n")
    print(f"{request_url} {method} {url}")
    if body:
        pretty_print_json_obj(body, json_print_redact_path)
    else:
        print()
    if not suppress_input:
        input("Send?\n")

    headers = {"Authorization": f"Bearer {config['API_KEY']}", "openai-beta": "responses=v1"}


    if url == "/v1/files" and body["file"]:
        # For file uploads, send a multipart/form-data request
        data = {"purpose": body["purpose"]}
        files = {"file": (body["file"], open(body["file"], "rb"))}
        resp = requests.request(
            method,
            request_url,
            data=data,
            files=files,
            headers=headers,
        )
    else:
        if url.startswith("/v1/vector_stores"):
            headers["openai-beta"] = "assistants=v2"
        resp = requests.request(
            method,
            request_url,
            json=body if method == "POST" else None,
            headers=headers,
        )
    
    if resp.status_code >= 400:
        body = json.loads(resp.content)
        request_id = resp.headers.get("X-Request-ID")
        raise OpenAIError(
            request_id=request_id, status_code=resp.status_code, message=body
        )

    pretty_print_json_obj(resp.json())
    print(f"Request id: {resp.headers.get('X-Request-ID')}")
    if not suppress_input and wait_for_final_input:
        input("")
    return resp.json()

def may_retry(func, *args, **kwargs):
    should_try = True
    wait_time = 0
    while should_try:
        try:
            time.sleep(wait_time)
            return func(*args, **kwargs)
        except OpenAIError as oaierr:
            if oaierr.status_code == 429:
                import re
                pattern = r"Please try again in (\d+)s"
                msg = oaierr.message["error"]["message"]
                match = re.search(pattern,msg)
                if match:
                    wait_time = int(match.group(1))
                    print(f"Rate limit exceeded. Waiting for {wait_time} seconds.")
                else:
                    print(f"{oaierr.message} - cannot parse wait time.")
                    should_try = False
        except Exception as e:
            print(f"Error: {e}")
            should_try = False
    