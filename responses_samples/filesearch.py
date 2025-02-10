'''File search is a tool offered to provide additional context to your own data. If you do not have your own vector index, 
follow the steps to make one here: FINISH THIS'''
from openai_pilot import OpenAIResponsesPilotClient
client = OpenAIResponsesPilotClient()
vector_store_id = "VECTOR_STORE_ID"
response = client.beta.responses.create(
    model="gpt-4o",
    tools=[
        {
            "type": "file_search",
            "vector_store_ids": [vector_store_id],
        }
    ],
 input="Search the document for 'population of seattle'.",
)

print(response)

# View the search results the model saw
response = client.beta.responses.retrieve(
 response["id"],
 include=["output[*].file_search_call.search_results"],
)

# You can also control the number of search results the model sees...
response = client.beta.responses.create(
    model="gpt-4o",
    tools=[
        {
            "type": "file_search",
            "vector_store_ids": [vector_store_id],
            "max_num_results": 2,
        }
    ],
    input=[
        {
            "role": "user",
            "text": "Search the document for 'population of seattle'.",
        }
    ],
)