> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Batch Inference

<Callout icon="🚧" theme="warn">
  This feature is in Public Preview. The feature and the corresponding documentation might change at any time during the Preview period. To learn more, see <Anchor label="Preview Features" target="_blank" href="https://www.mongodb.com/docs/preview-features/">Preview Features</Anchor>.
</Callout>

Real-time API responses are unnecessary in some scenarios, such as when embedding large corpora for vector databases or running large-scale evaluations. In these cases, the **Batch API** provides a simple way to process multiple requests efficiently. It handles retries and threading automatically, ensuring high throughput and reliable results. You bundle requests into a single file, initiate a batch job, track its status as it runs, and retrieve results once complete. Our Batch API offers a **12-hour completion window** and is more cost-effective than standard endpoints, providing a **33% discount**.

You can also explore the API reference directly <Anchor label="here" target="_blank" href="https://docs.voyageai.com/reference/batch">here</Anchor>.

# Getting Started

You can create batch jobs for the following endpoints: `/v1/embeddings` (<a href="https://docs.voyageai.com/reference/embeddings-api" target="_blank">Text embedding models</a>), `/v1/contextualizedembeddings` (<a href="https://docs.voyageai.com/reference/contextualized-embeddings-api" target="_blank">Contextualized chunk embedding models</a>), and `v1/rerank` (<a href="https://docs.voyageai.com/reference/reranker-api" target="_blank">Rerankers</a>).

**Projects**. Batch jobs are tied to specific projects and can only be viewed or managed within the projects linked to the API keys used to create them.

## 1. Create Batch Input File

The input data for batch requests are bundled in a JSONL file. This separation of input data from other request parameters allows for reuse of the batch input file -- supporting experimentation, evaluation, and re-vectorizing use cases over the same data. The details, including an example of the batch request input object, are in the following collapsed section.

<Accordion title="Batch request input object" icon="fa-info-circle">
  A batch request input object requires two keys: `custom_id` and `body`.

  * **`custom_id`**. This is a user-provided ID used to match outputs to inputs since the ordering of output results will not necessarily be aligned with the ordering of input requests. The `custom_id` values must be unique for each request in a batch.
  * **`body`**. This is the input data of the underlying endpoint. The model and other other parameters are specified at the batch level will be used for all requests in the batch. How the input data is specified depends on the endpoint: `input` for `v1/embeddings`, `inputs` for `v1/contextualizedembeddings`, and `query` and `documents` for `v1/rerank`.

  **Examples**

  ```json JSONL snippet for v1/embeddings
  {"custom_id": "request_1", "body": {"input": ["Sample text 1", "Sample text 2"]}}
  {"custom_id": "request_2", "body": {"input": ["Sample text 3", "Sample text 4"]}}
  ```

  ```json JSONL snippet for v1/contextualizedembeddings
  {"custom_id": "request_1", "body": {"inputs": [["doc_1_chunk_1", "doc_1_chunk_2"], ["doc_2_chunk_1", "doc_2_chunk_2"]]}}
  {"custom_id": "request_2", "body": {"inputs": [["doc_3_chunk_1", "doc_3_chunk_2"], ["doc_4_chunk_1", "doc_4_chunk_2"]]}}
  ```

  ```json JSONL snippet for v1/rerank
  {"custom_id": "request_1", "body": {"query": "Sample query 1", "documents": ["Sample document 1", "Sample document 2"]}}
  {"custom_id": "request_2", "body": {"query": "Sample query 2", "documents": ["Sample document 3", "Sample document 4"]}}
  ```
</Accordion>

**100K inputs per batch maximum**. Each batch can contain up to 100K inputs. Each request may include multiple examples. For instance, a single request to the `v1/embeddings` endpoint can contain up to 1,000 examples. Each request is still subject to the context length (e.g., 32K tokens for `voyage-4-large`) and total token limit (e.g., 120K tokens for `voyage-4-large`) of the target model and endpoint.

## 2. Upload Batch Input File

In order for batch jobs to access the batch input file, it must be uploaded using our <Anchor label="Files API" target="_blank" href="https://docs.voyageai.com/reference/files">Files API</Anchor>. The following example uploads a batch input file named `foo.jsonl`:

