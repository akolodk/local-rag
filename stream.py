from langchain_ollama.llms import OllamaLLM
from get_vector_db import get_vector_db
from get_retriever import get_retriever

# Initialize the Ollama model
ollama_model = OllamaLLM(
    #model="deepseek-r1",  # Replace with your desired Ollama model
    #model="deepseek-r1:1.5b",
    model="llama3.2",
    base_url="http://172.28.193.30:11434",  # Ensure Ollama server is running
    num_ctx=4096, # make the context larger
    top_k=70,
    top_p=0.5,
    mirostat_tau=4,
    num_predict=300,
    keep_alive=600
)

db = get_vector_db()
prompt = "how biInvoiceGenerate is implemented?"

retriever = get_retriever(db, 7)

#docs = db.similarity_search(prompt, k=20)

docs = retriever.invoke(prompt)

print(f"\n\n ---------------- Context {len(docs)}-------")
# for i, doc in enumerate(docs, start=0):
#     print(docs[i].page_content)

# print("\n\n ---------------- Context end")

# Combine the context from the retrieved documents
context = "\n\n".join([doc.page_content for doc in docs])

# Create a new prompt with the context
contextual_prompt = f"""\
You are a Singleview Senior Architect. Singleview is a multi-tier billing and charging application.
Answer the question based on the provided context (in markdown format) from System architecture specification:
{context}

Answer the question as best as you can:
{prompt}
"""

# Use the model with streaming
# and print tokens as they arrive
for token in ollama_model.stream(input=contextual_prompt):
    print(token, end='', flush=True)

print("\n\nStreaming complete.")  # Indicate that streaming is done
