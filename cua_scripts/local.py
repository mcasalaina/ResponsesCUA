
import asyncio
import base64
import io
import platform
import PIL
import pyautogui

# Use pyautogui to drive local machine
class LocalManager:

    def __init__(self):
        self.target_width, self.target_height = 1024, 768
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
            new_width = self.target_width
            new_height = int(self.target_width / aspect_ratio)
        else:
            new_height = self.target_height
            new_width = int(self.target_height * aspect_ratio)
        resized_image = image.resize((new_width, new_height), PIL.Image.Resampling.LANCZOS)
        padded_image = PIL.Image.new("RGB", (self.target_width, self.target_height), (0, 0, 0))
        x_offset = (self.target_width - new_width) // 2
        y_offset = (self.target_height - new_height) // 2
        padded_image.paste(resized_image, (x_offset, y_offset))
        padded_image_buffer = io.BytesIO()
        padded_image.save(padded_image_buffer, format="PNG")
        padded_image_buffer.seek(0)
        image_data = padded_image_buffer.getvalue()
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
            point = self.point_to_screen_coords(action_args["x"], action_args["y"])
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
            print(f"Invalid action: {action}")
            return ""

        # Take a screenshot after the action
        return await self.take_screenshot()

    async def handle_tool_call(self, action: str, action_args: dict, resize: tuple[int, int] = None) -> str:
        print(f"Running action: {action} with args: {action_args}")
        screenshot_base64 = await self.take_action(action, action_args)
        if not screenshot_base64:
            return ""

        if resize:
            print("resizing screenshot")
            screenshot_bytes = base64.b64decode(screenshot_base64)
            with PIL.Image.open(io.BytesIO(screenshot_bytes)) as img:
                resized_img = img.resize((resize[0], resize[1]), PIL.Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                resized_img.save(buffer, format=img.format)
                screenshot_bytes = buffer.getvalue()
                screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        print(f"Screenshot (partial): {screenshot_base64[:20]}...")
        return screenshot_base64
