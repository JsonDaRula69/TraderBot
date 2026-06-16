> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# API Key and Python Client

## Authentication with API Keys

Voyage AI utilizes API keys to monitor usage and manage permissions. To obtain your key, please sign in with your Voyage AI account and click the "Create new secret key" button in the <a href="https://dashboard.voyageai.com/organization/api-keys" target="_blank">**API keys**</a> section of the Voyage <a href="https://dashboard.voyageai.com/organization/api-keys" target="_blank">dashboard</a>. We recommend setting the API key as an environment variable. For example, in MacOS or Linux, type the following command in the terminal, replacing `<your secret key>` with your actual API key:

```shell
export VOYAGE_API_KEY="<your secret key>"
```

You can verify the setup by typing `echo $VOYAGE_API_KEY` in the terminal. It should display your API key.

Your API key is supposed to be secret -- please avoid sharing it or exposing it in browsers or apps. Please store your API key securely for future use.

## Install Voyage Python Package

You can interact with the API through HTTP requests from any language. For Python users, we offer an official package which can be installed via `pip` :

```shell
pip install -U voyageai
```

We recommend using the `-U` or `--upgrade` option to ensure you are installing the latest version of the package. This helps you access the most recent features and bug fixes.

After installation, you can test it by running:

```shell
python -c "import voyageai"
```

The installation is successful if this command runs without any errors.

## `voyageai.Client`

The Python package offers the `voyageai.Client` class as the interface to invoke Voyage's API. You can create a client object and use it to access the predictions by our models.

[`class voyageai.Client`](https://github.com/voyage-ai/voyageai-python/blob/main/voyageai/client.py)

**Parameters**

* **api\_key** (str, optional, defaults to `None`) - Voyage API key. If `None`, the client will search for the API key in the following order:
  * `voyageai.api_key_path`, path to the file containing the key;
  * environment variable `VOYAGE_API_KEY_PATH`, which can be set to the path to the file containing the key;
  * `voyageai.api_key`, an attribute of the `voyageai` module, which can be used to store the key;
  * environment variable `VOYAGE_API_KEY`.
* **max\_retries** (int, defaults to 0) - Maximum number of retries for each API request in case of rate limit errors or temporary server unavailability. The client employs a wait-and-retry strategy to handle such errors, and will raise an exception upon reaching the maximum retry limit. By default, the client does not retry.
* **timeout** (int, optional, defaults to `None`) - Maximum time in seconds to wait for a response from the API before aborting the request. If the specified timeout is exceeded, the request is terminated and a timeout exception is raised. By default, no timeout constraint is enforced.

**Example**

```python
import voyageai

vo = voyageai.Client()
# This will automatically use the environment variable VOYAGE_API_KEY.
# Alternatively, you can use vo = voyageai.Client(api_key="<your secret key>")

result = vo.embed(["hello world"], model="voyage-4-large")
```

## Asynchronous Requests

The following client-side code serves as a reference for handling high-concurrency and/or asynchronous (non-blocking) requests.

```python
import asyncio
import os

import aiohttp


async def main():
    # Number of concurrent workers (coroutines) to run in parallel
    # Each worker will make requests independently
    concurrency = 10

    async def sending_coroutine(t: int, session: aiohttp.ClientSession) -> None:
        """
        Worker coroutine that makes multiple sequential API requests.

        Args:
            t: Worker ID number for tracking/debugging
            session: Shared aiohttp session for connection pooling

        Each worker makes 100 requests sequentially, sharing the same
        session across all requests to reuse TCP connections.
        """
        # Each worker makes 100 requests
        for i in range(100):
            # Use async context manager to ensure response is properly closed
            async with session.post(
                # Update for your endpoint, model, and input data
                # "a " * 1000 creates a ~1000-token string to test larger payloads
                f"https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {os.getenv('VOYAGE_API_KEY')}"},
                json={"model": "voyage-4-large", "input": ["a " * 1000]}
            ) as response:
                assert response.status == 200, (
                    f"Response status code {response.status}: {response.text}"
                )
                # Log progress showing which worker and which iteration
                print(f"Processed request {i=} in thread {t=}")

    # Create a single session to be shared across all workers
    # This enables connection pooling and reduces overhead
    async with aiohttp.ClientSession() as session:
        # asyncio.gather runs all coroutines concurrently
        # The * operator unpacks the list comprehension into separate arguments
        # Creates 10 workers (t=0 through t=9), each sharing the same session
        await asyncio.gather(
            *[sending_coroutine(t, session) for t in range(concurrency)],
        )


if __name__ == "__main__":
    # Entry point: starts the async event loop and runs main()
    # asyncio.run() handles event loop creation, execution, and cleanup
    asyncio.run(main())
```