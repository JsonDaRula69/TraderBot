> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Multimodal Embeddings

Multimodal embedding models transform unstructured data from multiple modalities into a shared vector space. Voyage multimodal embedding models support text and content-rich images — such as figures, photos, slide decks, and document screenshots — eliminating the need for complex text extraction or ETL pipelines. Unlike traditional multimodal models like CLIP, which process text and images separately, Voyage multimodal embedding models can directly vectorize inputs containing interleaved text + images. The architecture of CLIP also prevents it from being usable in mixed-modality searches, as text and image vectors often align with irrelevant items of the same modality. Voyage multimodal embedding models eliminate this bias by processing all inputs through a single backbone.

# Model Choices

Voyage currently provides the following multimodal embedding models:

| Model                   | Context Length (tokens) |       Embedding Dimension      | Description                                                                                                                                                                                                                                             |
| ----------------------- | :---------------------: | :----------------------------: | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `voyage-multimodal-3.5` |          32,000         | 1024 (default), 256, 512, 2048 | Rich multimodal embedding model that can vectorize interleaved text and visual data, such as screenshots of PDFs, slides, tables, figures, videos, and more. See [blog post](https://blog.voyageai.com/2026/01/15/voyage-multimodal-3-5/)  for details. |

<details>
  <summary><em>Older models </em></summary>

  The following are our earlier models, which are still accessible from our API. We recommend using the new models above for better quality and efficiency. Our latest models listed in the above table will be strictly better than the legacy models in all aspects, such as quality, context length, latency, and throughput.

  | Model                 | Context Length (tokens) | Embedding Dimension | Description                                                                                                                                                                                                                                                                                  |
  | --------------------- | :---------------------: | :-----------------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | `voyage-multimodal-3` |          32,000         |         1024        | Previous generation of multimodal embeddings that can vectorize interleaved text and content-rich images, such as screenshots of PDFs, slides, tables, figures, and more. See <a href="https://blog.voyageai.com/2024/11/12/voyage-multimodal-3/" target="_blank">blog post</a> for details. |
</details>

***

# Python API

Voyage multimodal embeddings are accessible in Python through the `voyageai` [package](https://docs.voyageai.com/docs/api-key-and-installation#install-voyage-python-package). Please install the `voyageai` package, [set up](https://docs.voyageai.com/docs/api-key-and-installation)  the API key, and use the `voyageai.Client.multimodal_embed()` function to vectorize your inputs.

> <a href="https://github.com/voyage-ai/voyageai-python/blob/main/voyageai/client.py#L103" target="_blank">`voyageai.Client.multimodal_embed`</a> `(inputs : List[Dict] or List[List[Union[str, PIL.Image.Image, voyageai.video_utils.Video]]], model : str, input_type : Optional[str] = None, truncation : Optional[bool] = True)`

<Callout icon="🚧" theme="warn">
  Starting **December 8, 2025**, the following constraints apply to all URL parameters (e.g., image\_url):

  * Limit the number of redirects.
  * Require that responses include a content-length header
  * Respect robots.txt to prevent unauthorized scraping.
</Callout>

**Parameters**

* **inputs** (`List[Dict]` or `List[List[Union[str, PIL.Image.Image, voyageai.video_utils.Video]]]`) - A list of multimodal inputs to be vectorized.

  * Each input is a sequence of text, images, and videos which can be represented in either of the following two ways:

    **(1)** A list containing text strings, Image objects, or Video objects (`List[Union[str, PIL.Image.Image, voyageai.video_utils.Video]]`), where each image is an instance of the <a href="https://pillow.readthedocs.io/en/stable/reference/Image.html#the-image-class" target="_blank">Pillow Image class</a>. *Videos inputs are only supported by `voyage-multimodal-3.5`.*

    <details id="base64">
      <summary><em>PIL Image Object</em></summary>
      <a href="https://python-pillow.org/" target="_blank">Pillow</a> is a widely used Python library for image processing. In the above example, <a href="https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.open" target="_blank">`PIL.Image.open()`</a> opens an image file and returns a PIL Image. Please see our [FAQ](https://docs.voyageai.com/docs/faq#what-is-the-python-pillow-library) for more details about Pillow.
    </details>

    **(2)** A dictionary that contains a single key `"content"`, whose value represents a sequence of text, images, and videos. The dictionary schema is identical to that of an input in the `inputs` parameter of the [REST API](https://docs.voyageai.com/reference/multimodal-embeddings-api).
  * The following constraints apply to the `inputs` list:
    * The list must not contain more than 1,000 inputs.
    * Each image must not contain more than 16 million pixels or be larger than 20 MB in size.
    * Each video must not be larger than 20 MB in size.
    * With every 560 pixels of an image and every 1120 pixels of a video being counted as a token, each input in the list must not exceed 32,000 tokens, and the total number of tokens across all inputs must not exceed 320,000.
* **model** (`str`) - Name of the model. Recommended option: `voyage-multimodal-3`.
* **input\_type** (`str`, optional, defaults to `None`) - Type of the input. Options: `None`, `query`, `document`.
  * When `input_type` is `None`, the embedding model directly converts the `inputs` into numerical vectors. For retrieval/search purposes, where a "query", which can be text or image in this case, is used to search for relevant information among a collection of data referred to as "documents," we recommend specifying whether your `inputs` are intended as queries or documents by setting `input_type` to `query` or `document`, respectively. In these cases, Voyage automatically prepends a prompt to your `inputs` before vectorizing them, creating vectors more tailored for retrieval/search tasks. Since `inputs` can be multimodal, "queries" and "documents" can be text, images, or an interleaving of both modalities. Embeddings generated with and without the `input_type` argument are compatible.
  * For transparency, the following prompts are prepended to your input.
    * For `query`, the prompt is " *Represent the query for retrieving supporting documents:*".
    * For `document`, the prompt is " *Represent the document for retrieval:*".
* **truncation** (`bool`, optional, defaults to `True`) - Whether to truncate the inputs to fit within the context length.
  * If `True`, an over-length input will be truncated to fit within the context length before being vectorized by the embedding model. If the truncation happens in the middle of an image, the entire image will be discarded.
  * If `False`, an error will be raised if any input exceeds the context length.

**Returns**

* A `MultimodalEmbeddingsObject`, containing the following attributes:
  * **embeddings** (`List[List[float]]`) - A list of embeddings for the corresponding list of inputs, where each embedding is a vector represented as a list of floats.
  * **text\_tokens** (`int`) - The total number of text tokens in the list of inputs.
  * **image\_pixels** (`int`) - The total number of image pixels in the list of inputs.
  * **total\_tokens** (`int`) - The combined total of text and image tokens. Every 560 pixels counts as a token.

**Example**

```python
import voyageai
from voyageai.video_utils import Video
import PIL 

vo = voyageai.Client()
# This will automatically use the environment variable VOYAGE_API_KEY.
# Alternatively, you can use vo = voyageai.Client(api_key="<your secret key>")

# Example input containing a text string, Image object, and Video object
inputs = [
    ["This is a banana.", PIL.Image.open("banana.jpg"), Video.from_path("banana.mp4", model="voyage-multimodal-3.5")]
]

# Vectorize inputs
result = vo.multimodal_embed(inputs, model="voyage-multimodal-3.5")
print(result.embeddings)
```

```python Output
[
  [0.027587890625, -0.021240234375, 0.018310546875,...]
]
```

***

# REST API

Voyage multimodal embeddings can be accessed by calling the endpoint `POST https://api.voyageai.com/v1/multimodalembeddings`. Please refer to the [Multimodal Embeddings API Reference](https://docs.voyageai.com/reference/multimodal-embeddings-api) for the specification and an example.

***

# TypeScript Library

Voyage multimodal embeddings are accessible in TypeScript through the <a href="https://www.npmjs.com/package/voyageai" target="_blank">Voyage TypeScript Library</a>, which exposes all the functionality of our multimodal embeddings endpoint (see [Multimodal Embeddings API Reference](https://docs.voyageai.com/reference/multimodal-embeddings-api)).