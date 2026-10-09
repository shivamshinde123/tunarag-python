# Framework Integrations

Only official framework adapters are accepted by `Optimizer`. Install the matching extra:
`langchain`, `langgraph`, or `google-adk` (Python 3.10+). Factories must return real framework
objects. Mapping functions configure framework inputs, configuration, session state, and outputs.

::: tunarag.integrations.google_adk.GoogleADKAdapter

Google ADK creates and deletes a fresh session for each sample, including retries. Candidate
parameters become session state; agent construction settings require a runner factory. The
application owns and closes runners. For LangGraph checkpointing, map each evaluation to its own
thread instead of reusing a production conversation. Include model, corpus, prompt, and mapper
revisions in adapter `identity` so cache and resume do not mix pipeline versions.

## LangChain and LangGraph

::: tunarag.integrations.runnables
    options:
      show_root_full_path: false

## MLflow

::: tunarag.integrations.mlflow
    options:
      show_root_full_path: false
