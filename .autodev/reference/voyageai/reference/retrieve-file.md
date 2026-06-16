> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Retrieve file

Returns information about a specific file.


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
    "/files/{file_id}": {
      "get": {
        "tags": [
          "Files"
        ],
        "summary": "Retrieve file",
        "description": "Returns information about a specific file.\n",
        "operationId": "retrieve-file",
        "parameters": [
          {
            "name": "file_id",
            "in": "path",
            "required": true,
            "description": "The ID of the file to return information about.",
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Success. The File object matching the specified ID.\n",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/FileObject"
                },
                "examples": {
                  "Success": {
                    "value": "{\n  \"id\": \"file-abc123\",\n  \"object\": \"file\",\n  \"bytes\": 372783,\n  \"created_at\": \"2025-02-11T19:52:02.536100+00:00\"\n  \"expires_at\": \"2025-03-11T19:52:02.536100+00:00\"\n  \"filename\": \"foo.jsonl\",\n  \"purpose\": \"batch\",\n}\n"
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
              "code": "curl https://api.voyageai.com/v1/files/file-abc123 \\\n  -H \"Authorization: Bearer $VOYAGE_API_KEY\" \\\n  -H \"content-type: application/json\"",
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