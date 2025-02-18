'''You can use external data sources and other APIs to generate more contextually appropriate
responses with function calling. Functions are configured as available tools.'''

from pprint import pprint
from openai_pilot import OpenAIResponsesPilotClient
client = OpenAIResponsesPilotClient()
response = client.beta.responses.create(
    model="gpt-4o-mini",
    tools=[
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get the weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    },
                "required": ["location"],
                },
        }
    ],
    input=[{"role": "user", "content": "What's the weather in San Francisco?"}],
)

# To provide output to tools, add a response for each tool call to an array passed
# to the next response as `input`
input = []
for output in response["output"]:
   if output["type"] == "function_call":
    match output["name"]:
        case "get_weather":
            input.append(
          {
            "type": "function_call_output",
            "call_id": output["id"],
            "output": '{"temperature": "70 degrees"}',
          }
        )
        case _:
            raise ValueError(f"Unknown function call: {output['name']}")

response_2 = client.beta.responses.create(
  model="gpt-4o-mini",
  previous_response_id=response["id"],
  input=input
)
pprint(response_2)