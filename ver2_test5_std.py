import logging
import os
import requests
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from chroma_vec import create_vector_store

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

os.environ["CHROMA_TELEMETRY_ENABLED"] = "false"
os.environ["ANONYMIZED_TELEMETRY"] = "false"

def setup_local_chatbot(model_name="llama3.1:8b"):
    BASE_DIR = "/Users/issacleung/ollama_trial"
    logging.info(f"Loading vector store for model: {model_name}")
    try:
        vector_db = create_vector_store()
        if vector_db is None:
            raise ValueError("Vector store creation returned None")
        try:
            sample_docs = vector_db.similarity_search("bullying, ADHD, music therapy, counselling technique, client centered therapy", k=1)
            logging.info(f"Vector store test query returned {len(sample_docs)} documents")
            for i, doc in enumerate(sample_docs):
                logging.debug(f"Test document {i+1}: {doc.page_content[:200]}...")
        except Exception as e:
            logging.warning(f"Vector store test query failed: {str(e)}")
    except Exception as e:
        logging.error(f"Failed to load vector store: {str(e)}")
        raise Exception(f"Failed to load vector store: {str(e)}")

    student_prompt_file = os.path.join(BASE_DIR, "final_prompt.txt")
    parents_prompt_file = os.path.join(BASE_DIR, "parents_prompt.txt")
    
    default_student_prompt = (
        "You are a counselor for students with ADHD, acting as a warm, empathetic listener and supportive friend. "
        "Your role is to focus on understanding and exploring the student’s emotions, especially when they face challenges like bullying or ADHD-related issues."
    )
    default_parents_prompt = (
        "You are a compassionate and knowledgeable parenting assistant designed to provide practical, flexible, and holistic strategies for parents. "
        "Your responses should be tailored to the parent's specific needs, offering guidance on supporting their child with ADHD."
    )
    
    for prompt_file, prompt_type in [(student_prompt_file, "Student"), (parents_prompt_file, "Parent")]:
        if not os.path.exists(prompt_file):
            logging.warning(f"{prompt_type} prompt file not found at {prompt_file}, using default prompt")
            if prompt_type == "Student":
                student_prompt = default_student_prompt
            else:
                parents_prompt = default_parents_prompt
            continue
        if os.path.getsize(prompt_file) == 0:
            logging.warning(f"{prompt_type} prompt file is empty: {prompt_file}, using default prompt")
            if prompt_type == "Student":
                student_prompt = default_student_prompt
            else:
                parents_prompt = default_parents_prompt
            continue

        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                prompt_content = f.read().strip()
                if not prompt_content:
                    logging.warning(f"{prompt_type} prompt file is empty, using default prompt")
                    prompt_content = default_student_prompt if prompt_type == "Student" else default_parents_prompt
                if prompt_type == "Student":
                    student_prompt = prompt_content
                else:
                    parents_prompt = prompt_content
                logging.debug(f"{prompt_type} prompt: {prompt_content[:200]}...")
        except Exception as e:
            logging.warning(f"Error loading {prompt_type} prompt file: {str(e)}, using default prompt")
            if prompt_type == "Student":
                student_prompt = default_student_prompt
            else:
                parents_prompt = default_parents_prompt

    logging.info("Checking Ollama server connectivity")
    try:
        response = requests.get("http://127.0.0.1:11434", timeout=5)
        if response.status_code != 200:
            raise Exception("Ollama server not responding")
    except Exception as e:
        logging.error(f"Ollama server not accessible: {str(e)}")
        raise Exception("Ollama server not running. Please start it with 'ollama serve'.")

    logging.info(f"Initializing Ollama LLM with model: {model_name}")
    try:
        llm = ChatOllama(model=model_name, temperature=0.5, request_timeout=120)  
        llm.invoke("Test connection")
    except Exception as e:
        logging.error(f"Failed to initialize Ollama LLM with {model_name}: {str(e)}")
        raise Exception(f"Failed to initialize Ollama LLM: {str(e)}. Ensure the model '{model_name}' is pulled and the server is running.")

    logging.info("Setting up retriever")
    try:
        primary_retriever = vector_db.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={"k": 5, "score_threshold": 0.1}  
        )
        fallback_retriever = vector_db.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 5}
        )
    except Exception as e:
        logging.error(f"Error setting up retriever: {str(e)}")
        raise Exception(f"Failed to set up retriever: {str(e)}")

    try:
        student_rag_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(student_prompt),
            HumanMessagePromptTemplate.from_template("Context: {context}\n\nQuery: {query}")
        ])
        parents_rag_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(parents_prompt),
            HumanMessagePromptTemplate.from_template("Context: {context}\n\nQuery: {query}")
        ])
    except Exception as e:
        logging.error(f"Error creating prompt templates: {str(e)}")
        raise Exception(f"Failed to create prompt templates: {str(e)}")

    logging.info("Creating query chains")
    try:
        def format_docs(docs):
            if not docs:
                logging.debug("No documents retrieved, returning empty context")
                return ""
            formatted = "\n\n".join([f"Source: {doc.metadata.get('source', 'unknown')}\nContent: {doc.page_content}\nScore: {doc.metadata.get('score', 'N/A')}" for doc in docs])
            logging.debug(f"Retrieved documents:\n{formatted[:1000]}...")
            return formatted

        student_chain = (
            {
                "context": primary_retriever | format_docs,
                "query": RunnablePassthrough()
            }
            | student_rag_prompt
            | llm
            | StrOutputParser()
        )
        parents_chain = (
            {
                "context": primary_retriever | format_docs,
                "query": RunnablePassthrough()
            }
            | parents_rag_prompt
            | llm
            | StrOutputParser()
        )
    except Exception as e:
        logging.error(f"Error creating query chains: {str(e)}")
        raise Exception(f"Failed to create query chains: {str(e)}")

    def query_local_mistral(query_engine, query):
        try:
            augmented_query = f"{query.strip().lower()} bullying ADHD"
            logging.info(f"Processing augmented query: {augmented_query}")
            try:
                result = query_engine.invoke(augmented_query)
                logging.debug(f"Primary chain result: {result[:200]}...")
                response = result if isinstance(result, str) else result.get('response', str(result))
            except Exception as e:
                logging.warning(f"Primary chain failed: {str(e)}. Trying fallback retriever.")
                try:
                    context = format_docs(fallback_retriever.invoke(augmented_query))
                    logging.debug(f"Fallback retriever context: {context[:1000]}...")
                    prompt_input = {"context": context, "query": augmented_query}
                    response = (
                        student_rag_prompt | llm | StrOutputParser()
                    ).invoke(prompt_input) if query_engine == student_chain else (
                        parents_rag_prompt | llm | StrOutputParser()
                    ).invoke(prompt_input)
                except Exception as e:
                    logging.warning(f"Fallback retriever failed: {str(e)}. Using direct LLM fallback.")
                    fallback_prompt = ChatPromptTemplate.from_messages([
                        SystemMessagePromptTemplate.from_template(
                            default_student_prompt if query_engine == student_chain else default_parents_prompt
                        ),
                        HumanMessagePromptTemplate.from_template("{query}")
                    ])
                    fallback_chain = fallback_prompt | llm | StrOutputParser()
                    response = fallback_chain.invoke(augmented_query)
            logging.info(f"Response for query '{augmented_query}': {response[:200]}...")
            return response.strip()
        except Exception as e:
            logging.error(f"Error querying Ollama: {str(e)}")
            return f"Error querying Ollama: {str(e)}"

    logging.info("Chatbot setup complete")
    return student_chain, parents_chain, query_local_mistral, student_prompt, parents_prompt

