'''In addition to textual prompts, you can also generate responses using image prompts as in the
examples below. You can pass in images using a publicly accessible URL, or by Base64 encoding
image data to send along with your API request.'''

from pprint import pprint
from openai_pilot import OpenAIResponsesPilotClient
client = OpenAIResponsesPilotClient()

response = client.beta.responses.create(
    model="gpt-4o-mini",
    input=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text", 
                    "text": "describe this image"
                    },
                {
                    "type": "input_image",
                    "image_url":
                    "https://images.unsplash.com/photo-1722359429728-49fe13071e6c?q=80&w=2957&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D",
                },
            ],
        }
    ],
)
pprint(response)


###BASE 64 IMAGE:
'''
from openai_pilot import OpenAIResponsesPilotClient
import base64
client = OpenAIResponsesPilotClient()
image_path = "PATH_TO_IMAGE"

# Read the image file in binary mode
with open(image_path, "rb") as image_file:
    image_data = image_file.read()

# Encode the image data in Base64
encoded_image = base64.b64encode(image_data)
encoded_image_str = encoded_image.decode("utf-8")
response = client.beta.responses.create(
    model="gpt-4o",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "describe this image"},
                {"type": "input_image",
                 "image_url": f"data:image/jpeg;base64,{encoded_image_str}",
                },
            ],
        }
    ],
)
'''
