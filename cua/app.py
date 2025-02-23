'''
This is a simple example of how to use the CUA model along with the Responses API.
When running the script, you will be prompted to give the CUA model a task to complete.
The CUA model will take the screenshot of the current screen, and then take action to try and complete the task.
Make sure to install the required packages before running the script.
'''

import argparse
import logging
import os

import openai_pilot
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
    parser.add_argument("--autoenter", dest="autoenter", default=True, action="store_true")
    parser.add_argument("--environment", dest="environment", default="linux")
    parser.add_argument("--no-input", dest="no_input", default=True, help="Whether or not to run through the demo without any input from the user", action="store_true")
    parser.add_argument("--vm-address", dest="vm_address", help="The address of the VM to use", type=str, default=None)
    parser.add_argument("--alt-screen-size", default=False, dest="alt_screen_size", action="store_true")
    args = parser.parse_args()

    if args.endpoint == "azure":
        base_url = os.environ.get("AZURE_OPENAI_ENDPOINT")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        api_version = "2024-12-01-preview"
        client = openai_pilot.OpenAIResponsesPilotClient(api_key, base_url, api_version)
    else:
        base_url = "https://api.openai.com"
        api_key = os.environ.get("OPENAI_API_KEY")
        api_version = None
        client = openai_pilot.OpenAIResponsesPilotClient(api_key)

    model = args.model

    # Machine is used to take screenshots and send keystrokes or mouse clicks
    machine = local.Machine() if args.vm_address is None else vnc.Machine(address=args.vm_address, environment=args.environment)

    # Scaler is used to resize the screen to a smaller size
    size = (1920, 1080) if args.alt_screen_size else (1024, 768)
    machine = cua.Scaler(*size, machine)

    # Agent to run the CUA model and keep track of state
    agent = cua.Agent(client, model, machine)

    # Get the user request
    user_message = args.instructions if args.instructions else input("Please enter the initial task for the computer: ")

    agent.start_task(user_message)
    while True:
        user_message = None
        if agent.requires_consent() and not args.autoenter:
            input("Press Enter to run computer tool...")
        elif agent.requires_user_input():
            print(f"Agent: {" ".join(agent.state.output_text)}")
            user_message = input("Please enter your message to continue: ")
        agent.continue_task(user_message)

if __name__ == "__main__":
    main()
