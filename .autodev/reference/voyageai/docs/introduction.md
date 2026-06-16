> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Introduction

Voyage AI provides cutting-edge embedding models and rerankers.

Embedding models are neural net models (e.g., transformers) that convert unstructured and complex data, such as documents, images, audios, videos, or tabular data, into dense numerical vectors (i.e. embeddings) that capture their semantic meanings. These vectors serve as representations/indices for datapoints and are essential building blocks for semantic search and retrieval-augmented generation (RAG), which is the predominant approach for domain-specific or company-specific chatbots and other AI applications.

Rerankers are neural nets that output relevance scores between a query and multiple documents. It is common practice to use the relevance scores to rerank the documents initially retrieved with embedding-based methods (or with lexical search algorithms such as <a href="https://en.wikipedia.org/wiki/Okapi_BM25" target="_blank">BM25</a> and <a href="https://en.wikipedia.org/wiki/Tf–idf" target="_blank">TF-IDF</a>). Selecting the highest-scored documents refines the retrieval results into a more relevant subset.

Voyage AI provides API endpoints for embedding and reranking models that take in your data (e.g., documents, queries, or query-document pairs) and return their embeddings or relevance scores. Embedding models and rerankers, as modular components, seamlessly integrate with other parts of a RAG stack, including vector stores and generative Large Language Models (LLMs).

Voyage AI’s embedding models and rerankers are **state-of-the-art** in retrieval accuracy. Please read our announcing <a href="https://blog.voyageai.com/2023/10/29/voyage-embeddings/" target="_blank">blog post</a> for details.  Please also check out a high-level <a href="https://www.mongodb.com/resources/basics/artificial-intelligence/retrieval-augmented-generation" target="_blank">introduction</a> of embedding models, semantic search, and RAG, and our step-by-step [quickstart tutorial](https://docs.voyageai.com/docs/quickstart-tutorial)  on implementing a minimalist RAG chatbot using Voyage model endpoints.