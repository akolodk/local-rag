from langchain_ollama.llms import OllamaLLM
from get_vector_db import get_vector_db

# Initialize the Ollama model
ollama_model = OllamaLLM(
    model="mistral",  # Replace with your desired Ollama model
    base_url="http://172.28.193.30:11434"  # Ensure Ollama server is running
)

db = get_vector_db()
prompt = "how does BGP produce an invoice?"
docs = db.similarity_search(prompt, k=10)

#print("\n\n ---------------- Context")
#for i, doc in enumerate(docs, start=0):
#    print(docs[i].page_content)
#
#print("\n\n ---------------- Context end")

# Combine the context from the retrieved documents
context = "\n\n".join([doc.page_content for doc in docs])

# Create a new prompt with the context
contextual_prompt = f"""\
Here is some context to help answer the question:
{context}

Now, answer the question:
{prompt}
"""




# Use the model with streaming
# and print tokens as they arrive
for token in ollama_model.stream(input=contextual_prompt):
    print(token, end='', flush=True)

print("\n\nStreaming complete.")  # Indicate that streaming is done
