'''To share context across several generated responses, you can use the “previous_response_id”
parameter to implement a threaded conversation.'''
from pprint import pprint
from openai_pilot import OpenAIResponsesPilotClient
client = OpenAIResponsesPilotClient()
response = client.beta.responses.create(
     model="gpt-4o-mini",
     input="tell me a joke",
)

second_response = client.beta.responses.create(
    model="gpt-4o-mini",
    previous_response_id=response["id"],
    input=[{"role": "user", "content": "explain why this is funny."}],
)

pprint(second_response)
