> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Rerankers

Voyage reranker endpoint receives as input a query, a list of documents, and other arguments such as the model name, and returns a response containing the reranking results.


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
    "/rerank": {
      "post": {
        "tags": [
          "Inference"
        ],
        "summary": "Rerankers",
        "description": "Voyage reranker endpoint receives as input a query, a list of documents, and other arguments such as the model name, and returns a response containing the reranking results.\n",
        "operationId": "reranker-api",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": [
                  "query",
                  "documents",
                  "model"
                ],
                "properties": {
                  "query": {
                    "type": "string",
                    "description": "The query as a string. The query can contain a maximum of 8,000 tokens for  `rerank-2.5` and `rerank-2.5-lite`; 4,000 tokens for `rerank-2`; 2,000  tokens for `rerank-2-lite` and `rerank-1`; and 1,000 tokens for `rerank-lite-1`.\n"
                  },
                  "documents": {
                    "type": "array",
                    "description": "The documents to be reranked as a list of strings. <ul> <li> The number of documents cannot exceed 1,000. </li> <li> The sum of the number of tokens in the query and the number of tokens in  any single document cannot exceed 32,000 for `rerank-2.5` and `rerank-2.5-lite`;  16,000 for `rerank-2`; 8,000 for `rerank-2-lite` and `rerank-1`; and 4,000 for  `rerank-lite-1`. </li> <li> The total number of tokens, defined as \"the number of query tokens × the  number of documents + sum of the number of tokens in all documents\", cannot  exceed 600K for `rerank-2.5`, `rerank-2.5-lite`, `rerank-2` and `rerank-2-lite`;  and 300K for `rerank-1` and `rerank-lite-1`. Please see our <a href=\"https://docs.voyageai.com/docs/faq#what-is-the-total-number-of-tokens-for-the-rerankers\">FAQ</a>. </li> </ul>\n",
                    "items": {
                      "type": "string"
                    }
                  },
                  "model": {
                    "type": "string",
                    "description": "Name of the model. Recommended options: `rerank-2.5`, `rerank-2.5-lite`.\n"
                  },
                  "top_k": {
                    "type": "integer",
                    "description": "The number of most relevant documents to return. If not specified, the reranking results of all documents will be returned.\n",
                    "nullable": true,
                    "default": null
                  },
                  "return_documents": {
                    "type": "boolean",
                    "description": "Whether to return the documents in the response. Defaults to `false`. <ul> <li> If `false`, the API will return a list of {\"index\", \"relevance_score\"} where \"index\" refers to the index of a document within the input list. </li> <li> If `true`, the API will return a list of {\"index\", \"document\", \"relevance_score\"} where \"document\" is the corresponding document from the input list. </li> </ul>\n",
                    "default": false
                  },
                  "truncation": {
                    "type": "boolean",
                    "description": "Whether to truncate the input to satisfy the \"context length limit\" on the query and the documents. Defaults to `true`. <ul> <li> If `true`,  the query and documents will be truncated to fit within the context length limit, before processed by the reranker model. </li> <li> If `false`, an error will be raised when the query exceeds 8,000 tokens for  `rerank-2.5` and `rerank-2.5-lite`; 4,000 tokens for `rerank-2`; 2,000 tokens  `rerank-2-lite` and `rerank-1`; and 1,000 tokens for `rerank-lite-1`, or the sum  of the number of tokens in the query and the number of tokens in any single document  exceeds 32,000 for `rerank-2.5` and `rerank-2.5-lite`; 16,000 for `rerank-2`; 8,000 for `rerank-2-lite` and `rerank-1`; and 4,000 for `rerank-lite-1`. </li> </ul>\n",
                    "default": true
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
                  "$ref": "#/components/schemas/RerankingObject"
                },
                "examples": {
                  "Success": {
                    "value": "{\"object\":\"list\",\"data\":[{\"relevance_score\":0.455078125,\"index\":0},{\"relevance_score\":0.439453125,\"index\":1}],\"model\":\"rerank-2.5-lite\",\"usage\":{\"total_tokens\":8}}\n"
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
              "code": "curl --request POST \\\n     --url https://api.voyageai.com/v1/rerank \\\n     --header \"Authorization: Bearer $VOYAGE_API_KEY\" \\\n     --header \"content-type: application/json\" \\\n     --data '\n{\n  \"query\": \"Sample query\",\n  \"documents\": [\n    \"Sample document 1\",\n    \"Sample document 2\"\n  ],\n  \"model\": \"rerank-2.5-lite\"\n}\n'"
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
      "RerankingObject": {
        "type": "object",
        "properties": {
          "object": {
            "type": "string",
            "description": "The object type, which is always `list`."
          },
          "data": {
            "type": "array",
            "description": "An array of the reranking results, sorted by the descending order of relevance scores.\n",
            "items": {
              "type": "object",
              "properties": {
                "index": {
                  "type": "integer",
                  "description": "The index of the document in the input list."
                },
                "relevance_score": {
                  "type": "number",
                  "description": "The relevance score of the document with respect to the query."
                },
                "document": {
                  "type": "string",
                  "description": "The document string. Only returned when return_documents is set to true.\n"
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
                "description": "The total number of tokens used for computing the reranking."
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