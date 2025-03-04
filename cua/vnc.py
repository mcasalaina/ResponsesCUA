
import asyncio
import math
import time
from contextlib import contextmanager
from typing import Iterator, Literal
from vncdotool import api

class Machine:
    """Controls a remote computer by using VNC to take screenshots and perform actions."""

    def __init__(self, width=1024, height=768, address=None, environment="browser"):
        self.width = width
        self.height = height
        self.vnc = VNCMachine(address)
        self.environment = environment

    async def take_screenshot(self):
        image_path = 'screenshot.png'
        await self.vnc.screenshot(screenshot_name=image_path, keys=None)
        with open(image_path, 'rb') as image_file:
            return image_file.read()

    async def take_action(self, action: str, action_args: dict):
        if action == "click":
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
            raise ValueError(f"Invalid action: {action}")

    async def handle_tool_call(self, action: str, action_args: dict) -> bytearray:
        if action not in ("initialize", "get", "screenshot"):
            await self.take_action(action, action_args)

        # Take a screenshot after the action
        return await self.take_screenshot()


# ---[ VNC ]--------------------------------------
# Based on the VNC protocol
# https://github.com/sibson/vncdotool/blob/0.13/vncdotool/client.py#L21
CUA_KEY_TO_VNC_KEY: dict[str, str] = {
    "/": "fslash",
    "\\": "bslash",
    "alt": "alt",
    "arrowdown": "down",
    "arrowleft": "left",
    "arrowright": "right",
    "arrowup": "up",
    "backspace": "bsp",
    "capslock": "caplk",
    "cmd": "super",
    "ctrl": "ctrl",
    "delete": "delete",
    "end": "end",
    "enter": "enter",
    "esc": "esc",
    "home": "home",
    "insert": "ins",
    "option": "alt",
    "pagedown": "pgdn",
    "pageup": "pgup",
    "shift": "shift",
    "space": "spacebar",
    "super": "super",
    "tab": "tab",
    "win": "super",
}


def cua_key_to_vnc_key(key: str) -> str:
    """
    Maps from our standard key definition to the VNC key definition
    More at: http://go/docs-link/cua-keyboard-keys
    """
    key = key.lower()
    return (CUA_KEY_TO_VNC_KEY.get(key) or key)


class VNCMachine:
    def __init__(self, address: str) -> None:
        self.address = address
        self.mouse_last_position = None

    async def _get_vnc_client(self) -> api.ThreadedVNCClientProxy:
        """
        Return the VNC client connected to this machine.
        """
        return api.connect(self.address,password=None)

    async def type(self, text: str) -> None:
        client = await self._get_vnc_client()
        client.factory.force_caps = True
        for char in text:
            if char == "\n":
                client.keyPress("enter")
            elif char == "\t":
                client.keyPress("tab")
            else:
                client.keyPress(char)
            time.sleep(0.06)

    async def multi_key_press(self, keys: list[str]) -> None:
        client = await self._get_vnc_client()
        with self.hold_keys(client, keys):
            pass

    async def move_mouse(
        self,
        position: tuple[int, int],
        keys: list[str] | None = None,
    ) -> None:
        client = await self._get_vnc_client()
        with self.hold_keys(client, keys):
            self._move_mouse_internal(position, client, 0.0002)

    async def mouse_click(
        self,
        position: tuple[int, int],
        action: Literal["click", "double_click"],
        button: int = 1,
        keys: list[str] | None = None,
    ) -> None:
        client = await self._get_vnc_client()
        with self.hold_keys(client, keys):
            self._move_mouse_internal(position, client)
            time.sleep(0.05) #wait for mouse to stabalize
            if action == "click":
                client.mousePress(button)
            elif action == "double_click":
                client.mousePress(1)
                time.sleep(0.05)
                client.mousePress(1)

    async def screenshot(self, keys: list[str], screenshot_name='screenshot.png') -> None:
        client = await self._get_vnc_client()
        with self.hold_keys(client, keys):
            client.local_cursor = True
            client.captureScreen(screenshot_name)

    async def drag_mouse(
        self,
        path: list[tuple[int, int]],
        keys: list[str] | None = None,
    ) -> None:
        if not path or len(path) < 2:
            raise ValueError("At least two points are required for a multi-point drag.")

        client = await self._get_vnc_client()
        with self.hold_keys(client, keys):
            self._move_mouse_internal(path[0], client)

            time.sleep(0.05)
            client.mouseDown(1)
            time.sleep(0.05)

            for point in path[1:]:
                self._move_mouse_internal(point, client, delay=0.005)

            client.mouseUp(1)
            time.sleep(0.05)

    async def scroll(
        self,
        position: tuple[int, int],
        horizontal: int,
        vertical: int,
        keys: list[str] | None = None,
    ) -> None:
        x, y = position
        keys = keys or []

        client = await self._get_vnc_client()
        self._move_mouse_internal((x, y), client)
        with self.hold_keys(client, keys):
            if vertical != 0:
                self._scroll_with_delay(vertical, 5 if vertical > 0 else 4, client)

            if horizontal != 0:
                with self.hold_keys(client, ["shift"]):
                    self._scroll_with_delay(horizontal, 5 if horizontal > 0 else 4, client)

    def _scroll_with_delay(
        self,
        scroll_amount: int,
        direction: int,
        client: api.ThreadedVNCClientProxy,
        delay: float = 0.05,
    ) -> None:
        scroll_amount = abs(int(scroll_amount / 10))
        for _ in range(scroll_amount + 2):
            client.mousePress(direction)
            time.sleep(delay)

    def _move_mouse_internal(
        self,
        position: tuple[int, int],
        client: api.ThreadedVNCClientProxy,
        delay: float = 0.0002,
    ) -> None:
        if not hasattr(self, 'mouse_last_position') or self.mouse_last_position is None: #assuming some arbitrary initial position
            self.mouse_last_position = (100, 100)
        x1, y1 = self.mouse_last_position
        x2, y2 = position
        steps = max(int(math.hypot(x2 - x1, y2 - y1)), 1)
        for i in range(1, steps + 1):
            client.mouseMove(int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps))
            time.sleep(delay)
        self.mouse_last_position = position
        time.sleep(0.05)  # Wait for the mouse to settle

    @staticmethod
    @contextmanager
    def hold_keys(
        client: api.ThreadedVNCClientProxy, keys: list[str] | None = None
    ) -> Iterator[None]:
        keys = keys or []
        client.factory.force_caps = True
        try:
            for key in keys:
                key = cua_key_to_vnc_key(key=key)
                client.keyDown(key)
            yield
        finally:
            for key in reversed(keys):
                key = cua_key_to_vnc_key(key=key)
                client.keyUp(key)
