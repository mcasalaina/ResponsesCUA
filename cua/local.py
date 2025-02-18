
import asyncio
import io
import logging
import platform
import pyautogui

class Machine:
    """Controls the local computer by using pyautogui to take screenshots and perform actions."""

    def __init__(self):
        screenshot = pyautogui.screenshot()
        self.width, self.height = screenshot.size
        system = platform.system()
        if system == "Windows":
            self.environment = "windows"
        elif system == "Darwin":
            self.environment = "mac"
        elif system == "Linux":
            self.environment = "linux"
        else:
            raise NotImplementedError(f"Unsupported operating system: '{system}'")

    async def take_screenshot(self):
        screenshot = pyautogui.screenshot()
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        buffer.seek(0)
        return bytearray(buffer.getvalue())

    async def handle_tool_call(self, action: str, action_args: dict) -> bytearray:
        if action not in ("initialize", "get", "screenshot"):
            await self.take_action(action, action_args)

        # Take a screenshot after the action
        return await self.take_screenshot()

    async def take_action(self, action: str, action_args: dict): # pylint: disable=too-many-branches
        if action == "click":
            x, y = action_args["x"], action_args["y"]
            if 0 <= x < self.width and 0 <= y < self.height:
                button = action_args["button"]
                button = "middle" if button == "wheel" else button
                pyautogui.moveTo(x, y, duration=0.1)
                pyautogui.click(x, y, button=button)
        elif action == "double_click":
            x, y = action_args["x"], action_args["y"]
            if 0 <= x < self.width and 0 <= y < self.height:
                button = action_args["button"]
                button = "middle" if button == "wheel" else button
                pyautogui.moveTo(x, y, duration=0.1)
                pyautogui.doubleClick(x, y, button=button)
        elif action == "drag":
            path = action_args["path"]
            x, y = path[0]
            pyautogui.moveTo(x, y, duration=0.1)
            pyautogui.mouseDown()
            for x, y in path[1:]:
                pyautogui.moveTo(x, y, duration=0.1)
            pyautogui.mouseUp()
        elif action == "keypress":
            for key in action_args["keys"]:
                key = key.lower()
                pyautogui.keyDown(key)
            for key in action_args["keys"]:
                key = key.lower()
                pyautogui.keyUp(key)
        elif action == "move":
            x, y = action_args["x"], action_args["y"]
            pyautogui.moveTo(x, y, duration=0.1)
        elif action == "scroll":
            x, y = action_args["x"], action_args["y"]
            pyautogui.moveTo(x, y, duration=0.1)
            scroll_x, scroll_y = action_args["scroll_x"], action_args["scroll_y"]
            pyautogui.vscroll(scroll_y)
            pyautogui.hscroll(scroll_x)
        elif action == "type":
            pyautogui.write(action_args["text"])
        elif action == "wait":
            await asyncio.sleep(1)
        else:
            logging.critical("Invalid action: %s", action)
            return ""