```curl
curl https://api.voyageai.com/v1/files \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -F purpose="batch" \
  -F file="@foo.jsonl"
```

```json Example cURL response
{
  "object": "file",
  "id": "file_abc123",
  "purpose": "batch",
  "filename": "foo.jsonl",
  "bytes": 372783,
  "created_at": "2025-02-11T19:52:02.536100+00:00"
}
```

When you successfully upload your batch input file, the input file will be given a file ID that can be referenced when creating a batch job.

<Accordion title="Listing files" icon="fa-info-circle">
  You can always verify your files by listing them. The following example lists your available files:

  ```cURL cURL
  curl https://api.voyageai.com/v1/files \
    -H "Authorization: Bearer $VOYAGE_API_KEY"
  ```

  ```json Example cURL response
  {
  "object": "list", 
  "data": [
    {
      "id": "file-abc123",
      "object": "file",
      "bytes": 372783,
      "created_at": "2025-02-11T19:52:02.536100+00:00",
      "expires_at": "2025-03-11T19:52:02.536100+00:00",
      "filename": "foo.jsonl",
      "purpose": "batch",
    },
    {
      "id": "file-def456",
      "object": "file",
      "bytes": 972782,
      "created_at": "2025-11-19T07:20:59.230081+00:00",
      "expires_at": "2025-12-19T07:20:59.230081+00:00",
      "filename": "batch_batch-ghi789_output",
      "purpose": "batch-output",
    }
  ],
  "first_id": "file-abc123",
  "last_id": "file-def456",
  "has_more": false
  ```
</Accordion>

## 3. Create the Batch

When creating a batch, you must specify the batch input file, endpoint, completion window, and model. Optionally, you can provide up to 16 custom key-value pairs to associate with the batch job using the `metadata` parameter. For example, you could provide a custom `corpus` key to associate the corpus you may be vectorizing.

A `Batch` object containing metadata about the batch job, such as an assigned batch id, will be created and returned.

**Example**

```curl
curl -X POST https://api.voyageai.com/v1/batches \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -H "content-type: application/json" \
  -d ' 
  {
    "endpoint": "/v1/embeddings",
    "completion_window": "12h",
    "request_params": {
      "model": "voyage-4-large"
    },
    "input_file_id": "file-abc123",
    "metadata": {
      "corpus": "company policies"
    }
  }'
```

The `request_params` parameter specifies all endpoint parameters for requests, except for the input data, which is provided in the batch input JSONL file. The only required endpoint parameter—and the only mandatory key in `request_params`—is `model`. Essentially, the batch job combines the input data from the batch input JSONL file with the endpoint parameters in `request_params` to form the inference requests that are ultimately processed. Any endpoint parameter not explicitly set will default to the endpoint’s default value. Below is an example of a batch job created with multiple endpoint parameters specified in `request_params`.

```curl
curl -X POST https://api.voyageai.com/v1/batches \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -H "content-type: application/json" \
  -d ' 
  {
    "endpoint": "/v1/embeddings",
    "completion_window": "12h",
    "requests_params": {
      "model": "voyage-4-large",
      "input_type": "document",
      "output_dimension": 512,
      "output_dtype": "uint8"
    },
    "input_file_id": "file-abc123",
    "metadata": {
      "corpus": "company policies"
    }
  }'
```

## 4. Check Batch Status

Once created, batch jobs have an **12-hour completion window**. If a batch job cannot be finished within this time, the job will process as many requests as possible. Completed results will be provided in an output file, and users will only be charged for tokens used in these requests.

