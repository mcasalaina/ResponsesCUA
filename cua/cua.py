
import asyncio
import json
import time
import re
import logging
import typing
import requests
import openai_pilot

# Tracking and controlling the state
class State:
    previous_response_id: str
    next_action: typing.Literal["user_interaction", "computer_tool_output"]
    previous_computer_id: str = ""
    computer_action: str = ""
    computer_action_args: dict = {}
    output_text: str = ""

    def __init__(self, response):
        assert response["status"] == "completed"
        self.previous_response_id = response["id"]
        self.output_text = []

        # If the item is a computer call, setting the next action and passing the action arguments.
        for item in response["output"]:
            if item.get("type") == "computer_call":
                self.next_action = "computer_tool_output"
                self.previous_computer_id = item["id"]
                self.computer_action = item["action"]["type"]
                self.computer_action_args = {k: v for k, v in item["action"].items() if k != "type"}
            else:
                self.next_action = "user_interaction"
                if item.get("type") == "message":
                    for content in item["content"]:
                        if content.get("type") == "output_text":
                            self.output_text.append(content["text"])

# CUA agent to start and continue task execution
class Agent:

    def __init__(self, base_url, api_key, model, machine):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.machine = machine
        self.state = None
        self.step_count = 0

    def start_task(self, user_message):
        body = {
            "model": self.model,
            "input": user_message,
            "tools": [{
                "type": "computer-preview",
                "display_width": self.machine.width,
                "display_height": self.machine.height,
                "environment": self.machine.environment,
            }],
        }
        response = self._make_api_request("POST", "/v1/responses", body)
        self.state = State(response)
        self.step_count = 0

    def requires_user_input(self):
        return self.state.next_action == "user_interaction"

    def requires_consent(self):
        return self.state.next_action == "computer_tool_output"

    def continue_task(self, user_message=""):
        screenshot = ""
        if self.state.next_action == "computer_tool_output":
            screenshot = asyncio.run(
                self.machine.handle_tool_call(
                    self.state.computer_action,
                    self.state.computer_action_args
                )
            )
        self.step_count += 1
        logging.debug("----- Step %s -----\n", self.step_count)
        body = {
            "model": self.model,
            "previous_response_id": self.state.previous_response_id,
            "tools": [{
                "type": "computer-preview",
                "display_width": self.machine.width,
                "display_height": self.machine.height,
                "environment": self.machine.environment,
            }],
            "input": (
                [{
                    "type": "computer_call_output",
                    "call_id": self.state.previous_computer_id,
                    "output": {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{screenshot}",
                    },
                }]
                if self.state.next_action == "computer_tool_output"
                else user_message
            ),
        }
        next_response = self._may_retry(self._make_api_request, "POST", "/v1/responses", body,
            json_print_redact_path=(
                [".input[0].output.image_url"]
                if self.state.next_action == "computer_tool_output"
                else []
            ),
        )
        self.state = State(next_response)

    def _pretty_print_json_obj(self, json_obj, json_print_redact_path=None):
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
            if isinstance(obj, list):
                return [redact_keys(item, f"{path}[{index}]") for index, item in enumerate(obj)]
            return obj

        redacted_obj = redact_keys(json_obj, path="")
        json_str = json.dumps(redacted_obj, indent=4, sort_keys=True)
        json_str = json_str.replace("\\n", "\n")
        logging.debug(json_str)

    def _make_api_request(
        self,
        method,
        url,
        body,
        json_print_redact_path=None,
    ):
        if json_print_redact_path is None:
            json_print_redact_path = []
        request_url = f"{self.base_url}{url}"
        logging.debug("%s %s", request_url, method)
        if body:
            self._pretty_print_json_obj(body, json_print_redact_path)

        headers = {
            "Authorization": f"Bearer {self.api_key}", 
            "OpenAI-Beta": "responses=v1"
        }
        if url == "/v1/files" and body["file"]:
            # For file uploads, send a multipart/form-data request
            data = {"purpose": body["purpose"]}
            files = {"file": (body["file"], open(body["file"], "rb"))}
            response = requests.request(
                method,
                request_url,
                data=data,
                files=files,
                headers=headers,
                timeout=60
            )
        else:
            if url.startswith("/v1/vector_stores"):
                headers["OpenAI-Beta"] = "assistants=v2"
            response = requests.request(
                method,
                request_url,
                json=body if method == "POST" else None,
                headers=headers,
                timeout=60
            )
        if response.status_code >= 400:
            body = json.loads(response.content)
            request_id = response.headers.get("X-Request-ID")
            raise openai_pilot.OpenAIError(request_id=request_id, status_code=response.status_code, message=body)
        self._pretty_print_json_obj(response.json())
        logging.debug("Request id: %s", response.headers.get('X-Request-ID'))
        return response.json()

    def _may_retry(self, func, *args, **kwargs):
        retry = True
        while retry:
            wait_time = 0
            try:
                time.sleep(wait_time)
                return func(*args, **kwargs)
            except openai_pilot.OpenAIError as oaierr:
                if oaierr.status_code == 429:
                    message = oaierr.message["error"]["message"]
                    match = re.search(r"Please try again in (\d+)s", message)
                    if match:
                        wait_time = int(match.group(1))
                        logging.debug("Rate limit exceeded. Waiting for %s seconds.", wait_time)
                    else:
                        logging.debug("%s. Cannot parse wait time.", oaierr.message)
                        retry = False
            except Exception as error: # pylint:disable=broad-except
                logging.critical("Error: %s", error)
                retry = False
        return None
