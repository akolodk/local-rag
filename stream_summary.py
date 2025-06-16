from langchain_ollama.llm import OllamaLLM

import sys
from pathlib import Path
parent_dir = str(Path(__file__).parent.parent)
sys.path.append(parent_dir)

from confluence_ai.load import load_page

# Initialize the Ollama model
ollama_model = OllamaLLM(
    #model="deepseek-r1",  # Replace with your desired Ollama model
    #model="deepseek-r1:1.5b",
    #model="llama3.1",
    model="llama3.2",
    #model="mistral",
    base_url="http://172.28.193.30:11434",  # Ensure Ollama server is running
    num_ctx=8192, # make the context larger
    top_k=20,
    top_p=0.5,
    mirostat_tau=4,
    num_predict=1300,
    keep_alive=1200
    #top
)


# Combine the context from the retrieved documents
docs = load_page()
context = "\n\n".join([doc.page_content for doc in docs])

# Create a new prompt with the context
contextual_prompt = f"""\
Here is a Use case text:

{context}

provide a concise summary for the use case, do not skip anything important, include Title, Description, Key Features and Requirements only.
Go as long as necessary to list all requirements, do not copy text from the context."""

# Use the model with streaming
# and print tokens as they arrive
for token in ollama_model.stream(input=contextual_prompt):
    print(token, end='', flush=True)

print("\n\nDone answering.")  # Indicate that streaming is done
