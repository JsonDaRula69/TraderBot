> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Error Codes

The following table shows the possible error codes that might be returned from the API.

<Table>
  <thead>
    <tr>
      <th>
        <div style={{ width: "80px" }}>
          Error Code
        </div>
      </th>

      <th>
        <div style={{ width: "170px" }}>
          Error Type
        </div>
      </th>

      <th>
        Description
      </th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <td>
        🔴 400
      </td>

      <td>
        `Invalid Request`
      </td>

      <td>
        * **Cause:** The request is invalid, which might be due to one of the following reasons:

        <ul>
          <li>The request body is not a valid [JSON](https://en.wikipedia.org/wiki/JSON);</li>
          <li>A parameter is invalid or has the wrong type.</li>
          <li>Batch size is too large;</li>
          <li>Total number of tokens in the batch exceeds the limit;</li>
          <li>Number of tokens in an example exceeds the context length;</li>
        </ul>

        **Solution:** The specific error will be indicated in the error message. Double check the request body and correct the errors.
      </td>
    </tr>

    <tr>
      <td>
        🔴 401
      </td>

      <td>
        `Unauthorized`
      </td>

      <td>
        * **Cause:** Invalid authentication.<br /> **Solution:** Ensure the API key is correctly specified in the HTTP request header. Please create or view your API key in our [dashboard](https://dash.voyageai.com).
      </td>
    </tr>

    <tr>
      <td>
        🔴 403
      </td>

      <td>
        `Forbidden`
      </td>

      <td>
        * **Cause:** The IP address you are sending the request from might be forbidden.<br /> **Solution:** Try to use a different IP address to call the API.
      </td>
    </tr>

    <tr>
      <td>
        🔴 429
      </td>

      <td>
        `Rate Limit Exceeded`
      </td>

      <td>
        * **Cause:** The frequency of your requests is too high.<br /> **Solution:** Please pace your requests. Read the [rate limit guide](https://docs.voyageai.com/docs/rate-limits) for more information.
      </td>
    </tr>

    <tr>
      <td>
        🔴 500
      </td>

      <td>
        `Server Error`
      </td>

      <td>
        * **Cause:** Unexpected issue on our servers.<br /> **Solution:** Retry your request after a brief wait. If the error persists, please contact us at [contact@voyageai.com](mailto:contact@voyageai.com).
      </td>
    </tr>

    <tr>
      <td>
        🔴 502 <br /> 🔴 503 <br /> 🔴 504
      </td>

      <td>
        `Service Unavailable`
      </td>

      <td>
        * **Cause:** Our servers are currently experiencing high traffic.<br /> **Solution:** Retry your requests after a brief wait.
      </td>
    </tr>
  </tbody>
</Table>