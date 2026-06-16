> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Contextualized chunk embedding models

The Voyage contextualized chunk embedding endpoint accepts document chunks—in addition to queries and full documents—and returns a response containing contextualized chunk vector embeddings. These contextualized chunk embeddings capture not only the local details within each chunk but also global, coarse-grained metadata from the entire document.

# OpenAPI definition

```json
{
  "openapi": "3.0.2",
  "info": {
    "title": "Voyage API",
    "description": "The VoyageAI REST API. Please see https://docs.voyageai.com/reference for more details.\n",
    "version": "1.1",
    "contact": {
      "name": "VoyageAI Support",
      "url": "https://docs.voyageai.com/docs/faq",
      "email": "contact@voyageai.com"
    },
    "license": {
      "name": "MIT",
      "url": "https://github.com/voyage-ai/voyage-openapi/blob/main/LICENSE"
    }
  },
  "servers": [
    {
      "url": "https://api.voyageai.com/v1"
    }
  ],
  "security": [
    {
      "ApiKeyAuth": []
    }
  ],
  "tags": [
    {
      "name": "Inference"
    }
  ],
  "paths": {
    "/contextualizedembeddings": {
      "post": {
        "tags": [
          "Inference"
        ],
        "summary": "Contextualized chunk embedding models",
        "description": "The Voyage contextualized chunk embedding endpoint accepts document chunks—in addition to queries and full documents—and returns a response containing contextualized chunk vector embeddings. These contextualized chunk embeddings capture not only the local details within each chunk but also global, coarse-grained metadata from the entire document.",
        "operationId": "contextualized-embeddings-api",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": [
                  "inputs",
                  "model"
                ],
                "properties": {
                  "inputs": {
                    "type": "array",
                    "description": "A list of lists, where each inner list contains a query, a document, or document chunks to be vectorized.<br>\nEach inner list in <code>inputs</code> represents a set of text elements that will be embedded together. Each element in the list is encoded not just independently, but also encodes context from the other elements in the same list.<br>\n<pre><code> inputs = [[\"text_1_1\", \"text_1_2\", ..., \"text_1_n\"],\n          [\"text_2_1\", \"text_2_2\", ..., \"text_2_m\"]]\n</code></pre>\n<br> <b>Document Chunks</b>. Most commonly, each inner list contains chunks from a single document, ordered by their position in the document. In this case:\n<pre><code> inputs = [[\"doc_1_chunk_1\", \"doc_1_chunk_2\", ..., \"doc_1_chunk_n\"],\n          [\"doc_2_chunk_1\", \"doc_2_chunk_2\", ..., \"doc_2_chunk_m\"]]\n</code></pre>\nEach chunk is encoded in context with the others from the same document, resulting in more context-aware embeddings. <strong>We recommend that supplied chunks <em>not</em> have any overlap.</strong><br> <br> <b>Context-Agnostic Behavior for Queries and Documents</b>. If there is one element per inner list, each text is embedded independently—similar to standard (context-agnostic) embeddings:\n<pre><code> inputs = [[\"query_1\"], [\"query_2\"], ..., [\"query_k\"]]\n inputs = [[\"doc_1\"], [\"doc_2\"], ..., [\"doc_k\"]]\n</code></pre>\nTherefore, if the inputs are queries, each inner list should contain a single query (i.e., a length of one), as shown above, and the <code>input_type</code> should be set to <code>query</code>. <br>\nThe following constraints apply to the <code>inputs</code> list: <ul>\n  <li> The list must not contain more than 1,000 inputs. </li>\n  <li> The total number of tokens across all inputs must not exceed 120K. </li>\n  <li> The total number of chunks across all inputs must not exceed 16K. </li>\n</ul>\n",
                    "items": {
                      "type": "array",
                      "description": "For queries, the list contains only a single query. For documents or document chunks, the list should include all chunks from a single document, ordered by their position in the document, or the entire document may be provided as a single chunk. The total number of tokens in the list must not exceed 32,000 tokens.\n",
                      "items": {
                        "type": "string",
                        "description": "A query, document, or chunk of text from a document.\n"
                      }
                    }
                  },
                  "model": {
                    "type": "string",
                    "description": "Name of the model. Recommended options: `voyage-context-3`.\n"
                  },
                  "input_type": {
                    "type": "string",
                    "description": "Type of the input text. Defaults to `null`. Other options: `query`, `document`. <ul> <li> When `input_type` is `null`, the embedding model directly converts the inputs into numerical vectors. For retrieval/search purposes, where a \"query\" is used to search for relevant information among a collection of data referred to as \"documents,\" we recommend specifying whether your inputs are intended as queries or documents by setting `input_type` to `query` or `document`, respectively. In these cases, Voyage automatically prepends a prompt to your `inputs` before vectorizing them, creating vectors more tailored for retrieval/search tasks. Embeddings generated with and without the `input_type` argument are compatible. </li> <li> For transparency, the following prompts are prepended to your input. </li>\n  <ul>\n    <li> For <code>query</code>, the prompt is <i>\"Represent the query for retrieving supporting documents: \".</i> </li>\n    <li> For <code>document</code>, the prompt is <i>\"Represent the document for retrieval: \".</i> </li>\n  </ul> \n<ul> <ul>\n",
                    "enum": [
                      null,
                      "query",
                      "document"
                    ],
                    "nullable": true,
                    "default": null
                  },
                  "output_dimension": {
                    "type": "integer",
                    "description": "The number of dimensions for resulting output embeddings. Defaults to `null`.  `voyage-context-3` supports the following `output_dimension` values: 2048, 1024 (default), 512, and 256.  If set to `null`, the model uses the default value of 1024.\n",
                    "nullable": true,
                    "default": null
                  },
                  "output_dtype": {
                    "type": "string",
                    "description": "The data type for the embeddings to be returned. Defaults to `float`. Other options: `int8`, `uint8`, `binary`, `ubinary`. Please see our <a href=\"https://docs.voyageai.com/docs/flexible-dimensions-and-quantization#quantization\" target=\"_blank\">guide</a> for more details about output data types. <ul> <li> `float`: Each returned embedding is a list of 32-bit (4-byte) <a href=\"https://en.wikipedia.org/wiki/Single-precision_floating-point_format\" target=\"_blank\">single-precision floating-point</a> numbers. This is the default and provides the highest precision / retrieval accuracy. </li> <li> `int8` and `uint8`: Each returned embedding is a list of 8-bit (1-byte) integers ranging from -128 to 127 and 0 to 255, respectively. </li> <li> `binary` and `ubinary`: Each returned embedding is a list of 8-bit integers that represent bit-packed, quantized single-bit embedding values: `int8` for `binary` and `uint8` for `ubinary`. The length of the returned list of integers is 1/8 of `output_dimension` (which is the actual dimension of the embedding). The `binary` type uses the offset binary method. Please refer to our guide for details on <a href=\"https://docs.voyageai.com/docs/flexible-dimensions-and-quantization#offset-binary\" target=\"_blank\">offset binary</a> and <a href=\"https://docs.voyageai.com/docs/flexible-dimensions-and-quantization#quantization\" target=\"_blank\">binary embeddings</a>.  </ul>\n",
                    "enum": [
                      "float",
                      "int8",
                      "uint8",
                      "binary",
                      "ubinary"
                    ],
                    "default": "float"
                  },
                  "encoding_format": {
                    "type": "string",
                    "description": "Format in which the embeddings are encoded. Defaults to `null`. Other options: `base64`. <ul> <li> If `null`, each embedding is an array of float numbers when `output_dtype` is set to `float` and as an array of integers for all other values of `output_dtype` (`int8`, `uint8`, `binary`, and `ubinary`). See `output_dtype` for more details. <li> If `base64`, the embeddings are represented as a <a href=\"https://docs.python.org/3/library/base64.html\" target=\"_blank\">Base64-encoded</a> NumPy array of: </li>\n  <ul>\n    <li> Floating-point numbers (<a href=\"https:/umpy.org/doc/2.1/user/basics.types.html#numerical-data-types\" target=\"_blank\">numpy.float32</a>) for <code>output_dtype</code> set to <code>float</code>. </li>\n    <li> Signed integers (<a href=\"https:/umpy.org/doc/2.1/user/basics.types.html#numerical-data-types\" target=\"_blank\">numpy.int8</a>) for <code>output_dtype</code> set to <code>int8</code> or <code>binary</code>. </li>\n    <li> Unsigned integers (<a href=\"https:/umpy.org/doc/2.1/user/basics.types.html#numerical-data-types\" target=\"_blank\">numpy.uint8</a>) for <code>output_dtype</code> set to <code>uint8</code> or <code>ubinary</code>. </li>\n  </ul> \n</ul>\n",
                    "enum": [
                      null,
                      "base64"
                    ],
                    "nullable": true,
                    "default": null
                  }
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Success.\n",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ChunkEmbeddingsObject"
                },
                "examples": {
                  "SuccessDocuments": {
                    "summary": "Success response for documents.\n",
                    "value": "{\n  \"object\": \"list\",\n  \"data\": [\n    {\n      \"object\": \"list\",\n      \"data\": [\n        {\n          \"object\": \"embedding\",\n          \"embedding\": [0.040455919, -0.017057089, -0.007927173, \"...\", 0.042205364],\n          \"index\": 0\n        },\n        {\n          \"object\": \"embedding\",\n          \"embedding\": [0.03946501, -0.015512259, -0.009809222, \"...\", 0.033990096],\n          \"index\": 1\n        }\n      ],\n      \"index\": 0\n    },\n    {\n      \"object\": \"list\",\n      \"data\": [\n        {\n          \"object\": \"embedding\",\n          \"embedding\": [0.047289684, -0.042560715, -7.7669e-05, \"...\", 0.038691558],\n          \"index\": 0\n        },\n        {\n          \"object\": \"embedding\",\n          \"embedding\": [0.04198277, -0.036370102, -0.00352195, \"...\", 0.031879965],\n          \"index\": 1\n        }\n      ],\n      \"index\": 1\n    },\n  ],\n  \"model\": \"voyage-context-3\",\n  \"usage\": {\n    \"total_tokens\": 24 \n  }\n}\n"
                  },
                  "SuccessQueries": {
                    "summary": "Success response for queries.\n",
                    "value": "{\n  \"object\": \"list\",\n  \"data\": [\n    {\n      \"object\": \"list\",\n      \"data\": [\n        {\n          \"object\": \"embedding\",\n          \"embedding\": [0.00738032, -0.025062965, 0.007892424, \"...\" , 0.002048415],\n          \"index\": 0\n        }\n      ],\n      \"index\": 0\n    },\n    {\n      \"object\": \"list\",\n      \"data\": [\n        {\n          \"object\": \"embedding\",\n          \"embedding\": [0.056637563, -0.026602492, 0.021989964, \"...\" , 0.004612529],\n          \"index\": 0\n        }\n      ],\n      \"index\": 1\n    }\n  ],\n  \"model\": \"voyage-context-3\",\n  \"usage\": {\n    \"total_tokens\": 4 \n  }\n}\n"
                  }
                }
              }
            }
          },
          "4XX": {
            "$ref": "#/components/responses/4XX"
          },
          "5XX": {
            "$ref": "#/components/responses/5XX"
          }
        },
        "x-readme": {
          "code-samples": [
            {
              "language": "shell",
              "name": "Documents",
              "code": "curl -X POST https://api.voyageai.com/v1/contextualizedembeddings \\\n  -H \"Authorization: Bearer $VOYAGE_API_KEY\" \\\n  -H \"content-type: application/json\" \\\n  -d ' \n  {\n    \"inputs\": [\n      [\"doc_1_chunk_1\", \"doc_1_chunk_2\"],\n      [\"doc_2_chunk_1\", \"doc_2_chunk_2\"]\n    ],\n    \"input_type\": \"document\",\n    \"model\": \"voyage-context-3\"\n  }\n  '"
            },
            {
              "language": "shell",
              "name": "Queries",
              "code": "curl -X POST https://api.voyageai.com/v1/contextualizedembeddings \\\n  -H \"Authorization: Bearer $VOYAGE_API_KEY\" \\\n  -H \"content-type: application/json\" \\\n  -d ' \n  {\n    \"inputs\": [\n      [\"query_1\"],\n      [\"query_2\"]\n    ],\n    \"input_type\": \"query\",\n    \"model\": \"voyage-context-3\"\n  }\n  '"
            }
          ]
        }
      }
    }
  },
  "components": {
    "securitySchemes": {
      "ApiKeyAuth": {
        "type": "apiKey",
        "in": "header",
        "name": "Authorization: Bearer",
        "x-default": "$VOYAGE_API_KEY"
      }
    },
    "responses": {
      "4XX": {
        "description": "Client error  <p> This indicates an issue with the request format or frequency. Please see our  [Error Codes](https://docs.voyageai.com/docs/error-codes) guide. </p>\n",
        "content": {
          "application/json": {
            "schema": {
              "properties": {
                "detail": {
                  "type": "string",
                  "description": "The error message."
                }
              }
            }
          }
        }
      },
      "5XX": {
        "description": "Server Error <p> This indicates our servers are experiencing high traffic or having an unexpected issue. Please see our  [Error Codes](https://docs.voyageai.com/docs/error-codes) guide. </p>\n"
      }
    },
    "schemas": {
      "ChunkEmbeddingsObject": {
        "type": "object",
        "properties": {
          "object": {
            "type": "string",
            "description": "The object type, which is always `list`."
          },
          "data": {
            "type": "array",
            "description": "An array of contextualized embeddings.\n",
            "items": {
              "type": "object",
              "properties": {
                "object": {
                  "type": "string",
                  "description": "The object type, which is always `list`.\n"
                },
                "data": {
                  "type": "array",
                  "description": "An array of embedding objects.",
                  "items": {
                    "type": "object",
                    "properties": {
                      "object": {
                        "type": "string",
                        "description": "The object type, which is always `embedding`.\n"
                      },
                      "embedding": {
                        "type": "array",
                        "description": "Each embedding is a vector represented as an array of float numbers when `output_dtype` is set to `float` and as an array of integers for all other values of `output_dtype` (`int8`, `uint8`, `binary`, and `ubinary`). The length of this vector varies depending on the specific model, `output_dimension`, and `output_dtype`.\n",
                        "items": {
                          "type": "number"
                        }
                      },
                      "index": {
                        "type": "integer",
                        "description": "An integer representing the index of the query or the contextualized chunk embedding within the list of embeddings from the same document.\n"
                      }
                    }
                  }
                },
                "index": {
                  "type": "integer",
                  "description": "An integer representing the index of the query or document within the list of queries or documents, respectively.       \n"
                }
              }
            }
          },
          "model": {
            "type": "string",
            "description": "Name of the model."
          },
          "usage": {
            "type": "object",
            "properties": {
              "total_tokens": {
                "type": "integer",
                "description": "The total number of tokens used for computing the embeddings."
              }
            }
          }
        }
      }
    }
  },
  "x-readme": {
    "headers": [],
    "explorer-enabled": false,
    "proxy-enabled": false,
    "samples-enabled": true
  },
  "x-readme-fauxas": true
}
```