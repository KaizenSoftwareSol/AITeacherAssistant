# ai/rag.py

from typing import List, Optional

import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from settings import settings


class RAGSystem:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
        self.chroma_client = chromadb.PersistentClient(
            path="./chroma_store",
            settings=Settings(anonymized_telemetry=False)
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        self.vectorstore = None
        self._initialize_vectorstore()
    
    def _initialize_vectorstore(self):
        """Initialize the vector store."""
        try:
            self.vectorstore = Chroma(
                client=self.chroma_client,
                collection_name="ai_teacher_knowledge",
                embedding_function=self.embeddings
            )
        except Exception as e:
            print(f"Error initializing vectorstore: {e}")
            self.vectorstore = None
    
    def add_documents(self, documents: List[str], metadatas: Optional[List[dict]] = None):
        """Add documents to the knowledge base."""
        if not self.vectorstore:
            return False
        
        try:
            # Split documents into chunks
            texts = self.text_splitter.split_text("\n".join(documents))
            
            # Prepare metadatas
            if metadatas is None:
                metadatas = [{"source": f"doc_{i}"} for i in range(len(texts))]
            
            # Add to vectorstore
            self.vectorstore.add_texts(texts=texts, metadatas=metadatas)
            return True
        except Exception as e:
            print(f"Error adding documents: {e}")
            return False
    
    def search(self, query: str, k: int = 5) -> List[dict]:
        """Search for relevant documents."""
        if not self.vectorstore:
            return []
        
        try:
            results = self.vectorstore.similarity_search_with_score(query, k=k)
            return [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": score
                }
                for doc, score in results
            ]
        except Exception as e:
            print(f"Error searching: {e}")
            return []
    
    def get_relevant_context(self, query: str, k: int = 3) -> str:
        """Get relevant context for a query."""
        results = self.search(query, k)
        if not results:
            return ""
        
        context = "\n\n".join([result["content"] for result in results])
        return context


