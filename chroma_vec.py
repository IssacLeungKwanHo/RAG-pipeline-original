import logging
import os
import glob
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
import chromadb

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

os.environ["CHROMA_TELEMETRY_ENABLED"] = "false"
os.environ["ANONYMIZED_TELEMETRY"] = "false"

def create_vector_store():
    BASE_DIR = "/Users/issacleung/ollama_trial"
    DATA_DIR = os.path.join(BASE_DIR, "data")
    CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
    
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR, settings=chromadb.Settings(allow_reset=True, anonymized_telemetry=False))
    
    logging.info("Initializing Nomic embedding model")
    try:
        embedding_model = HuggingFaceEmbeddings(
            model_name="nomic-ai/nomic-embed-text-v1.5",
            model_kwargs={"device": "cpu", "trust_remote_code": True}
        )
    except Exception as e:
        logging.error(f"Failed to initialize HuggingFaceEmbeddings: {str(e)}")
        raise Exception(f"Failed to initialize HuggingFaceEmbeddings: {str(e)}")

    logging.info("Checking for existing Chroma store")
    vector_db = None
    if os.path.exists(CHROMA_DIR):
        try:
            vector_db = Chroma(
                persist_directory=CHROMA_DIR,
                embedding_function=embedding_model,
                collection_name="local-rag",
                client=chroma_client
            )
            logging.info("Loaded existing Chroma vector store")
            test_query = "bullying and ADHD"
            retriever = vector_db.as_retriever(search_type="similarity", search_kwargs={"k": 20})
            retrieved_docs = retriever.invoke(test_query)
            logging.info(f"Test retrieval for '{test_query}': {len(retrieved_docs)} documents retrieved")
            for i, doc in enumerate(retrieved_docs):
                logging.debug(f"Retrieved document {i+1} (source: {doc.metadata.get('source', 'unknown')}): {doc.page_content[:200]}...")
            return vector_db
        except Exception as e:
            logging.warning(f"Failed to load existing Chroma store: {str(e)}. Rebuilding store.")

    txt_files = glob.glob(os.path.join(DATA_DIR, "*.txt"))
    if not txt_files:
        raise FileNotFoundError(f"No text files found in {DATA_DIR}")
    
    logging.info(f"Loading {len(txt_files)} text files from {DATA_DIR}")
    documents = []
    for txt_file in txt_files:
        try:
            loader = TextLoader(txt_file)
            docs = loader.load()
            logging.info(f"Loaded {len(docs)} documents from {txt_file}")
            for i, doc in enumerate(docs):
                logging.debug(f"Document {i+1} from {txt_file}: {doc.page_content[:200]}...")
            documents.extend(docs)
        except Exception as e:
            logging.warning(f"Error loading text file {txt_file}: {str(e)}")
            continue
    
    if not documents:
        raise ValueError("No documents loaded from text files")

    logging.info("Chunking documents")
    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,  
            chunk_overlap=100,
            length_function=len
        )
        chunks = text_splitter.split_documents(documents)
        logging.info(f"Created {len(chunks)} chunks")
        for i, chunk in enumerate(chunks[:5]):
            logging.debug(f"Chunk {i+1} (source: {chunk.metadata.get('source', 'unknown')}): {chunk.page_content[:200]}...")
    except Exception as e:
        logging.error(f"Error chunking documents: {str(e)}")
        raise Exception(f"Failed to chunk documents: {str(e)}")

    logging.info("Creating Chroma vector store")
    try:
        vector_db = Chroma.from_documents(
            documents=chunks,
            embedding=embedding_model,
            collection_name="local-rag",
            persist_directory=CHROMA_DIR,
            client=chroma_client
        )
        vector_db.persist()
        logging.info(f"Chroma vector store created and persisted to {CHROMA_DIR}")
    except Exception as e:
        logging.error(f"Error creating Chroma vector store: {str(e)}")
        raise Exception(f"Failed to create Chroma vector store: {str(e)}")

    return vector_db

if __name__ == "__main__":
    try:
        vector_db = create_vector_store()
        print("Vector store created successfully")
    except Exception as e:
        print(f"Vector store creation failed: {str(e)}")
        logging.error(f"Vector store creation failed: {str(e)}")