def validate_paid_payload(body, priced_models, allow_tools=False):
    if body.get("model") not in priced_models or body.get("n", 1) != 1 or body.get("stream"):
        raise RuntimeError("Unpriced model or unsupported request")
    output = body.get("max_tokens", body.get("max_completion_tokens", 0))
    if not isinstance(output, int) or isinstance(output, bool) or not 0 <= output <= 512:
        raise RuntimeError("Output limit exceeds approved allowance")
    tools = body.get("tools")
    if tools:
        if not allow_tools or not isinstance(tools, list) or len(tools) != 1:
            raise RuntimeError("Tools are not authorized for this phase")
        tool = tools[0]
        function = tool.get("function", {})
        if tool.get("type") != "function" or function.get("name") != "search_paper":
            raise RuntimeError("Only the local paper retrieval tool is allowed")
        parameters = function.get("parameters", {})
        if parameters.get("type") != "object" or set(parameters.get("properties", {})) != {"query"}:
            raise RuntimeError("Unexpected retrieval tool schema")
        if parameters["properties"]["query"].get("type") != "string":
            raise RuntimeError("Retrieval query must be a string")
    response = body.get("response_format", {}).get("json_schema", {}).get("name")
    if response == "reference_quality":
        return "evaluator"
    if response in {"adk_configuration", "rag_configuration"}:
        return "search"
    if "text-embedding" in body["model"]:
        return "embedding"
    return "generation"
