"""Three real RAG apps over the same corpus, built the way each framework's docs recommend.

Real OpenRouter embeddings + chat (gpt-4.1-mini). Nothing here is TunaRAG-specific except the adapters.
"""

from __future__ import annotations

import os
import re
from functools import cache
from pathlib import Path
from typing import Any, TypedDict

from dotenv import load_dotenv

REPO = Path(r"D:\WPI Things\Coding Projects\autorag-tuner")
load_dotenv(REPO / ".env")
BASE = "https://openrouter.ai/api/v1"
CHAT_MODEL = "openai/gpt-4.1-mini"
EMBED_MODEL = "openai/text-embedding-3-small"
KEY = os.environ["OPENROUTER_API_KEY"]

from corpus import DOCS  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_core.prompts import ChatPromptTemplate  # noqa: E402
from langchain_core.vectorstores import InMemoryVectorStore  # noqa: E402
from langchain_openai import ChatOpenAI, OpenAIEmbeddings  # noqa: E402

PROMPTS = {
    "terse": "Answer with only the fact asked for, no extra words.",
    "grounded": "Answer in one sentence using only facts from the context.",
}


def chat(temperature: float = 0.0, max_tokens: int = 160) -> ChatOpenAI:
    return ChatOpenAI(
        model=CHAT_MODEL, temperature=temperature, api_key=KEY, base_url=BASE, max_tokens=max_tokens
    )


@cache
def vector_store() -> InMemoryVectorStore:
    embeddings = OpenAIEmbeddings(
        model=EMBED_MODEL, api_key=KEY, base_url=BASE, check_embedding_ctx_length=False
    )
    docs = [
        Document(page_content=text, metadata={"doc_id": doc_id}) for doc_id, text in DOCS.items()
    ]
    return InMemoryVectorStore.from_documents(docs, embeddings)


def system_prompt(style: str) -> str:
    return (
        "You are Brightwave's support assistant. Use only the context. If the context lacks the "
        f"answer, say you don't know. {PROMPTS[style]}\n\nContext:\n{{context}}"
    )


# --------------------------------------------------------------------- LangChain (factory per candidate)
def langchain_factory():
    from langchain_classic.chains import create_retrieval_chain
    from langchain_classic.chains.combine_documents import create_stuff_documents_chain

    @cache
    def build(top_k: int, style: str, temperature: float):
        prompt = ChatPromptTemplate.from_messages(
            [("system", system_prompt(style)), ("human", "{input}")]
        )
        retriever = vector_store().as_retriever(search_kwargs={"k": top_k})
        return create_retrieval_chain(
            retriever, create_stuff_documents_chain(chat(temperature), prompt)
        )

    def factory(candidate):
        p = candidate.parameters
        return build(int(p["top_k"]), str(p["style"]), float(p.get("temperature", 0.0)))

    return factory


def langchain_output(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": result["answer"],
        "contexts": [d.page_content for d in result["context"]],
        "document_ids": [d.metadata["doc_id"] for d in result["context"]],
    }


# --------------------------------------------------------------------- LangGraph (params via config)
class RagState(TypedDict, total=False):
    question: str
    documents: list
    answer: Any  # the AIMessage, so TunaRAG can discover usage_metadata


def langgraph_graph():
    from langgraph.graph import END, START, StateGraph

    async def retrieve(state: RagState, config):
        k = config["configurable"]["top_k"]
        docs = await vector_store().asimilarity_search(state["question"], k=k)
        return {"documents": docs}

    async def generate(state: RagState, config):
        style = config["configurable"]["style"]
        context = "\n\n".join(d.page_content for d in state["documents"])
        message = await chat().ainvoke(
            [("system", system_prompt(style).format(context=context)), ("human", state["question"])]
        )
        return {"answer": message}

    builder = StateGraph(RagState)
    builder.add_node("retrieve", retrieve)
    builder.add_node("generate", generate)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)
    return builder.compile()


def langgraph_output(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": state["answer"].content,
        "contexts": [d.page_content for d in state["documents"]],
        "document_ids": [d.metadata["doc_id"] for d in state["documents"]],
    }


# --------------------------------------------------------------------- Google ADK (params via session state)
def adk_runner():
    from google.adk.agents import LlmAgent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import InMemoryRunner
    from google.adk.tools import ToolContext

    def search_handbook(query: str, tool_context: ToolContext) -> dict:
        """Search the Brightwave support handbook and return the most relevant passages."""
        k = int(tool_context.state.get("top_k", 2))
        docs = vector_store().similarity_search(query, k=k)
        return {
            "passages": [{"doc_id": d.metadata["doc_id"], "text": d.page_content} for d in docs]
        }

    agent = LlmAgent(
        name="brightwave_support",
        model=LiteLlm(model=f"openrouter/{CHAT_MODEL}", api_key=KEY),
        instruction=(
            "You are Brightwave's support assistant. Always call search_handbook first, then "
            "answer using only the returned passages. Style: {style?}"
        ),
        tools=[search_handbook],
    )
    return InMemoryRunner(agent=agent, app_name="brightwave_rag")


# --------------------------------------------------------------------- shared evaluators
def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9$]+", text.lower()))


def answer_recall(output: dict[str, Any], example: Any) -> float:
    expected = words(example.reference_answer or "")
    return len(expected & words(output["answer"])) / len(expected) if expected else 0.0


class RetrievalEvaluator:
    """Custom evaluator class, as in the README; versioned via fingerprint()."""

    async def evaluate(self, output, example):
        from tunarag import MetricValue

        relevant = set(example.relevant_document_ids)
        got = output.get("document_ids")
        if got is None and "tool_responses" in output:  # ADK default output (evidence fix)
            got = [
                p["doc_id"]
                for r in output["tool_responses"]
                for p in (r["response"] or {}).get("passages", [])
            ]
        if got is None:  # pipeline does not expose retrieval evidence
            return (MetricValue("retrieval_recall", None, coverage=0.0),)
        return (
            MetricValue("retrieval_recall", len(relevant & set(got)) / len(relevant)),
            MetricValue("context_count", float(len(got))),
        )

    def fingerprint(self):
        return {"evaluator": "retrieval", "version": 1}
