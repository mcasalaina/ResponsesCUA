import argparse
from typing import Literal, NamedTuple
import pyautogui
from PIL import Image
import base64
from io import BytesIO
import requests
import asyncio

# API Configuration
API_KEY = "API_KEY"
API_BASE_URL = "API_BASE_URL"

class size(NamedTuple):
    width: int
    height: int


DEFAULT_SIZE = size(1024, 768)
ALT_SIZE = size(1920, 1080)

class state:
    previous_response_id: str
    next_action: Literal["user_interaction", "computer_tool_output"]
    previous_computer_id: str = ""
    computer_action: str = ""
    computer_action_args: dict = {}

    def __init__(self, response):
        assert response["status"] == "completed"
        self.previous_response_id = response["id"]

        for item in response["output"]:
            if item.get("type") == "computer_call":
                self.next_action = "computer_tool_output"
                self.previous_computer_id = item["id"]
                self.computer_action = item["action"]["type"]
                self.computer_action_args = {k: v for k, v in item["action"].items() if k != "type"}
            else:
                self.next_action = "user_interaction"

class machine:
    def __init__(self):
        self.vnc = pyautogui

    async def take_screenshot(self):
        """Takes a screenshot and returns a base64 encoded string"""
        try:
            # Take a screenshot
            print("Watching screen...")
            screenshot = self.vnc.screenshot()

            # Resize the screenshot to 1024x768 for API compatibility
            screenshot = screenshot.resize((DEFAULT_SIZE.width, DEFAULT_SIZE.height), Image.Resampling.LANCZOS)

            # Convert the image to bytes and encode in base64
            buffered = BytesIO()
            screenshot.save(buffered, format="PNG")
            base64_data = base64.b64encode(buffered.getvalue()).decode('utf-8')

            return base64_data

        except Exception as e:
            print(f"Error taking screenshot: {e}")
            return None

    async def take_action(self, action: str, action_args: dict) -> str:
        if action in ("initialize", "get", "screenshot"):
            return await self.take_screenshot()
        elif action == "click":
            self.vnc.click(action_args["x"], action_args["y"])
        elif action == "double_click":
            self.vnc.doubleClick(action_args["x"], action_args["y"])
        elif action == "drag":
            # Drag the mouse along the specified path
            for x, y in action_args["path"]:
                self.vnc.moveTo(x, y, duration=0.1)  # Add a slight delay for smooth dragging
        elif action == "keypress":
            keys = action_args["keys"]
            if isinstance(keys, list):
                for key in keys:
                    pyautogui.press(key)
                    print(f"Pressed key: {key}")
            else:
                pyautogui.press(keys)
                print(f"Pressed key: {keys}")
        elif action == "scroll":
            # Perform scrolling
            self.vnc.moveTo(action_args["x"], action_args["y"])
            self.vnc.scroll(action_args["scroll_y"])
            self.vnc.hscroll(action_args["scroll_x"])
        elif action == "move":
            self.vnc.moveTo(action_args["x"], action_args["y"])
        elif action == "type":
            self.vnc.typewrite(action_args["text"])
        elif action == "wait":
            await asyncio.sleep(1)
        else:
            print(f"Invalid action: {action}")
            return ""

        # Take a screenshot after the action
        return await self.take_screenshot()

    async def handle_tool_call(self, action: str, action_args: dict) -> str:
        print(f"Running action: {action} with args: {action_args}")
        screenshot_base64 = await self.take_action(action, action_args)
        if not screenshot_base64:
            return ""

        print(f"Screenshot (partial): {screenshot_base64[:100]}...")
        return screenshot_base64

def make_api_request(endpoint: str, data: dict) -> dict:
    """Centralized API request handler"""
    url = f"{API_BASE_URL}/{endpoint}"
    headers = {
        "OpenAI-Beta": "responses=v1",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {str(e)}")
        if hasattr(e.response, 'text'):
            print(f"Response text: {e.response.text}")
        return None

def make_initial_call(user_instruction: str):
    data = {
        "model": "computer-use-alpha",
        "input": user_instruction,
        "tools": [{
            "type": "computer-preview",
            "display_width": DEFAULT_SIZE.width,  # Use 1024x768 for API
            "display_height": DEFAULT_SIZE.height,
            "environment": "windows"
        }]
    }

    return make_api_request("responses", data)

def make_follow_up_call(previous_response_id: str, call_id: str, screenshot_base64: str):
    data = {
        "model": "computer-use-alpha",
        "previous_response_id": previous_response_id,
        "tools": [{
            "type": "computer-preview",
            "display_width": DEFAULT_SIZE.width,  # Use 1024x768 for API
            "display_height": DEFAULT_SIZE.height,
            "environment": "mac"
        }],
        "input": [{
            "type": "computer_call_output",
            "call_id": call_id,
            "output": {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{screenshot_base64}"
            }
        }]
    }

    return make_api_request("responses", data)

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

def main():
    pyautogui.FAILSAFE = True

    try:
        parser = get_parser()
        args = parser.parse_args()

        parser.add_argument("--instructions", dest="instructions", help="Instructions to follow")
        parser.add_argument("--model", dest="model", default="computer-use-alpha")
        parser.add_argument("--environment", dest="environment", default="linux")
        parser.add_argument("--autoenter", dest="autoenter", default=False, action="store_true")

        size = DEFAULT_SIZE
        print(f"Using screen size: {size}")

        user_instruction = input("What do you want me to do? ")

        # Initial API call
        print("\nMaking initial API call...")
        initial_response = make_initial_call(user_instruction)
        persisted_state = state(initial_response)
        vm = machine()

        step_count = 0
        user_message = ""
        base64_screenshot_data = ""
        while True:
            if persisted_state.next_action == "computer_tool_output":
                base64_screenshot_data = asyncio.run(
                    vm.handle_tool_call(
                        persisted_state.computer_action,
                        persisted_state.computer_action_args,
                    )
                )
            else:
                user_message = input("What do you want me to do? ")

            step_count += 1
            next_response = make_follow_up_call(persisted_state.previous_response_id, persisted_state.previous_computer_id, base64_screenshot_data if persisted_state.next_action == "computer_tool_output" else user_message)
            persisted_state = state(next_response)

    except KeyboardInterrupt:
        print("\nProgram terminated by user")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()