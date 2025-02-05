import os
from langchain.retrievers import ParentDocumentRetriever
from langchain.text_splitter import MarkdownTextSplitter, TextSplitter, MarkdownHeaderTextSplitter
from langchain.storage import LocalFileStore
from langchain.storage._lc_store import create_kv_docstore

STORE_PATH = os.getenv('STORE_PATH', 'store')

def get_retriever(db, k=4, parent_splitter=MarkdownTextSplitter(), child_splitter=MarkdownTextSplitter()) -> ParentDocumentRetriever:

    # The storage layer for the parent documents
    fs = LocalFileStore(f"./{STORE_PATH}")
    store = create_kv_docstore(fs)
    # Initialize the retriever
    retriever = ParentDocumentRetriever(
        vectorstore=db,
        docstore=store,
        child_splitter=child_splitter,
        parent_splitter=parent_splitter,
        search_kwargs={"k": k}
    )
    return retriever
