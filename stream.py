from langchain_ollama.llms import OllamaLLM
from get_vector_db import get_vector_db
from get_retriever import get_retriever
import os



os.environ["USER_AGENT"] = "akolodk/testing RAG"

# Use the model with streaming
# and print tokens as they arrive
def chat_stream(model, prompt):
    print("Streaming started")
    for token in model.stream(input=prompt):
        print(token, end='', flush=True)
        yield token
        


# Initialize the Ollama model
ollama_model = OllamaLLM(
    #model="deepseek-r1",  # Replace with your desired Ollama model
    #model="deepseek-r1:1.5b",
    model="llama3.2",
    base_url="http://172.28.193.30:11434",  # Ensure Ollama server is running
    num_ctx=4096, # make the context larger
    top_k=20, # Reduces the probability of generating nonsense.
    top_p=0.2, # Works together with top-k. A higher value (e.g., 0.95) will lead to more diverse text, while a lower value (e.g., 0.5) will generate more focused and conservative text. (Default: 0.9)
    #mirostat_tau=1,
    num_predict=2500,
    keep_alive=600,
    temperature=0.2 #The temperature of the model. Increasing the temperature will make the model answer more creatively. (Default: 0.8)
)

db = get_vector_db()
prompt = "How does BGP generate an invoice?"

retriever = get_retriever(db, 9)

#docs = db.similarity_search(prompt, k=20)

docs = retriever.invoke(prompt)

print(f"\n\n ---------------- Context {len(docs)}-------")
for i, doc in enumerate(docs, start=0):
     print(docs[i].metadata)

# print("\n\n ---------------- Context end")

# Combine the context from the retrieved documents
context = "\n\n".join([doc.page_content for doc in docs])

# Create a new prompt with the context
contextual_prompt = f"""
Answer the question based on the provided context (in markdown format) from System Architecture Specification:
{context}

Answer the question as best as you can:
{prompt}
"""

for x in chat_stream(ollama_model, contextual_prompt):
    print(x, end='', flush=True)




print("\n\nStreaming complete.")  # Indicate that streaming is done