As the batch job progresses through its lifecycle, the Batch object will be updated, and it can be queried to check on the status of the batch job. More on the batch lifecycle in a [section below](https://docs.voyageai.com/docs/batch-inference#batch-lifecycle) .

### Example: Retrieve batch for status

To check the status of a batch, you need to specify its batch id.

```curl
curl https://api.voyageai.com/v1/batches/batch-abc123 \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -H "Content-Type: application/json"
```

```json Example cURL response
{
  "id": "batch_abc123",
  "object": "batch",
  "endpoint": "/v1/embeddings",
  "errors": null,
  "input_file_id": "file_abc123",
  "completion_window": "8h",
  "status": "in_progress",
  "output_file_id": null,
  "error_file_id": null,
  "created_at": "2025-01-29 13:05:05",
  "in_progress_at": "2025-01-29 13:05:15",
  "expected_completion_at": "2025-01-30 13:05:05",
  "finalizing_at": null,
  "completed_at": null,
  "failed_at": null,
  "partial_finalizing_at": null,
  "partially_completed_at": null,
  "canceling_at": null,
  "canceled_at": null,
  "request_counts": {
    "total": 10000,
    "completed": 363,
    "failed": 0
  },
  "metadata": {
    "corpus": "company policies" 
  }
}
```

## 5. Retrieve Results

Once a batch job successfully completes, a JSONL output file will be created with the results, where there will be one response line for every successful request from the batch input file.

<Callout icon="🚧" theme="warn">
  Note that the output line order may not match the input line order. Instead of relying on order to process your results, use the `custom_id` field, which will be present in each line of your output results file and allow you to map requests in your input to results in your output.
</Callout>

You can retrieve and download the output file using the <Anchor label="Files API" target="_blank" href="https://docs.voyageai.com/reference/files">Files API</Anchor>. The Batch object will provide the file id of the output file in the `output_file_id` field.

For failed requests, error information will be written to an error file specified by the `error_file_id` field of the Batch object.

**Example**

```curl
curl https://api.voyageai.com/v1/batches/batch-def456 \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -H "Content-Type: application/json"
```

```json Example cURL response
{
  "id": "batch_def456",
  "object": "batch",
  "endpoint": "/v1/embeddings",
  "errors": null,
  "input_file_id": "file_def456",
  "completion_window": "8h",
  "status": "completed",
  "output_file_id": "file_xyz987",
  "error_file_id": null,
  "created_at": "2025-01-29 15:52:43",
  "in_progress_at": "2025-01-29 15:52:53",
  "expected_completion_at": "2025-01-30 15:52:43",
  "finalizing_at": "2025-01-29 16:45:24",
  "completed_at": "2025-01-29 17:09:15",
  "failed_at": null,
  "partial_finalizing_at": null,
  "partially_completed_at": null,
  "canceling_at": null,
  "canceled_at": null,
  "request_counts": {
    "total": 20000,
    "completed": 20000,
    "failed": 0
  },
  "metadata": {
    "corpus": "product documentation"
  }
}
```

The following code snippets show you how to retrieve the actual contents of your output file.

```curl
curl https://api.voyageai.com/v1/files/file-xyz987/content \
  -H "Authorization: Bearer $VOYAGE_API_KEY" > foo_batch_results.jsonl
```

```python
import voyageai
vo = voyageai.Client()

output_file = vo.files.content(file_id='file_xyz987')
output_file.write_to_file(file='foo_batch_results.jsonl')
```

## 6. Cancel a Batch

You can cancel an ongoing batch at any time. The batch's status will change to `cancelling` until in-flight requests are complete (up to 10 minutes), after which the status will change to `cancelled`.

Any completed results before cancelation will be available in the output file, and users will be charged for the tokens consumed from completed requests. There is no penalty for cancellation.

**Example**

```curl
curl https://api.voyageai.com/v1/batches/batch-abc123/cancel \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -H "Content-Type: application/json" \
  -X POST
```

```json Example cURL response cancelling
{
  "id": "batch-def456",
  "object": "batch",
  "endpoint": "/v1/embeddings",
  "errors": null,
  "input_file_id": "file-def456",
  "completion_window": "12h",
  "model": "voyage-3.5",
  "status": "cancelling",
  "output_file_id": null,
  "error_file_id": null,
  "request_counts": {
    "total": 10,
    "completed": 2,
    "failed": 0
  },
  "metadata": {
    "corpus": "product documentation"
  },
  "created_at": "2025-11-19T02:46:44.547607+00:00",
  "in_progress_at": "2025-11-19T02:46:45.992553+00:00",
  "finalizing_at": null,
  "completed_at": null,
  "failed_at": null,
  "expected_completion_at": "2025-11-19T10:46:44.547607+00:00",
  "cancelling_at": "2025-11-19T02:46:46.202515+00:00",
  "cancelled_at": null
}
```

```json Example cURL response cancelled
{
  "id": "batch-def456",
  "object": "batch",
  "endpoint": "/v1/embeddings",
  "errors": null,
  "input_file_id": "file-def456",
  "completion_window": "12h",
  "model": "voyage-3.5",
  "status": "cancelled",
  "output_file_id": "file-klm789",
  "error_file_id": null,
  "request_counts": {
    "total": 10,
    "completed": 2,
    "failed": 0
  },
  "metadata": {
    "corpus": "product documentation"
  },
  "created_at": "2025-11-19T02:46:44.547607+00:00",
  "in_progress_at": "2025-11-19T02:46:45.992553+00:00",
  "finalizing_at": null,
  "completed_at": null,
  "failed_at": null,
  "expected_completion_at": "2025-11-19T10:46:44.547607+00:00",
  "cancelling_at": "2025-11-19T02:46:46.202515+00:00",
  "cancelled_at": "2025-11-19T02:46:48.970135+00:00"
}
```

## 7. Get a List of Batches

At any time, you can see all your batches. For users with many batches, you can use the `limit` and `after` parameters to paginate your results.

```curl
curl https://api.voyageai.com/v1/batches \
  -H "Authorization: Bearer $VOYAGE_API_KEY" \
  -H "Content-Type: application/json"
```

```json Example cURL response
{
  "object": "list",
  "data": [
    {
      "id": "batch-abc123",
      "object": "batch",
      "endpoint": "/v1/embeddings",
      "errors": null,
      "input_file_id": "file-abc123",
      "completion_window": "12h",
      "model": "voyage-3.5",
      "status": "completed",
      "output_file_id": "file-hij789",
      "error_file_id": null,
      "request_counts": {
        "total": 2,
        "completed": 2,
        "failed": 0
      },
      "metadata": {
        "corpus": "company policies"
      },
      "created_at": "2025-11-19T02:47:42.031781+00:00",
      "in_progress_at": "2025-11-19T02:47:46.166042+00:00",
      "finalizing_at": "2025-11-19T02:48:00.101059+00:00",
      "completed_at": "2025-11-19T02:48:09.221885+00:00",
      "failed_at": null,
      "expected_completion_at": "2025-11-19T10:47:42.031781+00:00",
      "cancelling_at": null,
      "cancelled_at": null
    },
    {
      "id": "batch-def456",
      "object": "batch",
      "endpoint": "/v1/embeddings",
      "errors": null,
      "input_file_id": "file-def456",
      "completion_window": "12h",
      "model": "voyage-3.5",
      "status": "cancelled",
      "output_file_id": "file-klm789",
      "error_file_id": null,
      "request_counts": {
        "total": 10,
        "completed": 2,
        "failed": 0
      },
      "metadata": {
        "corpus": "product documentation"
      },
      "created_at": "2025-11-19T02:46:44.547607+00:00",
      "in_progress_at": "2025-11-19T02:46:45.992553+00:00",
      "finalizing_at": null,
      "completed_at": null,
      "failed_at": null,
      "expected_completion_at": "2025-11-19T10:46:44.547607+00:00",
      "cancelling_at": "2025-11-19T02:46:46.202515+00:00",
      "cancelled_at": "2025-11-19T02:46:48.970135+00:00"
    }
  ]
}
```

# Batch lifecycle

The following diagram illustrates the batch lifecycle, showing state transitions from one status to another.

<Image align="center" alt="Batch Lifecycle" border={false} src="https://files.readme.io/96601ff80bf6cca1d14136a34bad5b72ade4f5a5a1370d5fe37c6c6122e73783-batch-api-Batch_Lifecycle.png" />

All jobs start by validating the input (i.e., their status is `validating`).

**Standard, successful batch job.** A standard, successful job is ready to process after input validation is complete, moving into the `in_progress` status. The results are prepared once the job is completed and the job is in the `finalizing` status. Once the results are ready, the job is marked as `completed`.

**Failed job.** Jobs not properly validated will have a `failed` status.

**Cancelled jobs.** Users can cancel jobs at any time. If a cancellation is initiated, the job enters the `cancelling` status, which can take up to 10 minutes until the job is actually cancelled. Once cancelled, the job is marked as `cancelled`.

**Partially complete jobs.** If the job has not been completed within the completion window, it will prepare the results that it has completed. The unfinished requests will be written in your error file with the message shown below. You can use the `custom_id` to retrieve the request data for unfinished requests. You will only be charged for tokens consumed from any completed requests.

**Lifecycle tracking.** The batch lifecycle is tracked in the Batch object, storing the timestamps of when the batch enters various statuses. See the <Anchor label="Batch API reference" target="_blank" href="https://docs.voyageai.com/reference/batch">Batch API reference</Anchor> for details.

The table below summarizes and describes the various batch statuses.

| Status        | Description                                                                                                                                                                                  |
| :------------ | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `validating`  | The input file is being validated before the batch can begin. This checks that the requests in the input file are valid, such as adhering to the input request schema and valid schema keys. |
| `failed`      | Input validation has failed.                                                                                                                                                                 |
| `in_progress` | The batch is currently being run.                                                                                                                                                            |
| `finalizing`  | The batch has been completed, and the results are being prepared.                                                                                                                            |
| `completed`   | The batch has been completed, and the results are ready                                                                                                                                      |
| `cancelling`  | The batch is being canceled (it may take up to 10 minutes).                                                                                                                                  |
| `cancelled`   | The batch was canceled.                                                                                                                                                                      |

# Batch Results

As mentioned earlier, once a batch job successfully completes, a JSONL output file will be created with the results, where there will be one response line for every successful request from the batch input file.

```json Batch output file object
{
  "batch_id": "batch-abc123",
  "custom_id": "task_0",
  "response": {
    "status_code": 200,
    "body": {
      "object": "list",
      "data": [
        {
          "object": "embedding",
          "index": 0,
          "embedding": [-0.0076687671244, "...", 0.023722406476]
        }
      ],
      "model": "voyage-4-large",
      "usage": {"total_tokens": 33}
    }
  },
  "error": null
}
```

# Batch Errors

For failed requests, error information will be written to an error file, a JSONL file where there will be one line for every failed requests.

```json
{
  "batch_id": "batch-abc123",
  "custom_id": "task_1",
  "response": {
    "status_code": 500,
    "message": "Internal Server Error"
  },
  "error": null
}
```

```json
{
  "batch_id": "batch-abc123",
  "custom_id": "task_1",
  "response": null,
  "error": {
    "code": "batch_expired",
    "message": "This request could not be executed before the completion window expired."
  }
}
```

# Organization Limits

**In-flight batch jobs** are those with the following statuses: `validating`, `in_progress`, `finalizing`, and `cancelling`. An organization must not have more than **100 in-flight batch jobs** or **exceed 1B tokens** across all of them. Additionally, each batch job may contain no more than **100K inputs**.

## Maximizing Token Limits

If you need to process more than 1B tokens, a simple approach is to submit batches totalling 1B tokens every 12 hours (the duration of the completion window). However, to maximize processing throughput you can continuously submit batches, backing off when you receive 429s. While you're still limited to 1B tokens at any given time, this method ensures you're continuously utilizing as much of that limit as possible. Below is pseudocode that demonstrates how to implement this.

```python
# Continuously submit batches, backing off on 429s.
while have_more_batches():
    status_code = send_next_batch()

    # 429 indicates we've hit a limit (e.g., too many active batches)
    if status_code == 429:
        # Sleep 30 minutes before retrying. This backoff method is sufficient
        # and exponential backoff is not needed.
        sleep(30 * 60)
```

# Model Availability

The Batch API can currently be used to execute queries against the following models: `voyage-4-large`, `voyage-4`, `voyage-4-lite`, `voyage-3-large`, `voyage-3.5`, `voyage-3.5-lite`, `voyage-context-3`, `voyage-code-3`, `voyage-code-2`, `rerank-2.5`, and `rerank-2.5-lite`.