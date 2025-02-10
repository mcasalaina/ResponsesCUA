import asyncio
import base64
import io
import logging
import os
import shutil
import tempfile
from typing import Literal, NamedTuple
from PIL import ImageGrab, Image, ImageOps
import pyautogui

from dotenv import load_dotenv
from utils import get_config, get_parser, make_req, may_retry

from vm import VNCMachine

load_dotenv()
load_dotenv(dotenv_path='secrets.env')
api_key = os.environ.get("OPENAI_API_KEY_NEWMODEL")


# This is the CUA size
class Size(NamedTuple):
    width: int
    height: int


DEFAULT_SIZE = Size(1024, 768)
ALT_SIZE = Size(1920, 1080)


class PersistentState:
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


class LocalMachineManager:
    def __init__(self):
        self.target_width, self.target_height = 1024, 768
        screenshot = pyautogui.screenshot()
        self.screen_width, self.screen_height = screenshot.size

    async def take_screenshot(self):
        screenshot = pyautogui.screenshot()
        screenshot.save("screenshot.png")
        screenshot = Image.open("screenshot.png")
        self.screen_width, self.screen_height = screenshot.size
        aspect_ratio = self.screen_width / self.screen_height
        if aspect_ratio > 1:
            new_width = self.target_width
            new_height = int(self.target_width / aspect_ratio)
        else:
            new_height = self.target_height
            new_width = int(self.target_height * aspect_ratio)
        resized_screenshot = screenshot.resize((new_width, new_height), Image.Resampling.LANCZOS)
        padded_image = Image.new("RGB", (self.target_width, self.target_height), (0, 0, 0))
        x_offset = (self.target_width - new_width) // 2
        y_offset = (self.target_height - new_height) // 2
        padded_image.paste(resized_screenshot, (x_offset, y_offset))
        padded_image.save("screenshot.png")
        with open("screenshot.png", "rb") as image_file:
            image_data = image_file.read()
        screenshot_base64 = base64.b64encode(image_data).decode("utf-8")
        return screenshot_base64

    def point_to_screen_coords(self, x, y):
        aspect_ratio = self.screen_width / self.screen_height
        if aspect_ratio > 1:
            new_width = self.target_width
            new_height = int(self.target_width / aspect_ratio)
            x_offset = 0
            y_offset = (self.target_height - new_height) // 2
        else:
            new_height = self.target_height
            new_width = int(self.target_height * aspect_ratio)
            x_offset = (self.target_width - new_width) // 2
            y_offset = 0
        original_x = (x - x_offset) * (self.screen_width / new_width)
        original_y = (y - y_offset) * (self.screen_height / new_height)
        return int(original_x), int(original_y)

    async def take_action(self, action: str, action_args: dict) -> str:
        if action in ("initialize", "get", "screenshot"):
            return await self.take_screenshot()

        if action == "click":
            x, y = self.point_to_screen_coords(action_args["x"], action_args["y"])
            if 0 <= x < self.screen_width and 0 <= y < self.screen_width:
                button = action_args["button"]
                pyautogui.moveTo(x, y, duration=0.5)
                pyautogui.click(x, y, button=button)
        elif action == "double_click":
            x, y = self.point_to_screen_coords(action_args["x"], action_args["y"])
            if 0 <= x < self.screen_width and 0 <= y < self.screen_width:
                button = action_args["button"]
                pyautogui.moveTo(x, y, duration=0.5)
                pyautogui.doubleClick(x, y, button=button)
        elif action == "drag":
            raise NotImplementedError("drag")
            # await self.vnc.drag_mouse(path=action_args["path"],)
        elif action == "keypress":
            for key in action_args["keys"]:
                key = key.lower()
                pyautogui.keyDown(key)
            for key in action_args["keys"]:
                key = key.lower()
                pyautogui.keyUp(key)
            # await self.vnc.multi_key_press(keys=action_args["keys"],)
        elif action == "move":
            point = self.point_to_screen_coords(action_args["x"], action_args["y"])
            pyautogui.moveTo(point, duration=0.5)
            # await self.vnc.move_mouse(position=(action_args["x"], action_args["y"]),)
        elif action == "scroll":
            raise NotImplementedError("scroll")
            # await self.vnc.scroll(
            #     position=(action_args["x"], action_args["y"]),
            #     horizontal=action_args["scroll_x"],
            #     vertical=action_args["scroll_y"],
            # )
        elif action == "type":
            pyautogui.write(action_args["text"])
            # await self.vnc.type(text=action_args["text"],)
        elif action == "wait":
            await asyncio.sleep(1)
        else:
            print(f"Invalid action: {action}")
            return ""

        # Take a screenshot after the action
        return await self.take_screenshot()

    async def handle_tool_call(
        self, dir: str, action: str, action_args: dict, step_count: int, resize: bool
    ) -> str:
        print(f"Running action: {action} with args: {action_args}")
        screenshot_base64 = await self.take_action(action, action_args)
        if not screenshot_base64:
            return ""
        
        if resize:
            print("resizing screenshot")
            screenshot_bytes = base64.b64decode(screenshot_base64)
            size = ALT_SIZE
            with Image.open(io.BytesIO(screenshot_bytes)) as img:
                resized_img = img.resize((size.width, size.height), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                resized_img.save(buffer, format=img.format)
                screenshot_bytes = buffer.getvalue()
                screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        print(f"Screenshot (partial): {screenshot_base64[:100]}...")
        return screenshot_base64


class VMManager:
    def __init__(self, address):
        self.vnc = VNCMachine(address=address)

    async def take_screenshot(self):
        image_path = 'screenshot.png'
        await self.vnc.screenshot(screenshot_name=image_path, keys=None)
        with open(image_path, 'rb') as image_file:
            image_data = image_file.read()
        screenshot_base64 = base64.b64encode(image_data).decode('utf-8')
        return screenshot_base64
    
    async def take_action(self, action: str, action_args: dict) -> str:
        if action in ("initialize", "get", "screenshot"):
            return await self.take_screenshot()
        elif action == "click":
            await self.vnc.mouse_click(
                position=(action_args["x"], action_args["y"]),
                action="click",
                button=1
            )
        elif action == "double_click":
            await self.vnc.mouse_click(
                position=(action_args["x"], action_args["y"]),
                action="double_click",
                button=1
            )
        elif action == "drag":
            await self.vnc.drag_mouse(
                path=action_args["path"],
            )
        elif action == "keypress":
            await self.vnc.multi_key_press(
                keys=action_args["keys"],
            )
        elif action == "move":
            await self.vnc.move_mouse(
                position=(action_args["x"], action_args["y"]),
            )
        elif action == "scroll":
            await self.vnc.scroll(
                position=(action_args["x"], action_args["y"]),
                horizontal=action_args["scroll_x"],
                vertical=action_args["scroll_y"],
            )
        elif action == "type":
            await self.vnc.type(
                text=action_args["text"],
            )
        elif action == "wait":
            await asyncio.sleep(1)
        else:
            print(f"Invalid action: {action}")
            return ""

        # Take a screenshot after the action
        return await self.take_screenshot()

    async def handle_tool_call(
        self, dir: str, action: str, action_args: dict, step_count: int, resize: bool
    ) -> str:
        print(f"Running action: {action} with args: {action_args}")
        screenshot_base64 = await self.take_action(action, action_args)
        if not screenshot_base64:
            return ""

        if resize:
            print("resizing screenshot")
            screenshot_bytes = base64.b64decode(screenshot_base64)
            size = ALT_SIZE
            with Image.open(io.BytesIO(screenshot_bytes)) as img:
                resized_img = img.resize((size.width, size.height), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                resized_img.save(buffer, format=img.format)
                screenshot_bytes = buffer.getvalue()
                screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        print(f"Screenshot (partial): {screenshot_base64[:100]}...")
        return screenshot_base64


def make_init_request(initial_task, args, config):
    size = DEFAULT_SIZE if not args.alt_screen_size else ALT_SIZE

    return make_req(
        "POST",
        "/v1/responses",
        body={
            "model": args.model,
            "input": initial_task,
            "tools": [
                {
                    "type": "computer-preview",
                    "display_width": size.width,
                    "display_height": size.height,
                    "environment": args.environment,
                }
            ],
        },
        step_name="initialize the computer",
        suppress_input=args.no_input,
        config=config,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = get_parser()
    parser.add_argument(
        "--vm_address",
        dest="vm_address",
        help="The address of the VM to use",
        type=str,
        default="192.168.236.154",
    )
    parser.add_argument("--instructions", dest="instructions", help="Instructions to follow")
    parser.add_argument("--alt-screen-size", default=False, dest="alt_screen_size", action="store_true")
    parser.add_argument("--model", dest="model", default="computer-use-alpha")
    # parser.add_argument("--model", dest="model", default="computer-use-preview-2025-02-04")
    parser.add_argument("--environment", dest="environment", default="windows")
    parser.add_argument("--autoenter", dest="autoenter", default=True, action="store_true")

    args = parser.parse_args()
    config = get_config(args)
    config["API_KEY"] = api_key

    # vm_manager = VMManager(address=args.vm_address)
    vm_manager = LocalMachineManager()


    folder = os.path.expandvars(r"%USERPROFILE%\source\repos\TestApp")
    if os.path.exists(folder):
        shutil.rmtree(folder)

    initial_task = """
You are a manual UX tester for Visual Studio 2022 main (Preview).
- Use the start menu to find the correct app.
- DO NOT ask the user unless absolutely necessary.

Please execute this test plan. Once done return a test report containing a list of (step, pass/fail, notes) for each step.
1. Open Visual Studio 2022 main
2. Create a new .NET C# Console App project called "TestApp"
3. Build the solution
4. Check that there are no build errors.
5. Run the project (Green play button in the toolbar)
6. Verify that the output is "Hello, world!"
7. Switch to Visual Studio and stop debugging
8. Close Visual Studio
"""


#     initial_task = """
# You are an autonomous manual UX tester for Visual Studio 2022 main (Preview).
# - Use the start menu to find the correct app.
# - Confirmations: DO NOT ask the user for any confirmations or approvals.

# Please execute this test plan and report any issues you encounter.
# 1. Open Visual Studio 2022 main
# 2. Create a new Blazor Web App project called "TestApp" using C#, overwrite the existing project if it exists
# 3. Open the Program.cs file in Solution Explorer
# 4. Set a breakpoint in the editor at line 12, make sure there is a red circle indicating the breakpoint on line 12 is active
# 5. Build the solution
# 6. Check that there are no build errors.
# 7. Launch the project (Green play button in the toolbar)
# 8. Validate that the breakpoint is hit and continue
# 9. Validate that the web browser was opened showing the running app
# 10. Click on "Weather" and validate the page loads
# 11. Switch back to the Visual Studio 2022 main window
# 12. Stop debugging (Red square button in the toolbar)
# 13. Close Visual Studio
# """
    #(
        #"close vscode"
        #args.instructions
        #or input("Please enter the initial task for the computer: ")
        #or "Go to booking.com"
    #)
    init_response = make_init_request(initial_task, args, config)
    persisted_state = PersistentState(init_response)
    print(f"arg.alt_screen_size: {args.alt_screen_size}")

    size = DEFAULT_SIZE if not args.alt_screen_size else ALT_SIZE
    print(f"Using screen size: {size}")

    with tempfile.TemporaryDirectory() as tmpdir:
        step_count = 0
        user_message = ""
        base64_screenshot_data = ""
        while True:
            if persisted_state.next_action == "computer_tool_output":
                # if not args.autoenter:
                #     input("Press Enter to run computer tool...")
                base64_screenshot_data = asyncio.run(
                    vm_manager.handle_tool_call(
                        tmpdir,
                        persisted_state.computer_action,
                        persisted_state.computer_action_args,
                        step_count,
                        resize=args.alt_screen_size,
                    )
                )
            else:
                user_message = input(
                    "Please enter your message and press Enter to continue sampling: "
                )

            step_count += 1
            next_response = may_retry(make_req,
                "POST",
                "/v1/responses",
                body={
                    "model": args.model,
                    "previous_response_id": persisted_state.previous_response_id,
                    "tools": [
                        {
                            "type": "computer-preview",
                            "display_width": size.width,
                            "display_height": size.height,
                            "environment": args.environment,
                        }
                    ],
                    "input": (
                        [
                            {
                                "type": "computer_call_output",
                                "call_id": persisted_state.previous_computer_id,
                                "output": {
                                    "type": "input_image",
                                    "image_url": f"data:image/png;base64,{base64_screenshot_data}",
                                },
                            },
                        ]
                        if persisted_state.next_action == "computer_tool_output" else user_message
                    )
                },
                step_name=f"step {step_count}",
                suppress_input=args.no_input,
                config=config,
                json_print_redact_path=(
                    [".input[0].output.image_url"] if persisted_state.next_action == "computer_tool_output" else []
                ),
            )
            persisted_state = PersistentState(next_response)


if __name__ == "__main__":
    main()