> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Flexible Dimensions and Quantization

Storage and search costs in vector-based search can become significant for large corpora, such as in code retrieval with massive repositories. The costs scale linearly in the embedding dimensionality and precision (i.e., the number of bits used to encode each number). Lower dimensional embeddings and quantization (e.g., binary or int8 representations) are used to dramatically lower costs without losing much retrieval quality. These are enabled by [Matryoshka learning](https://arxiv.org/abs/2205.13147) and [quantization-aware training](https://arxiv.org/abs/1702.00758).

## Matryoshka Embeddings

Matryoshka learning creates embeddings with a nested family of embeddings with various lengths within a single vector. Concretely, for each *k* in \{256, 512, and 1024}, the first *k* entries of a 2048-dimensional embedding also form a valid *k*-dimensional embedding that is shorter with a slight loss of retrieval quality. This allows users to vectorize documents into a long 2048-dimensional vector in advance and have the flexibility to use shorter versions of the embedding (by taking the first *k* entries) without re-invoking the embedding model.

Newer Voyage models, such as `voyage-4-large`, generate Matryoshka embeddings and support multiple output dimensions directly through the `output_dimension` parameter (see supported model embedding dimensions [here](https://docs.voyageai.com/docs/embeddings)).

### How can I truncate Matryoshka embeddings?

You can truncate Matryoshka embeddings by keeping the leading subset of dimensions. For example, the following Python code demonstrates how to truncate 1024-dimensional vectors to 256 dimensions:

```python
import voyageai
import numpy as np

def embd_normalize(v: np.ndarray) -> np.ndarray:
    """
    Normalize the rows of a 2D NumPy array to unit vectors by dividing each row by its Euclidean
    norm. Raises a ValueError if any row has a norm of zero to prevent division by zero.
    """
    row_norms = np.linalg.norm(v, axis=1, keepdims=True)
    if np.any(row_norms == 0):
        raise ValueError("Cannot normalize rows with a norm of zero.")
    return v / row_norms


vo = voyageai.Client()

# Generate voyage-4-large vectors, which by default are 1024-dimensional floating-point numbers
embd = vo.embed(["Sample text 1", "Sample text 2"], model="voyage-4-large").embeddings

# Set shorter dimension
short_dim = 256

# Resize and normalize vectors to shorter dimension
resized_embd = embd_normalize(np.array(embd)[:, :short_dim]).tolist()
```

## Quantization

Quantized embeddings have lower precision, with 8 bits or 1 bit per dimension, reducing storage costs by 4x or 32x compared to 32-bit floats. Newer Voyage embedding models, such as `voyage-4-large`, support lower-precision embeddings in various data types: `int8` (8-bit signed integer), `uint8` (8-bit unsigned integer), `binary` (bit-packed `int8`), and `ubinary` (bit-packed `uint8`). Most vector databases directly support storing and searching with quantized embeddings, including Milvus, Qdrant, Weaviate, Elasticsearch, and Vespa AI.

Supported Voyage models enable quantization by specifying the output data type with the `output_dtype` parameter:

* `float`: Each returned embedding is a list of 32-bit (4-byte) [single-precision floating-point](https://en.wikipedia.org/wiki/Single-precision_floating-point_format) numbers. This is the default and provides the highest precision / retrieval accuracy.
* `int8` and `uint8`: Each returned embedding is a list of 8-bit (1-byte) integers ranging from -128 to 127 and 0 to 255, respectively.
* `binary` and `ubinary`: Each returned embedding is a list of 8-bit integers that represent bit-packed, quantized single-bit embedding values: `int8` for `binary` and `uint8` for `ubinary`. The length of the returned list of integers is **1/8** of the actual dimension of the embedding. The `binary` type uses the offset binary method, explained below.

  **Binary quantization example:**

  Consider the following eight embedding values: -0.03955078, 0.006214142, -0.07446289, -0.039001465, 0.0046463013, 0.00030612946, -0.08496094, and 0.03994751. With binary quantization, values less than or equal to zero will be quantized to a binary zero, and positive values to a binary one, resulting in the following binary sequence: 0, 1, 0, 0, 1, 1, 0, 1. These eight bits are then packed into a single 8-bit integer: 01001101 (with the leftmost bit as the most significant bit).

  * `ubinary`: The binary sequence is directly converted and represented as the unsigned integer (`uint8`) 77.
  * `binary`: The binary sequence is represented as the signed integer (`int8`) -51, calculated using the [offset binary](#offset-binary) method (77 - 128 = -51).

### Offset binary

[Offset binary](https://en.wikipedia.org/wiki/Offset_binary) is a method for representing negative numbers in binary form (i.e., [signed number representations](https://en.wikipedia.org/wiki/Signed_number_representations)). This approach is used when representing quantized binary embedding values, specifically when the `output_dtype` parameter is set to `binary`. The binary values are bit-packed, with each 8-bit sequence represented as an integer calculated using the offset binary method. In this method, an offset is *added* to an integer before converting to binary and *subtracted* when converting from binary to a signed integer. For signed 8-bit integers, which have a range of -128 to 127, the offset is typically 128.

**Signed integer to binary example:**

To represent -32 as an 8-bit binary number:

1. Add the offset (128) to -32, resulting in 96.
2. Convert 96 to binary: 01100000.

**Binary to signed integer example:**

To determine the signed integer from the 8-bit binary number 01010101:

1. Convert it directly to an integer: 85.
2. *Subtract* the offset (128) from 85, resulting in -43.

## Examples

Below are Python code examples for converting and working with binary embeddings.

```python Convert float to binary & ubinary
import numpy as np
import voyageai

vo = voyageai.Client()

# Generate float embeddings
embd_float = vo.embed('Sample text 1', model='voyage-4-large', output_dimension=2048).embeddings[0]

# Compute 512-dimensional bit-packed binary and ubinary embeddings from 2048-dimensional float embeddings
embd_binary_calc = (np.packbits(np.array(embd_float) > 0, axis=0) - 128).astype(np.int8).tolist() # Quantize, binary offset
embd_binary_512_calc = embd_binary_calc[0:64] # Truncate. Binary is 1/8 length of embedding dimension.

embd_ubinary_calc = (np.packbits(np.array(embd_float) > 0, axis=0)).astype(np.uint8).tolist() # Quantize, binary offset
embd_ubinary_512_calc = embd_ubinary_calc[0:64] # Truncate. Binary is 1/8 length of embedding dimension.
```

```python Unpack binary & ubinary embeddings
import numpy as np
import voyageai

vo = voyageai.Client()

# Generate binary embeddings
embd_binary = vo.embed('Sample text 1', model='voyage-4-large', output_dtype='binary', output_dimension=2048).embeddings[0]
embd_ubinary = vo.embed('Sample text 1', model='voyage-4-large', output_dtype='ubinary', output_dimension=2048).embeddings[0]

# Unpack bits
embd_binary_bits = [format(x, f'08b') for x in np.array(embd_binary) + 128] # List of (bits) strings
embd_binary_unpacked = [bit == '1' for bit in ''.join(embd_binary_bits)] # List of booleans

embd_ubinary_bits = [format(x, f'08b') for x in np.array(embd_ubinary)] # List of (bits) strings
embd_ubinary_unpacked = [bit == '1' for bit in ''.join(embd_ubinary_bits)] # List of booleans
```

We also have a getting started tutorial in Google Colab [here](https://colab.research.google.com/drive/1JcIZ3dHLjsuxwgXsGTL79VwawMl9XXYt).