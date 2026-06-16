> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Multimodal embedding models

The Voyage multimodal embedding endpoint returns vector representations for a given list of multimodal inputs consisting of text, images, or an interleaving of both modalities.
<blockquote style="background-color: #e6f7ff; border-left: 4px solid #91d5ff;">
  <strong>Important:</strong> Starting December 8, 2025, the following constraints apply to all URL parameters (e.g., <code>image_url</code>)
  <ul>
    <li> Limit the number of redirects.  </li>
    <li> Require that responses include a content-length header. </li>
    <li> Respect robots.txt to prevent unauthorized scraping.  </li>
  </ul>
</blockquote>


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
    "/multimodalembeddings": {
      "post": {
        "tags": [
          "Inference"
        ],
        "summary": "Multimodal embedding models",
        "description": "The Voyage multimodal embedding endpoint returns vector representations for a given list of multimodal inputs consisting of text, images, or an interleaving of both modalities.\n<blockquote style=\"background-color: #e6f7ff; border-left: 4px solid #91d5ff;\">\n  <strong>Important:</strong> Starting December 8, 2025, the following constraints apply to all URL parameters (e.g., <code>image_url</code>)\n  <ul>\n    <li> Limit the number of redirects.  </li>\n    <li> Require that responses include a content-length header. </li>\n    <li> Respect robots.txt to prevent unauthorized scraping.  </li>\n  </ul>\n</blockquote>\n",
        "operationId": "multimodal-embeddings-api",
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
                    "description": "A list of multimodal inputs to be vectorized.<br> <br> A single input in the list is a dictionary containing a single key `\"content\"`, whose value represents a sequence of text, images, and videos. <ul>\n  <li> The value of <code>\"content\"</code> is a list of dictionaries, each representing a single piece of text or image. The dictionaries have four possible keys:\n      <ol class=\"nested-ordered-list\">\n          <li> <b>type</b>: Specifies the type of the piece of the content. Allowed values are <code>text</code>, <code>image_url</code>, <code>image_base64</code>, <code>video_url</code>, or <code>video_base64</code>.</li>\n          <li> <b>text</b>: Only present when <code>type</code> is <code>text</code>. The value should be a text string.</li>\n          <li> <b>image_base64</b>: Only present when <code>type</code> is <code>image_base64</code>. The value should be a Base64-encoded image in the <a href=\"https://developer.mozilla.org/en-US/docs/Web/URI/Schemes/data\" target=\"_blank\">data URL</a> format <code>data:[&lt;mediatype&gt;];base64,&lt;data&gt;</code>. Currently supported <code>mediatypes</code> are: <code>image/png</code>, <code>image/jpeg</code>, <code>image/webp</code>, and <code>image/gif</code>.</li>\n          <li> <b>image_url</b>: Only present when <code>type</code> is <code>image_url</code>. The value should be a URL linking to the image. We support PNG, JPEG, WEBP, and GIF images. The following constraints apply to the URL:\n              <ul>\n                  <li> Limit the number of redirects. </li>\n                  <li> Require that responses include a content-length header. </li>\n                  <li> Respect robots.txt to prevent unauthorized scraping. </li>\n              </ul>\n          </li>\n          <li> <b>video_base64</b>: Only present when <code>type</code> is <code>video_base64</code>. The value should be a Base64-encoded video in the <a href=\"https://developer.mozilla.org/en-US/docs/Web/URI/Schemes/data\" target=\"_blank\">data URL</a> format <code>data:[&lt;mediatype&gt;];base64,&lt;data&gt;</code>. Currently supported <code>mediatypes</code> are: <code>video/mp4</code>.</li>\n          <li> <b>video_url</b>: Only present when <code>type</code> is <code>video_url</code>. The value should be a URL linking to the video. We support MP4 videos. The following constraints apply to the URL:\n              <ul>\n                  <li> Limit the number of redirects. </li>\n                  <li> Require that responses include a content-length header. </li>\n                  <li> Respect robots.txt to prevent unauthorized scraping. </li>\n              </ul>\n          </li>\n      </ol>\n  </li>\n  <li> <b>Note</b>: Only one of the keys, <code>base64</code> or <code>url</code>, should be present in each dictionary for image and video data. Consistency is required within a request, meaning each request should use either <code>image_base64</code>/<code>video_base64</code> or <code>image_url</code>/<code>video_url</code> exclusively, not both.<br>\n  <br>\n  <details> <summary> Example payload where <code>inputs</code> contains an image as a URL </summary>\n      <br>\n      The <code>inputs</code> list contains a single input, which consists of a piece of text and an image (which is provided via a URL).\n      <pre><code>\n      {\n        \"inputs\": [\n          {   \n            \"content\": [\n              {   \n                \"type\": \"text\",\n                \"text\": \"This is a banana.\"\n              },\n              {   \n                \"type\": \"image_url\",\n                \"image_url\": \"https://raw.githubusercontent.com/voyage-ai/voyage-multimodal-3/refs/heads/main/images/banana.jpg\"\n              },\n              {\n                \"type\": \"video_url\",\n                \"video_url\": \"https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4\"\n              }\n            ]   \n          }   \n        ],  \n        \"model\": \"voyage-multimodal-3.5\"\n      }\n      </code></pre>\n  </details>\n  <details> <summary> Example payload where <code>inputs</code> contains a Base64 image </summary>\n      <br>\n      Below is an equivalent example to the one above where the image content is a Base64 image instead of a URL. (Base64 images can be lengthy, so the example only shows a shortened version.)\n      <pre><code>  \n      {\n        \"inputs\": [\n          {   \n            \"content\": [\n              {   \n                \"type\": \"text\",\n                \"text\": \"This is a banana.\"\n              },\n              {   \n                \"type\": \"image_base64\",\n                \"image_base64\": \"data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAA...\"\n              },\n              {\n                \"type\": \"video_base64\",\n                \"video_base64\": \"data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACA...\"\n              }  \n            ]   \n          }   \n        ],  \n        \"model\": \"voyage-multimodal-3.5\"\n      }\n      </code></pre>\n  </details>\n  </li>\n</ul>\n<span style=\"font-size: 13px;\">The following constraints apply to the <code>inputs</code> list:</span> <ul>\n    <li> The list must not contain more than 1,000 inputs. </li>\n    <li> Each image must not contain more than 16 million pixels or be larger than 20 MB in size. </li>\n    <li> Each video must not be larger than 20 MB in size. </li>\n    <li> With every 560 pixels of an image and every 1120 pixels of a video being counted as a token, each input in the list must not exceed 32,000 tokens, and the total number of tokens across all inputs must not exceed 320,000. </li>\n</ul>\n"
                  },
                  "model": {
                    "type": "string",
                    "description": "Name of the model. Recommended options: `voyage-multimodal-3.5`, `voyage-multimodal-3`.\n"
                  },
                  "input_type": {
                    "type": "string",
                    "description": "Type of the input. Defaults to `null`. Other options: `query`, `document`. <ul> <li> When `input_type` is `null`, the embedding model directly converts the `inputs` into numerical vectors. For retrieval/search purposes, where a \"query\", which can be text or image in this case, is used to search for relevant information among a collection of data referred to as \"documents,\" we recommend specifying whether your `inputs` are intended as queries or documents by setting `input_type` to `query` or `document`, respectively. In these cases, Voyage automatically prepends a prompt to your `inputs` before vectorizing them, creating vectors more tailored for retrieval/search tasks. Since inputs can be multimodal, \"queries\" and \"documents\" can be text, images, or an interleaving of both modalities. Embeddings generated with and without the `input_type` argument are compatible. </li> <li> For transparency, the following prompts are prepended to your input. </li>\n  <ul>\n    <li> For <code>query</code>, the prompt is <i>\"Represent the query for retrieving supporting documents: \".</i> </li>\n    <li> For <code>document</code>, the prompt is <i>\"Represent the document for retrieval: \".</i> </li>\n  </ul> \n<ul>\n",
                    "enum": [
                      null,
                      "query",
                      "document"
                    ],
                    "nullable": true,
                    "default": null
                  },
                  "truncation": {
                    "type": "boolean",
                    "description": "Whether to truncate the inputs to fit within the context length. Defaults to `true`. <ul>  <li> If `true`, an over-length input will be truncated to fit within the context length before being vectorized by the embedding model. If the truncation happens in the middle of an image, the entire image will be discarded. </li> <li> If `false`, an error will be raised if any input exceeds the context length. </li>  </ul>\n",
                    "default": true
                  },
                  "output_encoding": {
                    "type": "string",
                    "description": "Format in which the embeddings are encoded. Defaults to `null`. <ul> <li> If `null`, the embeddings are represented as a list of floating-point numbers. </li>  <li> If `base64`, the embeddings are represented as a Base64-encoded NumPy array of single-precision floats. </li>  </ul>\n",
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
            "description": "Success",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/MultimodalEmbeddingsObject"
                },
                "examples": {
                  "Success": {
                    "value": "{\n  \"object\": \"list\",\n  \"data\": [\n    {\n      \"object\": \"embedding\",\n      \"embedding\": [\n        0.027587891,\n        -0.021240234,\n        0.018310547,\n        \"...\",\n        -0.021240234\n      ],\n      \"index\": 0\n    }\n  ],\n  \"model\": \"voyage-multimodal-3.5\",\n  \"usage\": {\n    \"text_tokens\": 5,\n    \"image_pixels\": 2000000,\n    \"video_pixels\": 35631232,\n    \"total_tokens\": 32083\n  }\n}\n"
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
              "name": "URL",
              "code": "curl -X POST https://api.voyageai.com/v1/multimodalembeddings \\\n  -H \"Authorization: Bearer $VOYAGE_API_KEY\" \\\n  -H \"content-type: application/json\" \\\n  -d ' \n  {\n    \"inputs\": [\n      {\n        \"content\": [\n          {\n            \"type\": \"text\",\n            \"text\": \"This is a banana.\"\n          },\n          {\n            \"type\": \"image_url\",\n            \"image_url\": \"https://raw.githubusercontent.com/voyage-ai/voyage-multimodal-3/refs/heads/main/images/banana.jpg\"\n          },\n          {\n            \"type\": \"video_url\",\n            \"video_url\": \"https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4\"\n          }\n        ]\n      }\n    ],\n    \"model\": \"voyage-multimodal-3.5\"\n  }'"
            },
            {
              "language": "shell",
              "name": "Base64",
              "code": "curl -X POST https://api.voyageai.com/v1/multimodalembeddings \\\n  -H \"Authorization: Bearer $VOYAGE_API_KEY\" \\\n  -H \"content-type: application/json\" \\\n  -d ' \n  {\n    \"inputs\": [\n      {\n        \"content\": [\n          {\n            \"type\": \"text\",\n            \"text\": \"This is a banana.\"\n          },\n          {\n            \"type\": \"image_base64\",\n            \"image_base64\": \"data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAA...\"\n          },\n          {\n            \"type\": \"video_base64\",\n            \"video_base64\": \"data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACA...\"\n          }  \n        ]\n      }\n    ],\n    \"model\": \"voyage-multimodal-3\"\n  }'"
            }
          ],
          "samples-languages": [
            "shell"
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
      "MultimodalEmbeddingsObject": {
        "type": "object",
        "properties": {
          "object": {
            "type": "string",
            "description": "The object type, which is always `list`."
          },
          "data": {
            "type": "array",
            "description": "An array of embedding objects.",
            "items": {
              "type": "object",
              "properties": {
                "object": {
                  "type": "string",
                  "description": "The object type, which is always `embedding`."
                },
                "embedding": {
                  "type": "array",
                  "description": "The embedding vector consists of a list of floating-point numbers or a Base64-encoded NumPy array depending on `output_encoding`. The length of this vector varies depending on the specific model.\n"
                },
                "index": {
                  "type": "integer",
                  "description": "An integer representing the index of the embedding within the list of embeddings.\n"
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
              "text_tokens": {
                "type": "integer",
                "description": "The total number of text tokens in the list of inputs."
              },
              "image_pixels": {
                "type": "integer",
                "description": "The total number of image pixels in the list of inputs."
              },
              "video_pixels": {
                "type": "integer",
                "description": "The total number of video pixels in the list of inputs."
              },
              "total_tokens": {
                "type": "integer",
                "description": "The combined total of text and image tokens. Every 560 pixels counts as a token."
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