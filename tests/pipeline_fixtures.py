"""Framework-backed harness for isolated optimizer fault-injection tests."""

from typing import Any

from langchain_core.runnables import RunnableLambda

from tunarag import LangChainAdapter


class FixturePipeline(LangChainAdapter):
    """Keep engine test output, injected failures, and accounting deterministic."""

    def __init__(self, fixture: Any) -> None:
        self.fixture = fixture

        async def invoke(payload: Any) -> Any:
            candidate, example = payload
            return await fixture.run(candidate, example)

        super().__init__(RunnableLambda(invoke))

    async def run(self, candidate: Any, example: Any) -> Any:
        return await self._runnable.ainvoke((candidate, example))

    def fingerprint(self) -> Any:
        if hasattr(self.fixture, "fingerprint"):
            return self.fixture.fingerprint()
        return {"fixture": f"{type(self.fixture).__module__}.{type(self.fixture).__qualname__}"}


def framework_fixture(fixture: Any) -> LangChainAdapter:
    if isinstance(fixture, LangChainAdapter):
        return fixture
    return FixturePipeline(fixture)
