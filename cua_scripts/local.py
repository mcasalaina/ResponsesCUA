
import asyncio
import base64
import io
import PIL
import pyautogui

# Use pyautogui to drive local machine
class LocalManager:
    def __init__(self):
        self.target_width, self.target_height = 1024, 768
        screenshot = pyautogui.screenshot()
        self.screen_width, self.screen_height = screenshot.size

    async def take_screenshot(self):
        screenshot = pyautogui.screenshot()
        screenshot.save("screenshot.png")
        screenshot = PIL.Image.open("screenshot.png")
        self.screen_width, self.screen_height = screenshot.size
        aspect_ratio = self.screen_width / self.screen_height
        if aspect_ratio > 1:
            new_width = self.target_width
            new_height = int(self.target_width / aspect_ratio)
        else:
            new_height = self.target_height
            new_width = int(self.target_height * aspect_ratio)
        resized_screenshot = screenshot.resize((new_width, new_height), PIL.Image.Resampling.LANCZOS)
        padded_image = PIL.Image.new("RGB", (self.target_width, self.target_height), (0, 0, 0))
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
        self, dir: str, action: str, action_args: dict, step_count: int, resize: tuple[int, int] = None
    ) -> str:
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

        print(f"Screenshot (partial): {screenshot_base64[:100]}...")
        return screenshot_base64
