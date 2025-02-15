
import asyncio
import base64
import io
import logging
import platform
import PIL
import pyautogui

# Controls the local computer by using pyautogui to take screenshots and perform actions
class Machine:

    def __init__(self, width=1024, height=768):
        self.width = width
        self.height = height
        screenshot = pyautogui.screenshot()
        self.screen_width, self.screen_height = screenshot.size
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
        image_buffer = io.BytesIO()
        screenshot.save(image_buffer, format="PNG")
        image_buffer.seek(0)
        image = PIL.Image.open(image_buffer)
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
        image_data = padded_image_buffer.getvalue()
        screenshot_base64 = base64.b64encode(image_data).decode("utf-8")
        return screenshot_base64

    async def take_action(self, action: str, action_args: dict) -> str:
        if action in ("initialize", "get", "screenshot"):
            return await self.take_screenshot()

        if action == "click":
            x, y = self._point_to_screen_coords(action_args["x"], action_args["y"])
            if 0 <= x < self.screen_width and 0 <= y < self.screen_width:
                button = action_args["button"]
                pyautogui.moveTo(x, y, duration=0.5)
                pyautogui.click(x, y, button=button)
        elif action == "double_click":
            x, y = self._point_to_screen_coords(action_args["x"], action_args["y"])
            if 0 <= x < self.screen_width and 0 <= y < self.screen_width:
                button = action_args["button"]
                pyautogui.moveTo(x, y, duration=0.5)
                pyautogui.doubleClick(x, y, button=button)
        elif action == "drag":
            path = action_args["path"]
            x, y = path[0]
            pyautogui.moveTo(x, y, duration=0.5)
            pyautogui.mouseDown()
            for x, y in path[1:]:
                pyautogui.moveTo(x, y, duration=0.5)
            pyautogui.mouseUp()
        elif action == "keypress":
            for key in action_args["keys"]:
                key = key.lower()
                pyautogui.keyDown(key)
            for key in action_args["keys"]:
                key = key.lower()
                pyautogui.keyUp(key)
        elif action == "move":
            point = self._point_to_screen_coords(action_args["x"], action_args["y"])
            pyautogui.moveTo(point, duration=0.5)
        elif action == "scroll":
            raise NotImplementedError("scroll")
            # await self.vnc.scroll(
            #     position=(action_args["x"], action_args["y"]),
            #     horizontal=action_args["scroll_x"],
            #     vertical=action_args["scroll_y"],
            # )
        elif action == "type":
            pyautogui.write(action_args["text"])
        elif action == "wait":
            await asyncio.sleep(1)
        else:
            logging.critical("Invalid action: %s", action)
            return ""

        # Take a screenshot after the action
        return await self.take_screenshot()

    async def handle_tool_call(self, action: str, action_args: dict) -> str:
        logging.info("  action %s (%s)", action, action_args)
        screenshot_base64 = await self.take_action(action, action_args)
        if screenshot_base64:
            logging.debug("  screenshot (partial): %s...", screenshot_base64[:20])
            return screenshot_base64
        return ""

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
