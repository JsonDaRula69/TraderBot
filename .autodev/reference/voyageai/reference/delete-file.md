> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Delete file

Delete a file.


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
      "delete": {
        "tags": [
          "Files"
        ],
        "summary": "Delete file",
        "description": "Delete a file.\n",
        "operationId": "delete-file",
        "parameters": [
          {
            "name": "file_id",
            "in": "path",
            "required": true,
            "description": "The ID of the file to delete.",
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Success. The File object matching the specified ID is deleted.\n",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/FileDeleted"
                },
                "examples": {
                  "Success": {
                    "value": "{\n  \"id\": \"file-abc123\",\n  \"object\": \"file\",\n  \"deleted\": true\n}\n"
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
              "code": "curl -X POST https://api.voyageai.com/v1/files/file-abc123 \\\n  -X DELETE \\\n  -H \"Authorization: Bearer $VOYAGE_API_KEY\"",
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
      "FileDeleted": {
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
          "deleted": {
            "type": "boolean",
            "description": "Indicates whether the file was successfully deleted. Returns `true` if the file was deleted, otherwise returns `false`.\n"
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