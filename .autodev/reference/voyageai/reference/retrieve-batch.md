> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Retrieve batch

Returns a batch.


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
    "/batches/{batch_id}": {
      "get": {
        "tags": [
          "Batch"
        ],
        "summary": "Retrieve batch",
        "description": "Returns a batch.\n",
        "operationId": "retrieve-batch",
        "parameters": [
          {
            "name": "batch_id",
            "in": "path",
            "required": true,
            "description": "The ID of the batch to retrieve.\n",
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Success. The Batch object matching the specified ID.\n",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/BatchObject"
                },
                "examples": {
                  "Success": {
                    "value": "{\n  \"id\": \"batch-abc123\",\n  \"object\": \"batch\",\n  \"endpoint\": \"/v1/embeddings\",\n  \"errors\": null,\n  \"input_file_id\": \"file-abc123\",\n  \"completion_window\": \"12h\",\n  \"model\": \"voyage-4-large\",\n  \"status\": \"completed\",\n  \"output_file_id\": \"file-hij789\",\n  \"error_file_id\": null,\n  \"request_counts\": {\n    \"total\": 2,\n    \"completed\": 2,\n    \"failed\": 0\n  },\n  \"metadata\": {\n    \"corpus\": \"company policies\"\n  },\n  \"created_at\": \"2025-11-19T02:47:42.031781+00:00\",\n  \"in_progress_at\": \"2025-11-19T02:47:46.166042+00:00\",\n  \"finalizing_at\": \"2025-11-19T02:48:00.101059+00:00\",\n  \"completed_at\": \"2025-11-19T02:48:09.221885+00:00\",\n  \"failed_at\": null,\n  \"expected_completion_at\": \"2025-11-19T10:47:42.031781+00:00\",\n  \"cancelling_at\": null,\n  \"cancelled_at\": null\n}\n"
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
              "code": "curl https://api.voyageai.com/v1/batches/batch-def456 \\\n  -H \"Authorization: Bearer $VOYAGE_API_KEY\" \\\n  -H \"content-type: application/json\"",
              "samples-languages": null
            },
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