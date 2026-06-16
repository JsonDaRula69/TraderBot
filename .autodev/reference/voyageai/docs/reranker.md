> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Rerankers

A reranker, given a query and many documents, returns the (ranks of) relevancy between the query and documents. The documents oftentimes are the preliminary results from an embedding-based retrieval system, and the reranker refines the ranks of these candidate documents and provides more accurate relevancy scores.

Unlike [embedding](https://docs.voyageai.com/docs/embeddings) models that encode queries and documents separately, rerankers are [cross-encoders](https://www.sbert.net/examples/applications/cross-encoder/README.html) that jointly process a pair of query and document, enabling more accurate relevancy prediction. Thus, it is a common practice to apply a reranker on the top candidates retrieved with embedding-based search (or with lexical search algorithms such as [BM25](https://en.wikipedia.org/wiki/Okapi_BM25) and [TF-IDF](https://en.wikipedia.org/wiki/Tf–idf)).

# Model Choices

Voyage currently provides the following reranker models:

<table>
  <thead>
    <tr>
      <th>
        <div>
          Model
        </div>
      </th>

      <th>
        Context Length (tokens)
      </th>

      <th>
        Description
      </th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <td>
        `rerank-2.5`
      </td>

      <td>
        32,000
      </td>

      <td>
        Our generalist reranker optimized for quality with instruction-following and multilingual support. See <a href="https://blog.voyageai.com/2025/08/11/rerank-2-5" target="_blank">blog post</a> for details.
      </td>
    </tr>

    <tr>
      <td>
        `rerank-2.5-lite`
      </td>

      <td>
        32,000
      </td>

      <td>
        Our generalist reranker optimized for both latency and quality with instruction-following and multilingual support. See <a href="https://blog.voyageai.com/2025/08/11/rerank-2-5" target="_blank">blog post</a> for details.
      </td>
    </tr>
  </tbody>
</table>

<details>
  <summary><em>Older models </em></summary>

  The following are our earlier models, which are still accessible from our API. We recommend using the new models above for better quality and efficiency. Our latest models listed in the above table will be strictly better than the legacy models in all aspects, such as quality, context length, latency, and throughput.

  <table>
    <thead>
      <tr>
        <th>
          <div>
            Model
          </div>
        </th>

        <th>
          Context Length (tokens)
        </th>

        <th>
          Description
        </th>
      </tr>
    </thead>

    <tbody>
      <tr>
        <td>
          `rerank-2`
        </td>

        <td>
          16,000
        </td>

        <td>
          Our generalist second-generation reranker optimized for quality with multilingual support. See <a href="https://blog.voyageai.com/2024/09/30/rerank-2/" target="_blank">blog post</a> for details.
        </td>
      </tr>

      <tr>
        <td>
          `rerank-2-lite`
        </td>

        <td>
          8000
        </td>

        <td>
          Our generalist second-generation reranker optimized for both latency and quality with multilingual support. See <a href="https://blog.voyageai.com/2024/09/30/rerank-2/" target="_blank">blog post</a> for details.
        </td>
      </tr>

      <tr>
        <td>
          `rerank-1`
        </td>

        <td>
          8000
        </td>

        <td>
          Our generalist first-generation reranker optimized for quality.  Multilingual support. See [blog post](https://blog.voyageai.com/2024/05/29/voyage-rerank-1-cutting-edge-general-purpose-and-multilingual-reranker/)  for details.
        </td>
      </tr>

      <tr>
        <td>
          `rerank-lite-1`
        </td>

        <td>
          4000
        </td>

        <td>
          Our generalist first-generation reranker optimized for both latency and quality.  See [blog post](https://blog.voyageai.com/2024/03/15/boosting-your-search-and-rag-with-voyages-rerankers/)  for details.
        </td>
      </tr>
    </tbody>
  </table>
</details>

***

#

# Python API

Voyage reranker is accessible in Python through the `voyageai` package. Please first [install the `voyageai` package and setup the API key](https://docs.voyageai.com/docs/api-key-and-installation).

Voyage reranker receives as input a query and a list of candidate documents, e.g., the documents retrieved by a nearest neighbor search with embeddings. It reranks the candidate documents according to their semantic relevances to the search query, and returns the list of relevance scores. To access the reranker, create a [`voyageai.Client`](https://docs.voyageai.com/docs/api-key-and-installation#voyageaiclient) object and use its `rerank()` method.

> [`voyageai.Client.rerank`](https://github.com/voyage-ai/voyageai-python/blob/602ba757eb2e072c95e765f9b83992affbb4ea41/voyageai/client.py#L56) ` (query: str, documents: List[str], model: str, top_k: Optional[int] = None, truncation: bool = True)`

**Parameters**

* **query** (str) - The query as a string. The query can contain a maximum of 8,000 tokens for `rerank-2.5` and `rerank-2.5-lite`, 4,000 tokens for `rerank-2`, 2,000 tokens for `rerank-2-lite` and `rerank-1`, and 1,000 tokens for `rerank-lite-1`. For `rerank-2.5` and `rerank-2.5-lite`, optional instructions can be appended or prepended to the query to better guide the relevance.
* **documents** (List\[str]) - The documents to be reranked as a list of strings.
  * The number of documents cannot exceed 1,000.
  * The sum of the number of tokens in the query and the number of tokens in any single document cannot exceed 32,000 for `rerank-2.5` and `rerank-2.5-lite`, 16,000 for `rerank-2`; 8,000 for `rerank-2-lite` and `rerank-1`; and 4,000 for `rerank-lite-1`.
  * The total number of tokens, defined as "the number of query tokens × the number of documents + sum of the number of tokens in all documents", cannot exceed 600K for `rerank-2.5`, `rerank-2.5-lite`, `rerank-2` and `rerank-2-lite`; and 300K for `rerank-1` and `rerank-lite-1`. Please see our [FAQ](https://docs.voyageai.com/docs/faq#what-is-the-total-number-of-tokens-for-the-rerankers).
* **model** (str) - Name of the model. Recommended options: `rerank-2.5`, `rerank-2.5-lite`.
* **top\_k** (int, optional, defaults to `None`) - The number of most relevant documents to return. If not specified, the reranking results of all documents will be returned.
* **truncation** (bool, optional, defaults to `True`) - Whether to truncate the input to satisfy the "context length limit" on the query and the documents.
  * If `True`, the query and documents will be truncated to fit within the context length limit, before processed by the reranker model.
  * If `False`, an error will be raised when the query exceeds 8,000 tokens for `rerank-2.5` and `rerank-2.5-lite`; 4,000 tokens for `rerank-2`; 2,000 tokens `rerank-2-lite` and `rerank-1`; and 1,000 tokens for `rerank-lite-1`, or the sum of the number of tokens in the query and the number of tokens in any single document exceeds 16,000 for `rerank-2`; 8,000 for `rerank-2-lite` and `rerank-1`; and 4,000 for `rerank-lite-1`.

**Returns**

* A `RerankingObject`, containing the following attributes:
  * **results** (ListrankingResult`]) - ) - A list of `RerankingResult`, with format specified below, sorted by the descending order of relevance scores. The length of the list equals to top\_k if this argument is specified, otherwise the number of the input documents. Each element in the list is a `RerankingResult\` object, which contains attributes:
    * **index** (int) - The index of the document in the input list.
    * **document** (str) - The document as a string.
    * **relevance\_score** (float) - The relevance score of the document with respect to the query.
  * **total\_tokens** (int) - The total number of tokens in the input, which is defined as "the number of query tokens × the number of documents + sum of the number of tokens in all documents".

**Example**

```python
import voyageai

vo = voyageai.Client()
# This will automatically use the environment variable VOYAGE_API_KEY.
# Alternatively, you can use vo = voyageai.Client(api_key="<your secret key>")

query = "When is Apple's conference call scheduled?"
documents = [
    "The Mediterranean diet emphasizes fish, olive oil, and vegetables, believed to reduce chronic diseases.",
    "Photosynthesis in plants converts light energy into glucose and produces essential oxygen.",
    "20th-century innovations, from radios to smartphones, centered on electronic advancements.",
    "Rivers provide water, irrigation, and habitat for aquatic species, vital for ecosystems.",
    "Apple’s conference call to discuss fourth fiscal quarter results and business updates is scheduled for Thursday, November 2, 2023 at 2:00 p.m. PT / 5:00 p.m. ET.",
    "Shakespeare's works, like 'Hamlet' and 'A Midsummer Night's Dream,' endure in literature."
]

reranking = vo.rerank(query, documents, model="rerank-2.5", top_k=3)
for r in reranking.results:
    print(f"Document: {r.document}")
    print(f"Relevance Score: {r.relevance_score}")
    print()
```

```Text Output
Document: Apple’s conference call to discuss fourth fiscal quarter results and business updates is scheduled for Thursday, November 2, 2023 at 2:00 p.m. PT / 5:00 p.m. ET.
Relevance Score: 0.94140625
Index: 0


Document: 20th-century innovations, from radios to smartphones, centered on electronic advancements.
Relevance Score: 0.28515625
Index: 1


Document: Photosynthesis in plants converts light energy into glucose and produces essential oxygen.
Relevance Score: 0.255859375
Index: 2
```

***

# REST API

Voyage reranker can be accessed by calling the endpoint `POST https://api.voyageai.com/v1/rerank`. Please refer to the [Reranker API Reference](https://docs.voyageai.com/reference/reranker-api) for the specification.

**Example**

```shell
curl https://api.voyageai.com/v1/rerank \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -d '{
    "query": "Sample query",
    "documents": [
        "Sample document 1",
        "Sample document 2"
    ],
    "model": "rerank-2"
  }'
```

***

# TypeScript Library

Voyage rerankers are accessible in TypeScript through the [Voyage TypeScript Library](https://www.npmjs.com/package/voyageai), which exposes all the functionality of our reranker endpoint (see [Reranker API Reference](https://docs.voyageai.com/reference/reranker-api)).

# Tutorial

For a full tutorial on using Voyage rerankers, see our [detailed guide](https://www.mongodb.com/company/blog/technical/instruction-following-rerankers-an-unsung-context-engineering-tool).

The Jupyter Notebook for this tutorial is available on GitHub in our [GenAI Showcase repository](https://github.com/mongodb-developer/GenAI-Showcase/blob/main/notebooks/advanced_techniques/instruction_following_reranking.ipynb). To follow along, run the notebook in Google Colab or your preferred environment, and refer to the tutorial for explanations of key code blocks.