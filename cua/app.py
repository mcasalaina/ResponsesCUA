'''
This is a basic example of how to use the CUA model along with the Responses API.
The CUA model will take the screenshot of the current screen, and then take action to try and complete the task.
Make sure to install the required packages before running the script.
'''

import argparse
import logging
import os

import openai
import cua
import local
import vnc

def main():
    logging.basicConfig(level=logging.WARNING, format='%(message)s')
    logging.getLogger("cua").setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument("--instructions", dest="instructions", help="Instructions to follow", default="Open web browser and go to microsoft.com.")
    parser.add_argument("--model", dest="model", default="computer-use-preview")
    parser.add_argument("--endpoint", default="azure", help="The endpoint to use, either openai or azure")
    parser.add_argument("--autoplay", dest="autoplay", help="Autoplay VM actions without confirmation, only pause when the turn ends", action="store_true", default=True)
    parser.add_argument("--environment", dest="environment", default="linux")
    parser.add_argument("--vm-address", dest="vm_address", help="The address of the VM to use", type=str, default=None)
    args = parser.parse_args()

    if args.endpoint == "azure":
        base_url = os.environ.get("AZURE_OPENAI_ENDPOINT") # TODO
        api_key = os.environ.get("AZURE_OPENAI_API_KEY") # TODO
        api_version = "2024-12-01-preview" # TODO: 2025-03-01-preview
        client = openai.AzureOpenAI(azure_endpoint=base_url, api_key=api_key, api_version=api_version,
            default_headers = {"x-ms-enable-preview": "true"})
    else:
        client = openai.OpenAI()

    model = args.model

    # Machine is used to take screenshots and send keystrokes or mouse clicks
    machine = local.Machine() if args.vm_address is None else vnc.Machine(address=args.vm_address, environment=args.environment)

    # Scaler is used to resize the screen to a smaller size
    size = (1024, 768)
    machine = cua.Scaler(*size, machine)

    # Agent to run the CUA model and keep track of state
    agent = cua.Agent(client, model, machine)

    # Get the user request
    user_message = args.instructions if args.instructions else input("Please enter the initial task for the computer: ")

    agent.start_task(user_message)
    while True:
        user_message = None
        if agent.state.last_message:
            print(f"\nAgent: {agent.state.last_message}\n")
        if agent.requires_consent() and not args.autoplay:
            input("Press Enter to run computer tool...")
        elif agent.pending_safety_checks() and not args.autoplay:
            input(f"Press Enter to acknowledge the following safety checks: {agent.requires_safety_check()}...")
        elif agent.requires_user_input():
            user_message = input("Please enter your message to continue: ")
        agent.continue_task(user_message)

if __name__ == "__main__":
    main()
