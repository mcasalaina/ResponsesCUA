import os
import urllib.request
import urllib.error
import urllib.parse
import json
from typing import Any, Optional

Json = dict[str, Any]


class OpenAIError(Exception):
    request_id: str
    status_code: int
    message: Json

    def __init__(self, status_code: int, message: Json, request_id: str):
        self.status_code = status_code
        self.message = message
        self.request_id = request_id
        super().__init__(f"OpenAI API error: {status_code} {message}")

    def __str__(self):
        return f"OpenAI API error: {self.request_id} {self.status_code} {json.dumps(self.message, indent=2)}"


def compact(json: Json) -> Json:
    """
    Compact JSON by removing null values
    """
    return {k: v for k, v in json.items() if v is not None}


class ResponsesClient:
    def __init__(self, api_key: str):
        self.headers = {
            "Content-Type":"application/json", 
             "api-key": os.getenv("AZURE_OPENAI_API_KEY"), 
             "x-ms-enable-preview": "true"
        }

    def create(
        self,
        model: str,
        previous_response_id: Optional[str] = None,
        input: Optional[list[Json]] = None,
        tool_output: Optional[list[Json]] = None,
        include: Optional[list[str]] = None,
        tools: Optional[list[Json]] = None,
        metadata: Optional[Json] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        parallel_tool_calls: Optional[bool] = None,
    ) -> Json:
        return self._post(
            url=os.getenv("AZURE_OPENAI_ENDPOINT")+f"/openai/responses?api-version=2024-12-01-preview",
            data={
                "model": model,
                "previous_response_id": previous_response_id,
                "input": input,
                "tool_output": tool_output,
                "include": include,
                "tools": tools,
                "metadata": metadata,
                "temperature": temperature,
                "top_p": top_p,
                "parallel_tool_calls": parallel_tool_calls,
            },
        )

    def retrieve(self, response_id: str, include: Optional[list[str]] = None) -> Json:
        params = []
        for includable in include or []:
            params.append(f"include[]={includable}")

        return self._get(
            url=os.getenv("AZURE_OPENAI_ENDPOINT")+f"/openai/responses/{response_id}?api-version=2024-12-01-preview"
        )

    def _get(self, url) -> Json:
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req) as response:
                return self._handle_response(response)
        except urllib.error.HTTPError as exception:
            self._handle_exception(exception)

    def _post(self, url, data: Json) -> Json:
        headers = {**self.headers, "content-type": "application/json"}
        data = json.dumps(compact(data)).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req) as response:
                return self._handle_response(response)
        except urllib.error.HTTPError as exception:
            self._handle_exception(exception)

    def _handle_exception(self, exception: urllib.error.HTTPError) -> None:
        body = json.loads(exception.file.read().decode("utf-8"))
        request_id = exception.headers.get("x-request-id")
        raise OpenAIError(
            request_id=request_id, status_code=exception.code, message=body
        )

    def _handle_response(self, response) -> Json:
        content = response.read().decode("utf-8")
        return json.loads(content)


class OpenAIBeta:
    api_key: str

    def __init__(self, api_key: str):
        self.api_key = api_key

    @property
    def responses(self) -> ResponsesClient:
        return ResponsesClient(self.api_key)


class OpenAIResponsesPilotClient:
    api_key: str

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")

    @property
    def beta(self) -> OpenAIBeta:
        return OpenAIBeta(api_key=self.api_key)
