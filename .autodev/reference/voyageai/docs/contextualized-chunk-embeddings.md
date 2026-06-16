> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Contextualized Chunk Embeddings

# Model Choices

Voyage currently provides the following contextualized chunk embedding models:

<Table align={[null,"left",null,null,"left"]}>
  <thead>
    <tr>
      <th>
        Model
      </th>

      <th>
        Per Chunk Context Window
      </th>

      <th>
        Context Length (tokens)
      </th>

      <th>
        Embedding Dimension
      </th>

      <th>
        Description
      </th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <td>
        **In Preview:**`voyage-context-4`
      </td>

      <td>
        32,000
      </td>

      <td>
        120,000\*
      </td>

      <td>
        1024 (default), 256, 512, 2048
      </td>

      <td>
        Contextualized chunk embeddings optimized for general-purpose and multilingual retrieval quality.
      </td>
    </tr>

    <tr>
      <td>
        `voyage-context-3`
      </td>

      <td>
        32,000
      </td>

      <td>
        120,000\*
      </td>

      <td>
        1024 (default), 256, 512, 2048
      </td>

      <td>
        Contextualized chunk embeddings optimized for general-purpose and multilingual retrieval quality.

        To learn more, see the [blog post](https://www.mongodb.com/company/blog/product-release-announcements/voyage-context-3-focused-chunk-level-details-global-document-context).
      </td>
    </tr>
  </tbody>
</Table>

***

# Python API

Voyage contextualized chunk embeddings are accessible in Python through the [voyageai package](https://docs.voyageai.com/docs/api-key-and-installation#install-voyage-python-package). Install the package, [set up your API key](https://docs.voyageai.com/docs/api-key-and-installation), and use `voyageai.Client.contextualized_embed()` to vectorize your inputs.

> `voyageai.Client.contextualized_embed( inputs: Union[List[List[str]], List[str]], # see below for specifics on when to pass one or the other. model: str, input_type: Optional[str] = None, output_dimension: Optional[int] = None, output_dtype: Optional[str] = "float", enable_auto_chunking: Optional[bool] = False, chunk_size: Optional[int] = 512, chunk_overlap: Optional[int] = 0, chunk_fn: Optional[Callable[[str], List[str]]] = None, )`

**Parameters**

* **inputs** (`List[List[str]]` or `List[str]`) - The input texts to be vectorized.
* **model** (`str`) - Name of the model. Recommended options: `voyage-context-4`.
* **input\_type** (`str,` **optional**, defaults to `None`) - Type of the input text.
  * Options: `None`, `query`, `document`.
  * When `input_type` is `None`, the model directly converts the inputs into numerical vectors. For retrieval and search, we recommend setting `input_type` to `query` or `document`. In those cases, Voyage automatically prepends a prompt before vectorizing the input. Embeddings generated with and without `input_type` are compatible.
* **output\_dimension** (`int`, **optional**, defaults to `None`) - The number of dimensions for resulting embeddings.
  * Options: `2048`, `1024` (default), `512`, and `256`.
* **output\_dtype** The data type for returned embeddings.
  * Options: `float`, `int8`, `uint8`, `binary`, `ubinary`. See [Flexible Dimensions and Quantization](https://docs.voyageai.com/docs/flexible-dimensions-and-quantization#quantization) for details.
    * `float`: Each embedding is a list of 32-bit [floating-point numbers](https://en.wikipedia.org/wiki/Single-precision_floating-point_format).
    * `int8` and `uint8`: Each embedding is a list of 8-bit integers.
    * `binary` and `ubinary`: Each embedding is a list of 8-bit integers representing bit-packed single-bit values. The returned list length is `1/8` of `output_dimension.binary`uses offset binary.
* **enable\_auto\_chunking** (`bool`, **optional**, defaults to `False`) - Whether to automatically chunk each input document on the backend. When `True`, inputs must be a flat `List[str]` of full-document strings, and `input_type` must be `document`.
* **chunk\_size** (`int`, **optional**) - Target chunk size in tokens when `enable_auto_chunking=True`. If omitted, the server resolves it to `512`. `chunk_size` must not exceed 32K tokens.
* **chunk\_overlap** (`int`, **optional**, defaults to `0`) - Chunk overlap for improved context across chunks in tokens when `enable_auto_chunking=True`. `chunk_overlap` must be smaller than `chunk_size`. Only a valid input when `enable_auto_chunking=True`.

<Callout icon="🚧" theme="warn">
  - The listed limits for both `chunk_size` and `chunk_overlap` are upper bounds. The actual `chunk_size` and `chunk_overlap` can be less than the value passed, but cannot be higher.
  - Overlapping tokens are billed in the same way as input tokens.
</Callout>

* **chunk\_fn** (`Callable[[str]`, `List[str]]`, **optional**, defaults to `None`) - A custom client-side chunking function. If provided, it is applied locally to each input string before the request is sent. For convenience, `voyageai.default_chunk_fn` is available. Use `chunk_fn` for client-side chunking only; it cannot be combined with `enable_auto_chunking=True`.

**Returns**

* A `ContextualizedEmbeddingsObject`, containing the following attributes:
  * **results** (List\[`ContextualizedEmbeddingsResult`]) - One result per query or document.
    * **embeddings** (`List[List[float]]` or `List[List[int]]`) - Embeddings corresponding to a `query`, a `document`, or chunks from the same document. For document chunks, embeddings are ordered to match chunk order.
    * **chunk\_texts** (`List[str]`) - Chunk text returned by the Python SDK for chunked document results. If you provide a client-side `chunk_fn`, these correspond to the chunks produced by that function. When `enable_auto_chunking=True` they correspond to the backend-generated chunks.
    * **index** (`int`) - The index of the query or document in the input list.
  * **total\_tokens** (`int`) - The total number of tokens in the input texts.

<br />

**Example**: See our [quickstart](contextualized-chunk-embeddings#quickstart) below.

***

# REST API

Voyage contextualized chunk embeddings can be accessed by calling the endpoint `POST https://api.voyageai.com/v1/contextualizedembeddings`. See the [Contextualized Chunk Embeddings API Reference](https://docs.voyageai.com/reference/contextualized-embeddings-api) for the specification.

**Example**

```shell
curl -X POST https://api.voyageai.com/v1/contextualizedembeddings \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -H "content-type: application/json" \
  -d '
  {
    "inputs": [
      "This is the SEC filing on Leafy Inc.\u0027s Q2 2024 performance.\nThe company\u0027s revenue increased by 15% compared to the previous quarter.",
      "This is the SEC filing on Elephant Ltd.\u0027s Q2 2024 performance.\nThe company\u0027s revenue decreased by 2% compared to the previous quarter."
    ],
    "input_type": "document",
    "model": "voyage-context-4",
    "enable_auto_chunking": true,
    "chunk_size": 512,
    "chunk_overlap": 0
  }'

```

***

## Response Shape

```json
{
  "data": [
    {
      "data": [
        { "embedding": [...], "index": 0, "text": "chunk text here" },
        { "embedding": [...], "index": 1, "text": "..." }
      ],
      "index": 0
    }
  ],
  "model": "voyage-context-4",
  "usage": { "total_tokens": 100 },
  "chunker_version": "1.0.0"
}

```

<br />

## Inputs Validation

<br />

| Use Case                           | `inputs` shape                   | `input_type` | `enable_auto_chunking` | `chunk_fn` | Notes                                                    |
| ---------------------------------- | :------------------------------- | ------------ | ---------------------- | :--------- | -------------------------------------------------------- |
| Embed pre-chunked documents        | `List[List[str]]`                | `document`   | `False` or omitted     | Omitted    | Each inner list contains one document's chunks           |
| Client-side chunking and embedding | `List[List[str]]`                | `document`   | `False` or omitted     | Provided   | Common pattern: one full document string per inner list  |
| Auto chunking and embedding        | `List[str]`                      | `document`   | `True`                 | Omitted    | `chunk_size` and `chunk_over`                            |
| Embed queries                      | `List[str]` or `List[List[str]]` | `query`      | `False` or omitted     | Omitted    | If nested, each inner list should contain a single query |

# TypeScript Library

Voyage text embeddings are accessible in TypeScript through the [Voyage TypeScript Library](https://www.npmjs.com/package/voyageai), which exposes all the functionality of our text embeddings endpoint (see [Contextualized Chunk Embeddings API Reference](https://docs.voyageai.com/reference/contextualized-embeddings-api)).

***

# Quickstart

This quickstart demonstrates getting started with each of the supported use cases for `voyage-context-4`. Each section includes a working example snippet and a list of valid parameters for the associated use case.

## Auto Chunking and Embedding

Use this when you want Voyage to split each full document into chunks for you.

```python
import voyageai

vo = voyageai.Client()

documents = [
    "This is the SEC filing on Leafy Inc.'s Q2 2024 performance.\nThe company's revenue increased by 15% compared to the previous quarter.",
    "This is the SEC filing on Elephant Ltd.'s Q2 2024 performance.\nThe company's revenue decreased by 2% compared to the previous quarter.",
]

result = vo.contextualized_embed(
    model="voyage-context-4",
    inputs=documents,
    input_type="document",
    enable_auto_chunking=True,
    chunk_size=512,
    chunk_overlap=0,
)

```

## Embed Pre-Chunked Documents

Use this when you have already split each document into chunks on the client side.

```python
import voyageai

vo = voyageai.Client()

inputs = [
    [
        "This is the SEC filing on Leafy Inc.'s Q2 2024 performance.",
        "The company's revenue increased by 15% compared to the previous quarter.",
    ],
    [
        "This is the SEC filing on Elephant Ltd.'s Q2 2024 performance.",
        "The company's revenue decreased by 2% compared to the previous quarter.",
    ],
]

result = vo.contextualized_embed(
    model="voyage-context-4",
    inputs=inputs,
    input_type="document",
)

```

Each inner list is embedded as a group, so each chunk is encoded in the context of the other chunks from the same document.

## Client-Side Chunking and Embedding

Use this when you have full documents and want to handle chunking locally in the Python SDK rather than in the backend.

```python
import voyageai

vo = voyageai.Client()

inputs = [
    [
        "This is the SEC filing on Leafy Inc.'s Q2 2024 performance.\nThe company's revenue increased by 15% compared to the previous quarter.",
    ],
    [
        "This is the SEC filing on Elephant Ltd.'s Q2 2024 performance.\nThe company's revenue decreased by 2% compared to the previous quarter.",
    ],
]

result = vo.contextualized_embed(
    model="voyage-context-4",
    inputs=inputs,
    input_type="document",
    chunk_fn=voyageai.default_chunk_fn,
)

```

`chunk_fn` is applied locally to each input string before the request is sent.

## Embedding Queries

Use this when your inputs are search queries.

```python
import voyageai

vo = voyageai.Client()

result = vo.contextualized_embed(
    model="voyage-context-4",
    inputs=[
        "What was the revenue growth for Leafy Inc. in Q2 2024?",
        "What changed in Greenery Corp. between Q1 and Q2 2024?",
    ],
    input_type="query",
)

```

The following query input shape is also valid and is treated equivalently:

```python
result = vo.contextualized_embed(
    model="voyage-context-4",
    inputs=[
        ["What was the revenue growth for Leafy Inc. in Q2 2024?"],
        ["What changed in Greenery Corp. between Q1 and Q2 2024?"],
    ],
    input_type="query",
)

```

## Returned Chunk Text

The response contains contextualized embedding results for each query or document. For document chunks, embeddings are ordered to match chunk order. In the Python SDK, returned chunk text is available through `chunk_texts` on the result object. In the REST API, returned chunk text is available as `text` on each embedding item.

If you provide a client-side chunking function, the returned chunk text corresponds to the chunks produced by that function. When `enable_auto_chunking=True`, the response also includes the backend-generated chunk text for each returned embedding so you can inspect and store it.

## Input Constraints

The following constraints apply to a request:

* The list must not contain more than 1,000 inputs.
* The total number of tokens across all inputs must not exceed 120K.
* The total number of chunks across all inputs must not exceed 16K.
* `chunk_size` and `chunk_overlap` require `enable_auto_chunking=True`.
* `chunk_overlap` must be smaller than `chunk_size`.

## Common Invalid Parameter Combinations

* `List[str]` `document` inputs with `enable_auto_chunking=False` are invalid.
* `enable_auto_chunking=True` requires `input_type="document"`.
* Do not use `chunk_fn` together with `enable_auto_chunking=True`.

# Tutorial

For a full tutorial on using contextualized chunk embeddings, see [Contextualized Chunk Embeddings: Combining Local Detail with Global Context](https://www.mongodb.com/company/blog/technical/contextualized-chunk-embeddings-combining-local-detail-with-global-context). The Jupyter Notebook for this tutorial is available on GitHub in the [GenAI Showcase repository](https://github.com/mongodb-developer/GenAI-Showcase/blob/main/notebooks/advanced_techniques/contextual_chunk_embedding.ipynb).