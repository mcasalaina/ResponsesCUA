'''To test that the client library is working correctly, you can generate a text response to a prompt,
much as you could using the existing chat completions API. The following code assumes it is being
run in the same folder as “openai_pilot.py”. Be sure to also have your OPENAI_API_KEY system
environment variable set:'''
from pprint import pprint
from openai_pilot import OpenAIResponsesPilotClient
# Client initialized using OPENAI_API_KEY environment variable
client = OpenAIResponsesPilotClient()
# Create a generated response
response = client.beta.responses.create(
 model="gpt-4o-mini",
 input="tell me a joke",
)
# Retrieve a previously generated response by ID
fetched_response = client.beta.responses.retrieve(response["id"])
pprint(fetched_response)