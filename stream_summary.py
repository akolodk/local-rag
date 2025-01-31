from langchain_ollama.llms import OllamaLLM

import sys
from pathlib import Path
parent_dir = str(Path(__file__).parent.parent)
sys.path.append(parent_dir)

from confluence_ai.load import load_page

# Initialize the Ollama model
ollama_model = OllamaLLM(
    #model="deepseek-r1",  # Replace with your desired Ollama model
    model="deepseek-r1:1.5b",
    #model="llama3.2",
    base_url="http://172.28.193.30:11434",  # Ensure Ollama server is running
    num_ctx=8192 # make the context larger
    #top
)


# Combine the context from the retrieved documents
docs = load_page()
context = "\n\n".join([doc.page_content for doc in docs])

# Create a new prompt with the context
contextual_prompt = f"""\
Here is a text in markdown format:
{context}

extract explicit and implicit requirements.
"""

# Use the model with streaming
# and print tokens as they arrive
for token in ollama_model.stream(input=contextual_prompt):
    print(token, end='', flush=True)

print("\n\nDone answering.")  # Indicate that streaming is done
