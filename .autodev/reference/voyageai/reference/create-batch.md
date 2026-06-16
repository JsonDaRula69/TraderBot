> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Create batch

Creates and executes a batch.


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
  "paths": {
    "/batches": {
      "post": {
        "tags": [
          "Batch"
        ],
        "summary": "Create batch",
        "description": "Creates and executes a batch.\n",
        "operationId": "create-batch",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": [
                  "endpoint",
                  "input_file_id",
                  "completion_window",
                  "request_params"
                ],
                "properties": {
                  "endpoint": {
                    "type": "string",
                    "description": "The endpoint to be used for all requests in the batch. The supported endpoints are: <code>v1/embeddings</code>, <code>v1/contextualizedembeddings</code>, and <code>v1/rerank</code>.\n"
                  },
                  "input_file_id": {
                    "type": "string",
                    "description": "The ID of file that contains requests for the new batch.\nSee the Files API for how to list existing files or upload a new file. Your input file must be formatted as a JSONL file, and must be uploaded with the purpose `batch`.\n"
                  },
                  "completion_window": {
                    "type": "string",
                    "description": "The time frame within which the batch should be processed. Currently only <code>12h</code> is supported.\n"
                  },
                  "request_params": {
                    "type": "object",
                    "description": "A set of key-value pairs that define the parameters to be used for each request in the batch.\n",
                    "required": [
                      "model"
                    ],
                    "properties": {
                      "model": {
                        "type": "string",
                        "description": "The model to be used by the endpoint.\n"
                      }
                    }
                  },
                  "metadata": {
                    "type": "object",
                    "description": "Optional set of 16 key-value pairs that can be useful for storing additional metadata about the batch in a structured format. Keys can be a maximum of 64 characters long and values can be a maximum of 512 characters long.\n"
                  }
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Success. The created Batch object.\n",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BatchObject"
                },
                "examples": {
                  "Success": {
                    "value": "{\n  \"id\": \"batch-abc123\",\n  \"object\": \"batch\",\n  \"endpoint\": \"/v1/embeddings\",\n  \"errors\": null,\n  \"input_file_id\": \"file-abc123\",\n  \"completion_window\": \"12h\",\n  \"model\": \"voyage-4-large\",\n  \"status\": \"validating\",\n  \"output_file_id\": null,\n  \"error_file_id\": null,\n  \"request_counts\": {\n    \"total\": 0,\n    \"completed\": 0,\n    \"failed\": 0\n  },\n  \"metadata\": {\n    \"corpus\": \"company policies\"\n  },\n  \"created_at\": \"2025-11-19T02:47:42.031781+00:00\",\n  \"in_progress_at\": null,\n  \"finalizing_at\": null,\n  \"completed_at\": null,\n  \"failed_at\": null,\n  \"expected_completion_at\": \"2025-11-19T10:47:42.031781+00:00\",\n  \"cancelling_at\": null,\n  \"cancelled_at\": null\n}\n"
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
              "code": "curl -X POST https://api.voyageai.com/v1/batches \\\n  -H \"Authorization: Bearer $VOYAGE_API_KEY\" \\\n  -H \"content-type: application/json\" \\\n  -d '\n  {\n    \"endpoint\": \"/v1/embeddings\",\n    \"completion_window\": \"12h\",\n    \"input_file_id\": \"file-abc123\",\n    \"request_params\": {\n      \"model\": \"voyage-4-large\"\n    },\n    \"metadata\": {\n      \"corpus\": \"company policies\"\n    }\n  }"
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
      "BatchObject": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "description": "The batch identifier.\n"
          },
          "object": {
            "type": "string",
            "description": "The object type, which is always `batch`.\n"
          },
          "endpoint": {
            "type": "string",
            "description": "The endpoint used by the batch.\n"
          },
          "errors": {
            "type": "object",
            "description": "The error object containing the error code and message.\n",
            "properties": {
              "object": {
                "type": "string",
                "description": "The object type, which is always `list`.\n"
              },
              "data": {
                "type": "array",
                "description": "An array of error objects.\n",
                "items": {
                  "type": "object",
                  "properties": {
                    "code": {
                      "type": "string",
                      "description": "An error code identifying the error type.\n"
                    },
                    "line": {
                      "type": "integer",
                      "nullable": true,
                      "description": "The line number in the input file where the error occurred, if applicable.\n"
                    },
                    "message": {
                      "type": "string",
                      "description": "A human-readable message providing more details about the error.\n"
                    },
                    "param": {
                      "type": "string",
                      "nullable": true,
                      "description": "The parameter that caused the error, if applicable. \n"
                    }
                  }
                }
              }
            }
          },
          "input_file_id": {
            "type": "string",
            "description": "The ID of the input file for the batch.\n"
          },
          "completion_window": {
            "type": "string",
            "description": "The time frame within which the batch should be processed. \n"
          },
          "model": {
            "type": "string",
            "description": "The model used by the endpoint.\n"
          },
          "status": {
            "type": "string",
            "description": "The current status of the batch.\n"
          },
          "output_file_id": {
            "type": "string",
            "description": "The ID of the file containing the outputs of successfully executed requests.\n"
          },
          "error_file_id": {
            "type": "string",
            "description": "The ID of the file containing the outputs of requests with errors.\n"
          },
          "request_counts": {
            "type": "object",
            "description": "The request counts for different statuses within the batch.\n",
            "properties": {
              "total": {
                "type": "integer",
                "description": "The total number of requests in the batch.\n"
              },
              "completed": {
                "type": "integer",
                "description": "The number of requests that have been completed successfully.\n"
              },
              "failed": {
                "type": "integer",
                "description": "The number of requests that have failed.\n"
              }
            }
          },
          "metadata": {
            "type": "object",
            "description": "Set of key-value pairs attached to batch. This can be useful for storing additional information about the batch in a structured format.\n"
          },
          "created_at": {
            "type": "string",
            "description": "RFC 3339 datetime string for when the batch was created.\n"
          },
          "in_progress_at": {
            "type": "string",
            "description": "RFC 3339 datetime string for when the batch started processing.\n"
          },
          "finalizing_at": {
            "type": "string",
            "description": "RFC 3339 datetime string for when the batch started finalizing.\n"
          },
          "completed_at": {
            "type": "string",
            "description": "RFC 3339 datetime string for when the batch was completed.\n"
          },
          "failed_at": {
            "type": "string",
            "description": "RFC 3339 datetime string for when the batch failed.\n"
          },
          "expected_completion_at": {
            "type": "string",
            "description": "RFC 3339 datetime string for when the batch is expected to complete.\n"
          },
          "cancelling_at": {
            "type": "string",
            "description": "RFC 3339 datetime string for when the batch started canceling.\n"
          },
          "cancelled_at": {
            "type": "string",
            "description": "RFC 3339 datetime string for when the batch was canceled.\n"
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