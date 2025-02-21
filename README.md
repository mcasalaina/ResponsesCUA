# ResponsesCUAPrPr

Welcome to the Responses API + CUA Private Preview!

The Responses API is the newest API from AOAI. Think of it as an update to the ChatCompletions API that now additionally supports conversation threading and tool calling. The CUA (Computer-Using Agent) model is a new model from AOAI that can interact with GUIs, like a human would. 

How the CUA model works is the following: the CUA model for input on the first turn takes a set of instructions from the user of a task to be accomplished i.e. "navigate to Microsoft.com." Then on the second turn, the model takes a screenshot of a GUI, and based on the screenshot will output a set of instructions to be accomplished "double click in position x,y." This second turn will be repeated until the task from the first turn has been completed. 

In this repo you will find 2 folders:
* `responses_samples` that contains basic samples for the Responses API. These include conversation threading, tool usage.
* `cua` contains a sample to run the CUA model with either a remote VNC machine or a local machine.

Please set the environment variable AZURE_OPENAI_ENDPOINT to your sub url. Should be something like https://subname-region.openai.azure.com

Please set the environment variable AZURE_OPENAI_API_KEY to your API key
