import asyncio
import logging
import os
import tempfile

from typing import Literal, NamedTuple
from dotenv import load_dotenv
from utils import get_config, get_parser, make_req, may_retry

from vnc import VNCManager
from local import LocalManager

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
    parser.add_argument("--environment", dest="environment", default="browser")
    parser.add_argument("--autoenter", dest="autoenter", default=True, action="store_true")

    args = parser.parse_args()
    config = get_config(args)
    config["API_KEY"] = api_key

    use_local_machine = True
    if use_local_machine:
        vm_manager = LocalManager()
        initial_task = "open web browser"
    else:
        vm_manager = VNCManager(address=args.vm_address)
        initial_task = (
            args.instructions
            or input("Please enter the initial task for the computer: ")
            or "Go to booking.com"
        )

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
                if not args.autoenter:
                    input("Press Enter to run computer tool...")
                base64_screenshot_data = asyncio.run(
                    vm_manager.handle_tool_call(
                        tmpdir,
                        persisted_state.computer_action,
                        persisted_state.computer_action_args,
                        step_count,
                        resize=ALT_SIZE if args.alt_screen_size else None
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
                        if persisted_state.next_action == "computer_tool_output"
                        else user_message
                    ),
                },
                step_name=f"step {step_count}",
                suppress_input=args.no_input,
                config=config,
                json_print_redact_path=(
                    [".input[0].output.image_url"]
                    if persisted_state.next_action == "computer_tool_output"
                    else []
                ),
            )
            persisted_state = PersistentState(next_response)

if __name__ == "__main__":
    main()
