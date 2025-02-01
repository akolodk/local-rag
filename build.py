import os
from datetime import datetime
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_community.document_transformers import Html2TextTransformer
from langchain.text_splitter import MarkdownTextSplitter
from langchain_text_splitters import RecursiveCharacterTextSplitter
from get_vector_db import get_vector_db
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from langchain.retrievers import ParentDocumentRetriever
from langchain.storage import LocalFileStore
from langchain.storage._lc_store import create_kv_docstore
from get_retriever import get_retriever

STORE_PATH = os.getenv('STORE_PATH', 'store')

def extract_urls(url):
    """
    Extract all URLs from a webpage and return them as a list.
    
    Args:
        url (str): The URL of the webpage to scrape
        
    Returns:
        list: List of all URLs found on the page
    """
    # List to store URLs
    urls = []
    
    try:
        # Send GET request to the URL
        response = requests.get(url)
        response.raise_for_status()
        
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all <a> tags
        for link in soup.find_all('a'):
            href = link.get('href')
            if href:
                # Convert relative URLs to absolute URLs
                absolute_url = urljoin(url, href)
                urls.append(absolute_url)

        urls = [#'http://dingo:8080/11.00/cb/server/src/std/doc/std_sas.html',
                'http://dingo:8080/11.00/cb/server/src/bgp/doc/bgp_sas.html',
                #'http://dingo:8080/11.00/cb/server/src/rgp/doc/rgp_sas.html',
                #'http://dingo:8080/11.00/cb/server/src/igp/doc/igp_sas.html',
                #'http://dingo:8080/11.00/cb/server/src/sep/doc/sep_sas.html'
                ]


        return urls
    
    except Exception as e:
        print(f"An error occurred: {e}")
        return []
    

def build(url):
    db = get_vector_db()
    urls = extract_urls(url)
    print(urls)  
    loader = AsyncHtmlLoader(urls)
    docs = loader.load()
    html2text = Html2TextTransformer()
    print(f'transforming...') 
    docs_transformed = html2text.transform_documents(docs)
    print(docs_transformed)
    # Initialize the MarkdownTextSplitter
    print(f'splitting...') 
    #splitter = MarkdownTextSplitter(chunk_size=500, chunk_overlap=50)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    
    
    for doc in docs_transformed:
        #chunks = splitter.split_text(doc.page_content)
        chunks = text_splitter.split_documents(docs)
        #db.add_texts(chunks)
        db.add_documents(chunks)
        #Display the chunks
        for i, chunk in enumerate(chunks):
            print(f"Chunk {i + 1}:\n{chunk}\n")    
    return True

def build_1(url):
    db = get_vector_db()
    urls = extract_urls(url)
    print(urls)  
    loader = AsyncHtmlLoader(urls)
    docs = loader.load()
    html2text = Html2TextTransformer()
    print(f'transforming...') 
    docs_transformed = html2text.transform_documents(docs)
    print(docs_transformed)

    f = open("demofile3.txt", "w")

    for doc in docs_transformed:
       f.write(doc.page_content)
    f.close()

    # Initialize the MarkdownTextSplitter
    print(f'splitting...') 
    parent_splitter = MarkdownTextSplitter(chunk_size=4000, chunk_overlap=0)
    child_splitter = MarkdownTextSplitter(chunk_size=200, chunk_overlap=50) 
    # The storage layer for the parent documents

    fs = LocalFileStore(f"./{STORE_PATH}")
    store = create_kv_docstore(fs)
    # Initialize the retriever
    retriever = ParentDocumentRetriever(
        vectorstore=db,
        docstore=store,
        child_splitter=child_splitter,
        parent_splitter=parent_splitter,
    )

    retriever.add_documents(docs_transformed)
 
    return True