# TunaRAG UI and UX Wireframes

> V0.3 scope: TunaRAG tunes genuine LangChain runnables, compiled LangGraph graphs, and Google ADK 2.x runners through official adapters. Handwritten RAG adapters are unsupported. Evaluators, search strategies, and callbacks remain extensible.

## Scope

V0.1 is a Python library. A CLI may follow the orchestration API; a web dashboard is a
non-goal. This document covers developer workflows and observable states.

```text
Select an official framework adapter
      |
Define search space, evaluators, objective, strategy
      |
Create Optimizer -> await aoptimize(dataset)
      |
Inspect OptimizationResult and persisted study
```

Errors identify the object, field or stage, and corrective action without credentials or
evaluation content.

```text
TunaRAG  study support-rag-v1
Status       Running
Trials       8 completed  1 running  1 failed
Best score   0.8731
Usage        $1.42 estimated  48.2 s elapsed

0007  completed  0.8731  cache 42%
0008  failed     adapter.timeout  retrying
0009  running    18 of 50 samples
```

Required states distinguish validation, create/resume, incompatible resume, provider wait,
execution, cache hit, retry, cancellation, every stop reason, success, and no-success finish.
Output remains usable in noninteractive logs. V0.1 machine output is deterministic JSON and
flattened CSV through `OptimizationResult`; a CLI, interactive renderer, and associated
color/accessibility behavior remain `TBD` for a later version.
