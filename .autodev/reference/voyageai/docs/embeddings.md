> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Text Embeddings

# Model Choices

Voyage currently provides the following text embedding models:

| Model              | Context Length (tokens) |       Embedding Dimension      | Description                                                                                                                                                                                                                      |
| ------------------ | :---------------------: | :----------------------------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `voyage-4-large`   |          32,000         | 1024 (default), 256, 512, 2048 | The best general-purpose and multilingual retrieval quality. All embeddings created with the 4 series are compatible with each other. See [blog post](https://blog.voyageai.com/2026/01/15/voyage-4/) for details.               |
| `voyage-4`         |          32,000         | 1024 (default), 256, 512, 2048 | Optimized for general-purpose and multilingual retrieval quality. All embeddings created with the 4 series are compatible with each other. See [blog post](https://blog.voyageai.com/2026/01/15/voyage-4/) for details.          |
| `voyage-4-lite`    |          32,000         | 1024 (default), 256, 512, 2048 | Optimized for latency and cost. All embeddings created with the 4 series are compatible with each other. See [blog post](https://blog.voyageai.com/2026/01/15/voyage-4/)  for details.                                           |
| `voyage-code-3`    |          32,000         | 1024 (default), 256, 512, 2048 | Optimized for **code** retrieval. See [blog post](https://blog.voyageai.com/2024/12/04/voyage-code-3/) for details.                                                                                                              |
| `voyage-finance-2` |          32,000         |              1024              | Optimized for **finance** retrieval and RAG. See [blog post](https://blog.voyageai.com/2024/06/03/domain-specific-embeddings-finance-edition-voyage-finance-2/) for details.                                                     |
| `voyage-law-2`     |          16,000         |              1024              | Optimized for **legal** retrieval and RAG. Also improved performance across all domains. See [blog post](https://blog.voyageai.com/2024/04/15/domain-specific-embeddings-and-retrieval-legal-edition-voyage-law-2/) for details. |
| `voyage-code-2`    |          16,000         |              1536              | Optimized for code retrieval (17% better than alternatives) / Previous generation of code embeddings. See [blog post](https://blog.voyageai.com/2024/01/23/voyage-code-2-elevate-your-code-retrieval/) for details.              |

Need help deciding which text embedding model to use? Check out our [FAQ](https://docs.voyageai.com/docs/faq#what-embedding-models-are-available-and-which-one-should-i-use).

<details>
  <summary><em>Older models </em></summary>

  The following are our earlier models, which are still accessible from our API. We recommend using the new models above for better quality and efficiency. Our latest models listed in the above table will be strictly better than the legacy models in all aspects, such as quality, context length, latency, and throughput.

  | Model                     | Context Length (tokens) |       Embedding Dimension      | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
  | ------------------------- | :---------------------: | :----------------------------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | `voyage-3-large`          |          32,000         | 1024 (default), 256, 512, 2048 | Previous generation of text embeddings for general-purpose and multilingual retrieval quality. See [blog post](https://blog.voyageai.com/2025/01/07/voyage-3-large/) for details.                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
  | `voyage-3.5`              |          32,000         | 1024 (default), 256, 512, 2048 | Previous generation of text embeddings optimized for general-purpose and multilingual retrieval quality. See [blog post](https://blog.voyageai.com/2025/05/20/voyage-3-5/) for details.                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
  | `voyage-3.5-lite`         |          32,000         | 1024 (default), 256, 512, 2048 | Previous generation of text embeddings optimized for latency and cost. See [blog post](https://blog.voyageai.com/2025/05/20/voyage-3-5/) for details.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
  | `voyage-3`                |          32,000         |              1024              | Optimized for general-purpose and multilingual retrieval quality. See [blog post](https://blog.voyageai.com/2024/09/18/voyage-3/) for details.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
  | `voyage-3-lite`           |          32,000         |               512              | Optimized for latency and cost. See [blog post](https://blog.voyageai.com/2024/09/18/voyage-3/) for details.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
  | `voyage-multilingual-2`   |          32,000         |              1024              | Optimized for **multilingual** retrieval and RAG. See [blog post](https://blog.voyageai.com/2024/06/10/voyage-multilingual-2-multilingual-embedding-model/) for details.                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
  | `voyage-large-2-instruct` |          16,000         |              1024              | Top of [MTEB leaderboard](https://huggingface.co/spaces/mteb/leaderboard). Instruction-tuned general-purpose embedding model optimized for clustering, classification, and retrieval. For retrieval, please use `input_type` parameter to specify whether the text is a query or document. For classification and clustering, please use the instructions [here](https://github.com/voyage-ai/voyage-large-2-instruct). See [blog post](https://blog.voyageai.com/2024/05/05/voyage-large-2-instruct-instruction-tuned-and-rank-1-on-mteb/) for details. We recommend existing `voyage-large-2-instruct` users to transition to `voyage-3`. |
  | `voyage-large-2`          |          16,000         |              1536              | General-purpose embedding model that is optimized for retrieval quality (e.g., better than OpenAI V3 Large). Please transition to `voyage-3`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
  | `voyage-2`                |           4000          |              1024              | General-purpose embedding model optimized for a balance between cost, latency, and retrieval quality. Please transition to `voyage-3-lite`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
  | `voyage-lite-02-instruct` |           4000          |              1024              | \[*Deprecated*] [Instruction-tuned](https://github.com/voyage-ai/voyage-lite-02-instruct/blob/main/instruct.json) for classification, clustering, and sentence textual similarity tasks, which are the only recommended use cases. Please transition to `voyage-3`.                                                                                                                                                                                                                                                                                                                                                                         |
  | `voyage-02`               |           4000          |              1024              | \[*Deprecated*] This is our pilot-version v2 embedding model. We kindly ask you to transition to `voyage-3` as detailed above.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
  | `voyage-01`               |           4000          |              1024              | \[*Deprecated*] This is our v1 embedding model. Please transition to `voyage-3`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
  | `voyage-lite-01`          |           4000          |              1024              | \[*Deprecated*] This is our v1 embedding model. Please transition to `voyage-3`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
  | `voyage-lite-01-instruct` |           4000          |              1024              | \[*Deprecated*] Tweaked on top of `voyage-lite-01` for classification and clustering tasks. Please transition to `voyage-3`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
</details>

***

## Open Models

Voyage also provides the following open-weight embedding models:

| Model           | Context Length (tokens) |       Embedding Dimension      | Description                                                                                                                                                                                                                                         |
| :-------------- | :---------------------: | :----------------------------: | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `voyage-4-nano` |          32,000         | 1024 (default), 256, 512, 2048 | Open-weight model available on [Hugging Face](https://huggingface.co/voyageai/voyage-4-nano). All embeddings created with the 4 series are compatible with eachother. See [blog post](https://blog.voyageai.com/2026/01/15/voyage-4/)  for details. |

# Python API

Voyage text embeddings are accessible in Python through the `voyageai` [package](https://docs.voyageai.com/docs/api-key-and-installation#install-voyage-python-package). Please install the `voyageai` package, [set up](https://docs.voyageai.com/docs/api-key-and-installation)  the API key, and use the `voyageai.Client.embed()` function to vectorize your inputs.

> [`voyageai.Client.embed`](https://github.com/voyage-ai/voyageai-python/blob/870e95486d4f373a9dab9061f5e2397ff230db06/voyageai/client.py#L31) `(texts : List[str], model : str, input_type : Optional[str] = None, truncation : Optional[bool] = None, output_dimension: Optional[int] = None, output_dtype: Optional[str] = "float")`

**Parameters**

* **texts** (str or List\[str]) - A single text string, or a list of texts as a list of strings, such as `["I like cats", "I also like dogs"]`. Currently, we have two constraints on the list:
  * The maximum length of the list is 1,000.
  * The total number of tokens in the list is at most 1M for `voyage-4-lite`, `voyage-3.5-lite`; 320K for `voyage-4`, `voyage-3.5`, and `voyage-2`; and 120K for `voyage-4-large`, `voyage-3-large`, `voyage-code-3`, `voyage-large-2-instruct`, `voyage-finance-2`, `voyage-multilingual-2`, and `voyage-law-2`.
* **model** (str) - Name of the model. Recommended options: `voyage-4-large`, `voyage-4`, `voyage-4-lite`, `voyage-3-large`, `voyage-3.5`, `voyage-3.5-lite`, `voyage-code-3`, `voyage-finance-2`, `voyage-law-2`.
* **input\_type** (str, optional, defaults to `None`) - Type of the input text. Options: `None`, `query`, `document`.
  * When `input_type` is `None` , the embedding model directly converts the inputs (`texts`) into numerical vectors. For retrieval/search purposes, where a "query" is used to search for relevant information among a collection of data, referred to as "documents", we recommend specifying whether your inputs (`texts`) are intended as queries or documents by setting `input_type` to `query` or `document` , respectively. In these cases, Voyage automatically prepends a prompt to your inputs (`texts`) before vectorizing them, creating vectors more tailored for retrieval/search tasks. Embeddings generated with and without the `input_type` argument are compatible.
  * For transparency, the following prompts are prepended to your input.
    * For query, the prompt is "*Represent the query for retrieving supporting documents:* ".
    * For document, the prompt is "*Represent the document for retrieval:* ".
* **truncation** (bool, optional, defaults to `True`) - Whether to truncate the input texts to fit within the context length.
  * If `True`, an over-length input texts will be truncated to fit within the context length, before vectorized by the embedding model.
  * If `False`, an error will be raised if any given text exceeds the context length.
* **output\_dimension** (int, optional, defaults to `None`) - The number of dimensions for resulting output embeddings.
  * Most models only support a single default dimension, used when `output_dimension` is set to `None` (see model embedding dimensions [above](https://docs.voyageai.com/docs/embeddings#model-choices)).
  * `voyage-4-large`, `voyage-4`, `voyage-4-lite`, `voyage-3-large`, `voyage-3.5`, `voyage-3.5-lite`, and `voyage-code-3` support the following `output_dimension` values: 2048, 1024 (default), 512, and 256.
* **output\_dtype** (str, optional, defaults to `float`) - The data type for the embeddings to be returned. Options: `float`, `int8`, `uint8`, `binary`, `ubinary`. `float` is supported for all models. `int8`, `uint8`, `binary`, and `ubinary` are supported by `voyage-4-large`, `voyage-4`, `voyage-4-lite`, `voyage-3-large`, `voyage-3.5`, `voyage-3.5-lite`, and `voyage-code-3`. Please see our [guide](https://docs.voyageai.com/docs/flexible-dimensions-and-quantization#quantization) for more details about output data types.
  * `float`: Each returned embedding is a list of 32-bit (4-byte) <a href="https://en.wikipedia.org/wiki/Single-precision_floating-point_format" target="_blank">single-precision floating-point</a> numbers.  This is the default and provides the highest precision / retrieval accuracy.
  * `int8` and `uint8`: Each returned embedding is a list of 8-bit (1-byte) integers ranging from -128 to 127 and 0 to 255, respectively.
  * `binary` and `ubinary`: Each returned embedding is a list of 8-bit integers that represent bit-packed, quantized single-bit embedding values: `int8` for `binary` and `uint8` for `ubinary`. The length of the returned list of integers is 1/8 of `output_dimension` (which is the actual dimension of the embedding). The `binary` type uses the offset binary method. Please refer to our guide for details on [offset binary](https://docs.voyageai.com/docs/flexible-dimensions-and-quantization#offset-binary) and [binary embeddings](https://docs.voyageai.com/docs/flexible-dimensions-and-quantization#quantization).

**Returns**

* A `EmbeddingsObject`, containing the following attributes:
  * **embeddings** (List\[List\[float]] or List\[List\[int]]) - A list of embeddings for the corresponding list of input texts.  Each embedding is a vector represented as a list of <a href="https://docs.python.org/3/library/functions.html#float" target="_blank">floats</a> when `output_dtype` is set to `float` and as a list of <a href="https://docs.python.org/3/library/functions.html#int" target="_blank">integers</a> for all other values of `output_dtype` (`int8`, `uint8`, `binary`, `ubinary`).
  * **total\_tokens** (int) - The total number of tokens in the input texts.

**Example**

```python
import voyageai

vo = voyageai.Client()
# This will automatically use the environment variable VOYAGE_API_KEY.
# Alternatively, you can use vo = voyageai.Client(api_key="<your secret key>")

texts = [
    "The Mediterranean diet emphasizes fish, olive oil, and vegetables, believed to reduce chronic diseases.",
    "Photosynthesis in plants converts light energy into glucose and produces essential oxygen.",
    "20th-century innovations, from radios to smartphones, centered on electronic advancements.",
    "Rivers provide water, irrigation, and habitat for aquatic species, vital for ecosystems.",
    "Apple’s conference call to discuss fourth fiscal quarter results and business updates is scheduled for Thursday, November 2, 2023 at 2:00 p.m. PT / 5:00 p.m. ET.",
    "Shakespeare's works, like 'Hamlet' and 'A Midsummer Night's Dream,' endure in literature."
]

# Embed the documents
result = vo.embed(texts, model="voyage-4-large", input_type="document")
print(result.embeddings)
```

```Text Output
[
    [-0.01225314, 0.00206815, 0.030598236, ...],
    [0.008976975,-0.002981404,0.015463986, ...],
    [-0.062971942,-0.047771815,-0.101127356, ...],
    [0.047902156,-0.004106794,-0.007774695, ...],
    [-0.008545358,-0.063952357,-0.007111943, ...],
    [-0.00172591,-0.004946421,-0.04327229, ...]
]
```

***

## Deprecated Functions

The following functions are deprecated and will be removed in the future.

> `get_embedding(text, model="voyage-01", input_type=None)` [](https://github.com/voyage-ai/voyageai-python/blob/870e95486d4f373a9dab9061f5e2397ff230db06/voyageai/embeddings_utils.py#L72)

**Parameters**

* **text** - A single document/query as a string, such as `"I like cats"` .
* **model** - Name of the model. Options: `voyage-01` (default), `voyage-lite-01`.
* **input\_type** - Type of the input text. Defalut to `None`, meaning the type is unspecified. Other options:  `query`, `document`.

**Returns**

* An embedding vector (a list of floating-point numbers) for the document.

> `get_embeddings(list_of_text, model="voyage-01", input_type=None)` [](https://github.com/voyage-ai/voyageai-python/blob/870e95486d4f373a9dab9061f5e2397ff230db06/voyageai/embeddings_utils.py#L89)

**Parameters**

* **list\_of\_text** - A list of documents as a list of strings, such as  `["I like cats", "I also like dogs"]`. The maximum length of the list is 64.
* **model** - Name of the model. Options: `voyage-01` (default), `voyage-lite-01`.
* **input\_type** - Type of the input text. Defalut to `None`, meaning the type is unspecified. Other options: `query`, `document`.

**Returns**

* A list of embedding vectors.

***

# REST API

Voyage text embeddings can be accessed by calling the endpoint `POST https://api.voyageai.com/v1/embeddings`. Please refer to the [Text Embeddings API Reference](https://docs.voyageai.com/reference/embeddings-api) for the specification.

**Example**

```shell Embed a single string
curl https://api.voyageai.com/v1/embeddings \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -d '{
    "input": "Sample text",
    "model": "voyage-4-large",
    "input_type": "document"
  }'
```

```shell Embed a list of strings
curl https://api.voyageai.com/v1/embeddings \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -d '{
    "input": ["Sample text 1", "Sample text 2"],
    "model": "voyage-4-large",
    "input_type": "document"
  }'
```

***

# TypeScript Library

Voyage text embeddings are accessible in TypeScript through the [Voyage TypeScript Library](https://www.npmjs.com/package/voyageai), which exposes all the functionality of our text embeddings endpoint (see [Text Embeddings API Reference](https://docs.voyageai.com/reference/embeddings-api)).