if __name__ == "__main__":
    try:
        student_query_engine, parents_query_engine, query_local_mistral, student_prompt, parents_prompt = setup_local_chatbot()
        print("Chatbot setup successful")
        while True:
            mode = input("Please choose a mode: 'student' or 'parents' (type 'stop' to exit): ").lower()
            if mode == "stop":
                print("Exiting program...")
                break
            elif mode == "student":
                while True:
                    user_input = input("Student Mode - How can I help you? (Type 'stop' to exit or 'parents' to switch modes): ")
                    if user_input.lower() == "stop":
                        print("Exiting program...")
                        break
                    elif user_input.lower() == "parents":
                        break
                    else:
                        response = query_local_mistral(student_query_engine, user_input)
                        print("\nMistral Response:\n", response)
            elif mode == "parents":
                password_input = input("Enter password for Parents Mode: ")
                parents_password = "parent123"
                if password_input == parents_password:
                    print("Switched to Parents Mode.")
                    while True:
                        user_input = input("Parents Mode - How can I help you? (Type 'stop' to exit or 'student' to switch modes): ")
                        if user_input.lower() == "stop":
                            print("Exiting program...")
                            break
                        elif user_input.lower() == "student":
                            break
                        else:
                            response = query_local_mistral(parents_query_engine, user_input)
                            print("\nMistral Response:\n", response)
                else:
                    print("Incorrect password. Please choose a mode again.")
                    continue
    except Exception as e:
        print(f"Setup failed: {str(e)}")
        logging.error(f"Setup failed: {str(e)}")
