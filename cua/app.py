'''
This is a simple example of how to use the CUA model along with the Responses API.
When running the script, you will be prompted to give the CUA model a task to complete.
The CUA model will take the screenshot of the current screen, and then take action to try and complete the task.
Make sure to install the required packages before running the script.
'''

import argparse
import logging
import os

import cua
import local
import vnc

def main():

    logging.basicConfig(level=logging.WARNING, format='%(message)s')
    logging.getLogger("cua").setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument("--machine", dest="machine", help="The machine to use", type=str, default="local")
    parser.add_argument("--instructions", dest="instructions", help="Instructions to follow")
    parser.add_argument("--model", dest="model", default="computer-use-alpha")
    parser.add_argument("--autoenter", dest="autoenter", default=True, action="store_true")
    parser.add_argument("--environment", dest="environment", default="linux")
    parser.add_argument("--no-input", dest="no_input", default=True, help="Whether or not to run through the demo without any input from the user", action="store_true")
    parser.add_argument("--vm_address", dest="vm_address", help="The address of the VM to use", type=str, default="192.168.236.154")
    parser.add_argument("--alt-screen-size", default=False, dest="alt_screen_size", action="store_true")
    args = parser.parse_args()

    # OpenAI endpoint
    client = cua.Client(
        base_url="https://api.openai.com",
        api_key=os.environ.get("OPENAI_API_KEY"))

    # Azure OpenAI endpoint
    client = cua.Client(
        base_url=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
        api_version="2024-12-01-preview")

    model = args.model
    model = 'cua-bugbash'

    user_message = "Open web browser and go to microsoft.com."
    # user_message = args.instructions if args.instructions else input("Please enter the initial task for the computer: ")

    if args.machine == "local":
        machine = local.Machine()
    else:
        machine = vnc.Machine(args.vm_address, args.environment)

    size = (1920, 1080) if args.alt_screen_size else (1024, 768)
    machine = cua.Scaler(*size, machine)

    agent = cua.Agent(client, model, machine)
    agent.start_task(user_message)
    while True:
        user_message = None
        if agent.requires_consent() and not args.autoenter:
            input("Press Enter to run computer tool...")
        elif agent.requires_user_input():
            user_message = input("Please enter your message to continue: ")
        agent.continue_task(user_message)

if __name__ == "__main__":
    main()
