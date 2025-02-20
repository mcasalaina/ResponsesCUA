
import asyncio
import base64
import io
import json
import time
import re
import logging
import typing
import requests
import PIL
import openai_pilot

logger = logging.getLogger(__name__)

class State:
    "Tracking and controlling the state."

    previous_response_id: str
    next_action: typing.Literal["user_interaction", "computer_tool_output"]
    previous_computer_id: str = ""
    computer_action: str = ""
    computer_action_args: dict = {}
    output_text: str = ""

    def __init__(self, response):
        assert response["status"] == "completed"
        self.response = response
        self.next_action = ""
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

class Scaler:
    """Wrapper for a machine instance that performs resizing and coordinate translation."""

    def __init__(self, width, height, machine):
        self.width = width
        self.height = height
        self.machine = machine
        self.environment = machine.environment
        self.screen_width = -1
        self.screen_height = -1

    async def take_action(self, action: str, action_args: dict) -> str:
        if action in ("click", "double_click", "move", "scroll"):
            action_args["x"], action_args["y"] = self._point_to_screen_coords(action_args["x"], action_args["y"])
        elif action == "drag":
            path = action_args["path"]
            for point in path:
                point["x"], point["y"] = self._point_to_screen_coords(point["x"], point["y"])

    async def handle_tool_call(self, action: str, action_args: dict) -> bytearray:
        # Adjust the action arguments to match the machine coordinate system
        if action not in ("initialize", "get", "screenshot"):
            await self.take_action(action, action_args)
        # Call the underlying machine. Screenshot will be taken after the action
        screenshot = await self.machine.handle_tool_call(action, action_args)
        # Scale the screenshot
        buffer = io.BytesIO(screenshot)
        image = PIL.Image.open(buffer)
        self.screen_width, self.screen_height = image.size
        aspect_ratio = self.screen_width / self.screen_height
        if aspect_ratio > 1:
            new_width = self.width
            new_height = int(self.width / aspect_ratio)
        else:
            new_height = self.height
            new_width = int(self.height * aspect_ratio)
        resized_image = image.resize((new_width, new_height), PIL.Image.Resampling.LANCZOS)
        padded_image = PIL.Image.new("RGB", (self.width, self.height), (0, 0, 0))
        x_offset = (self.width - new_width) // 2
        y_offset = (self.height - new_height) // 2
        padded_image.paste(resized_image, (x_offset, y_offset))
        padded_image_buffer = io.BytesIO()
        padded_image.save(padded_image_buffer, format="PNG")
        padded_image_buffer.seek(0)
        return bytearray(padded_image_buffer.getvalue())

    def _point_to_screen_coords(self, x, y):
        aspect_ratio = self.screen_width / self.screen_height
        if aspect_ratio > 1:
            new_width = self.width
            new_height = int(self.width / aspect_ratio)
            x_offset = 0
            y_offset = (self.height - new_height) // 2
        else:
            new_height = self.height
            new_width = int(self.height * aspect_ratio)
            x_offset = (self.width - new_width) // 2
            y_offset = 0
        x = (x - x_offset) * (self.screen_width / new_width)
        y = (y - y_offset) * (self.screen_height / new_height)
        return int(x), int(y)

class Client:
    """Responses API calling code."""

    def __init__(self, base_url, bearer_token=None, api_key=None, api_version=None):
        self.base_url = base_url.rstrip('/')
        self.bearer_token = bearer_token
        self.api_key = api_key
        self.api_version = api_version

    def make_request(self, method, url, body, json_print_redact_path=None):
        if json_print_redact_path is None:
            json_print_redact_path = []
        headers = {
            "x-ms-enable-preview": "true",
        }
        params = {}
        if self.base_url.endswith("openai.azure.com"):
            request_url = f"{self.base_url}/openai/{url}"
            # headers['x-ms-client-request-id'] = 'true'
            headers["accept-encoding"] = "gzip, deflate, br"
            headers["accept"] = "*/*"
            # headers["api-key"] = self.api_key
            headers["Authorization"] = f"Bearer {self.bearer_token}"
            headers["User-Agent"] = ""
            params['api-version'] = self.api_version
        else:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
            headers["OpenAI-Beta"] = "responses=v1"
            request_url = f"{self.base_url}/v1/{url}"
        logger.debug("%s %s", method.lower(), request_url)
        if body:
            self._pretty_print_json_obj(body, json_print_redact_path)
        if url == "files" and body["file"]:
            # For file uploads, send a multipart/form-data request
            with open(body["file"], "rb") as file:
                data = {"purpose": body["purpose"]}
                files = {"file": (body["file"], file)}
                response = requests.request(method, request_url, data=data, files=files, headers=headers, params=params, timeout=60)
        else:
            if url.startswith("vector_stores"):
                headers["OpenAI-Beta"] = "assistants=v2"
            data = body if method == "POST" else None
            response = requests.request(method, request_url, json=data, headers=headers, params=params, timeout=60)
        if response.status_code >= 400:
            body = json.loads(response.content)
            request_id = response.headers.get("X-Request-ID")
            raise openai_pilot.OpenAIError(request_id=request_id, status_code=response.status_code, message=body)
        self._pretty_print_json_obj(response.json())
        logger.debug("Request id: %s", response.headers.get('X-Request-ID'))
        return response.json()

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
        logger.debug(json_str)

class Agent:
    """CUA agent to start and continue task execution"""

    def __init__(self, client, model, machine):
        self.client = client
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
        response = self.client.make_request("POST", "responses", body)
        self.state = State(response)
        self.step_count = 0

    def requires_user_input(self):
        return self.state.next_action == "user_interaction"

    def requires_consent(self):
        return self.state.next_action == "computer_tool_output"

    def continue_task(self, user_message=""):
        self.step_count += 1
        logger.debug("\n---- Step %s ----", self.step_count)

        screenshot = ""
        if self.state.next_action == "computer_tool_output":
            action = self.state.computer_action
            action_args = self.state.computer_action_args
            logger.info("action %s %s", action, action_args)
            screenshot = asyncio.run(
                self.machine.handle_tool_call(action, action_args)
            )
            if screenshot:
                screenshot = base64.b64encode(screenshot).decode("utf-8")
                logger.debug("screenshot %s...", screenshot[:20])

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
        next_response = self._may_retry(self.client.make_request, "POST", "responses", body,
            json_print_redact_path=(
                [".input[0].output.image_url"]
                if self.state.next_action == "computer_tool_output"
                else []
            ),
        )
        self.state = State(next_response)

    def _may_retry(self, func, *args, **kwargs):
        retry = 10
        wait_time = 0
        while retry > 0:
            retry -= 1
            try:
                time.sleep(wait_time)
                return func(*args, **kwargs)
            except openai_pilot.OpenAIError as oaierr:
                if oaierr.status_code == 429:
                    error = oaierr.message["error"]
                    wait_time = 10
                    if 'message' in error:
                        message = error["message"]
                        match = re.search(r"Please try again in (\d+)s", message)
                        if match:
                            wait_time = int(match.group(1))
                            logger.info("Rate limit exceeded. Waiting for %s seconds.", wait_time)
                        else:
                            logger.critical("%s. Cannot parse wait time.", oaierr.message)
                            retry = 0
                    elif 'type' in error and error['type'] == 'rate_limit_error':
                        logger.info("Rate limit error. Waiting for %s seconds.", wait_time)
            except Exception as error: # pylint: disable=broad-except
                logger.critical("Error: %s", error)
                retry = False
        logger.critical("Max retries exceeded.")
        return None
