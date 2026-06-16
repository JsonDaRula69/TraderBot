> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# List files

Returns a list of files that can be optionally limited to a set of results (e.g., `limit`, `after`), ordered (e.g., `order`), and filtered (e.g., `purpose`).


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
    "/files": {
      "get": {
        "tags": [
          "Files"
        ],
        "summary": "List files",
        "description": "Returns a list of files that can be optionally limited to a set of results (e.g., `limit`, `after`), ordered (e.g., `order`), and filtered (e.g., `purpose`).\n",
        "operationId": "list-files",
        "parameters": [
          {
            "name": "purpose",
            "in": "query",
            "required": false,
            "description": "Only return files with the given purpose.\n",
            "schema": {
              "type": "string"
            }
          },
          {
            "name": "limit",
            "in": "query",
            "required": false,
            "description": "A limit on the number of objects to be returned. Limit can range between 1 and 10,000.\n",
            "schema": {
              "type": "integer",
              "default": 10000,
              "minimum": 1,
              "maximum": 10000
            }
          },
          {
            "name": "order",
            "in": "query",
            "required": false,
            "description": "Sort order by the `created_at` timestamp of the objects. `asc` for ascending order and `desc` for descending order.\n",
            "schema": {
              "type": "string",
              "default": "desc",
              "enum": [
                "asc",
                "desc"
              ]
            }
          },
          {
            "name": "after",
            "in": "query",
            "required": false,
            "description": "A cursor for use in pagination. `after` is the file ID that defines your place in the list. For instance, if you make a list request and receive 100 objects, ending with `file-xyz`, your subsequent call can include `\"after\": \"file-xyz\"` in order to fetch the next page of the list.\n",
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Success. A list of paginated File objects.\n",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/SyncCursorPageFileObject"
                },
                "examples": {
                  "Success": {
                    "value": "{\n  \"object\": \"list\", \n  \"data\": [\n    {\n      \"id\": \"file-abc123\",\n      \"object\": \"file\",\n      \"bytes\": 372783,\n      \"created_at\": \"2025-02-11T19:52:02.536100+00:00\",\n      \"expires_at\": \"2025-03-11T19:52:02.536100+00:00\",\n      \"filename\": \"foo.jsonl\",\n      \"purpose\": \"batch\",\n    },\n    {\n      \"id\": \"file-def456\",\n      \"object\": \"file\",\n      \"bytes\": 972782,\n      \"created_at\": \"2025-11-19T07:20:59.230081+00:00\",\n      \"expires_at\": \"2025-12-19T07:20:59.230081+00:00\",\n      \"filename\": \"batch_batch-ghi789_output\",\n      \"purpose\": \"batch-output\",\n    }\n  ],\n  \"first_id\": \"file-abc123\",\n  \"last_id\": \"file-def456\",\n  \"has_more\": false\n"
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
              "code": "curl https://api.voyageai.com/v1/files \\\n  -H \"Authorization: Bearer $VOYAGE_API_KEY\" ",
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
      "FileObject": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "description": "The file identifier."
          },
          "object": {
            "type": "string",
            "description": "The object type, which is always `file`."
          },
          "bytes": {
            "type": "integer",
            "description": "The size of the file, in bytes."
          },
          "created_at": {
            "type": "string",
            "description": "RFC 3339 datetime string for when the file was created."
          },
          "expires_at": {
            "type": "string",
            "description": "RFC 3339 datetime string for when the file expires. Currently, this is 30 days after the file is created."
          },
          "filename": {
            "type": "string",
            "description": "The name of the file."
          },
          "purpose": {
            "type": "string",
            "description": "The intended purpose of the file. Supported values are `batch`, `batch-output`, and `batch-error`."
          }
        }
      },
      "SyncCursorPageFileObject": {
        "type": "object",
        "properties": {
          "object": {
            "type": "string",
            "description": "The object type, which is always `list`.\n"
          },
          "data": {
            "type": "array",
            "description": "An array of File objects.\n",
            "items": {
              "$ref": "#/components/schemas/FileObject"
            }
          },
          "first_id": {
            "type": "string",
            "description": "The identifier of the first File object in the `data` array. \n"
          },
          "last_id": {
            "type": "string",
            "description": "The identifier of the last File object in the `data` array.\n"
          },
          "has_more": {
            "type": "boolean",
            "description": "Returns `true` if more File objects are available; otherwise, returns `false`.\n"
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