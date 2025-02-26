
import asyncio
import base64
import io
import time
import re
import logging
import typing
import PIL
import openai_pilot

logger = logging.getLogger(__name__)

class State: # pylint: disable=too-many-instance-attributes
    "Tracking and controlling the state."

    previous_response_id: str
    next_action: typing.Literal["user_interaction", "computer_call_output"]
    previous_computer_id: str = ""
    computer_action: str = ""
    computer_action_args: dict = {}
    pending_safety_checks: list = []
    last_message: str = ""

    def __init__(self, response):
        assert response["status"] == "completed"
        self.response = response
        self.next_action = ""
        self.previous_response_id = response["id"]

        # If the item is a computer call, setting the next action and passing the action arguments.
        for item in response["output"]:
            if item.get("type") == "computer_call":
                self.next_action = "computer_call_output"
                self.previous_computer_id = item["call_id"] if "call_id" in item else item["id"]
                self.computer_action = item["action"]["type"]
                self.computer_action_args = {k: v for k, v in item["action"].items() if k != "type"}
                self.pending_safety_checks = item.get("pending_safety_checks", [])
            else:
                self.next_action = "user_interaction"
                if item.get("type") == "message":
                    for content in item["content"]:
                        if content.get("type") == "output_text":
                            self.last_message += content["text"]

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
            for point in action_args["path"]:
                x, y = self._point_to_screen_coords(point[0], point[1])
                point[0] = x
                point[1] = y

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
        ratio = min(self.width / self.screen_width, self.height / self.screen_height)
        new_width = int(self.screen_width * ratio)
        new_height = int(self.screen_height * ratio)
        resized_image = image.resize((new_width, new_height), PIL.Image.Resampling.LANCZOS)
        image = PIL.Image.new("RGB", (self.width, self.height), (0, 0, 0))
        image.paste(resized_image, (0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return bytearray(buffer.getvalue())

    def _point_to_screen_coords(self, x, y):
        ratio = min(self.width / self.screen_width, self.height / self.screen_height)
        x = x / ratio
        y = y / ratio
        return int(x), int(y)

class Agent:
    """CUA agent to start and continue task execution"""

    def __init__(self, client, model, machine):
        self.client = client
        self.model = model
        self.machine = machine
        self.state = None
        self.step_count = 0

    def start_task(self, user_message):
        tools = [{
            "type": "computer-preview",
            "display_width": self.machine.width,
            "display_height": self.machine.height,
            "environment": self.machine.environment,
        }]
        response = self.client.beta.responses.create(self.model, input=user_message, tools=tools)
        self.state = State(response)
        self.step_count = 0

    def requires_user_input(self):
        return self.state.next_action == "user_interaction"

    def requires_consent(self):
        return self.state.next_action == "computer_call_output"

    def requires_safety_check(self):
        return self.state.pending_safety_checks

    def continue_task(self, user_message=""): # pylint: disable=too-many-branches
        self.step_count += 1
        logger.debug("\n---- Step %s ----", self.step_count)
        screenshot = ""
        previous_response_id = self.state.previous_response_id
        if self.state.next_action == "computer_call_output":
            action = self.state.computer_action
            action_args = self.state.computer_action_args
            logger.info("action %s %s", action, action_args)
            screenshot = asyncio.run(self.machine.handle_tool_call(action, action_args))
            if screenshot:
                screenshot = base64.b64encode(screenshot).decode("utf-8")
                logger.debug("screenshot %s...", screenshot[:20])
        data = user_message
        if self.state.next_action == "computer_call_output":
            data = [{
                "type": "computer_call_output",
                "call_id": self.state.previous_computer_id,
                "output": {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{screenshot}",
                }
            }]
            if self.state.pending_safety_checks:
                data["acknowledged_safety_checks"] = self.state.pending_safety_checks
        tools = [{
            "type": "computer-preview",
            "display_width": self.machine.width,
            "display_height": self.machine.height,
            "environment": self.machine.environment,
        }]
        self.state = None
        retry = 10
        wait_time = 0
        while retry > 0:
            try:
                time.sleep(wait_time)
                next_response = self.client.beta.responses.create(self.model, previous_response_id, input=data, tools=tools)
                self.state = State(next_response)
                return
            except openai_pilot.OpenAIError as oaierr:
                if oaierr.status_code == 429:
                    error = oaierr.message["error"]
                    retry -= 1
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
                else:
                    logger.critical(str(oaierr))
            except Exception as error: # pylint: disable=broad-except
                logger.critical("Error: %s", error)
                retry = 0
        logger.critical("Max retries exceeded.")
