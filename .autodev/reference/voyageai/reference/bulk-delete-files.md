> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Bulk delete files

Delete one or more files at once.


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
    "/files/delete": {
      "post": {
        "tags": [
          "Files"
        ],
        "summary": "Bulk delete files",
        "description": "Delete one or more files at once.\n",
        "operationId": "bulk-delete-files",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": [
                  "file_ids"
                ],
                "properties": {
                  "file_ids": {
                    "type": "array",
                    "items": {
                      "type": "string"
                    },
                    "description": "The IDs of the files to delete. This operational is “all or nothing” — meaning all the file IDs must be valid and successfully deleted or none of the files specified by the file IDs are deleted.\n"
                  }
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Success. All files specified by the file IDs were deleted.\n",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/FileDeletedBulk"
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
              "code": "curl -X POST https://api.voyageai.com/v1/files/delete \\\n  -H \"Authorization: Bearer $VOYAGE_API_KEY\" \\\n  -H \"content-type: application/json\" \\\n  -d ' \n  {\n    \"file_ids\": [\n      \"file-abc123\",\n      \"file-def456\",\n      \"file-ghi789\"\n    ]\n  }"
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
      "FileDeletedBulk": {
        "type": "object",
        "properties": {
          "success": {
            "type": "boolean",
            "description": "Indicates whether the bulk delete was successful. Returns `true` if the all files were successfully deleted, otherwise returns `false`.\n"
          },
          "error_file_ids": {
            "type": "array",
            "description": "An array of file IDs that could not be deleted. This array will not be returned if all files were successfully deleted.\n",
            "items": {
              "type": "string"
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