# TunaRAG UI and UX Wireframes

## Scope

V0.1 is a Python library. A CLI may follow the orchestration API; a web dashboard is a
non-goal. This document covers developer workflows and observable states.

```text
Define RAGAdapter
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
Output remains usable in noninteractive logs. CLI commands, renderer, color/accessibility, and
machine-output format are `TBD` until implementation.
