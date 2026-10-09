import itertools
import json
import random
import re
import time
from pathlib import Path

from tunarag import Categorical, LangChainAdapter, LangGraphAdapter, SearchSpace
from tunarag.serialization import content_hash


def question_sets():
    from tunarag import EvaluationDataset

    records = json.loads(Path(__file__).with_name("attention_questions.json").read_text())
    assert len(records) == 30
    development = EvaluationDataset.from_records(
        [item for item in records if item["split"] == "optimize"]
    )
    held_out = EvaluationDataset.from_records([item for item in records if item["split"] == "test"])
    assert len(development.examples) == 10 and len(held_out.examples) == 20
    assert not {item.id for item in development.examples} & {item.id for item in held_out.examples}
    return development, held_out


def term_coverage(output, example):
    terms = example.metadata["required_terms"]
    return sum(bool(re.search(term, output["answer"], re.IGNORECASE)) for term in terms) / len(
        terms
    )


def page_recall(output, example):
    relevant = set(example.relevant_document_ids)
    return len(relevant & set(output["pages"])) / len(relevant) if relevant else 1.0


def search_space():
    return SearchSpace(
        {
            "top_k": Categorical((1, 3)),
            "chunk_size": Categorical((500, 1000)),
            "overlap": Categorical((0, 80)),
            "search_type": Categorical(("similarity", "mmr")),
            "prompt_style": Categorical(("brief", "structured")),
        }
    )


class ChatSuggestionProvider:
    def __init__(self, chat):
        self.chat = chat
        self.valid = 0
        self.requests = []
        dimensions = search_space().describe()
        self.choices = [
            dict(zip(dimensions, values, strict=True))
            for values in itertools.product(*(item["values"] for item in dimensions.values()))
        ]
        random.Random(17).shuffle(self.choices)
        self.used_choices = set()

    async def suggest(self, request):
        payload = {
            "search_space": request.search_space,
            "available_configurations": {
                index: parameters
                for index, parameters in enumerate(self.choices)
                if index not in self.used_choices
            },
            "observations": [
                {
                    "parameters": dict(item.candidate.parameters),
                    "metrics": [
                        {"name": metric.name, "value": metric.value} for metric in item.metrics
                    ],
                }
                for item in request.observations
            ],
            "suggestion_number": request.suggestion_number,
        }
        self.requests.append(payload)
        schema = {
            "type": "object",
            "properties": {
                "candidate_index": {
                    "type": "integer",
                    "enum": list(payload["available_configurations"]),
                }
            },
            "required": ["candidate_index"],
            "additionalProperties": False,
        }
        response = await self.chat.bind(
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "rag_configuration",
                    "strict": True,
                    "schema": schema,
                },
            }
        ).ainvoke(
            [
                (
                    "system",
                    "Select an available RAG configuration. Return only a JSON object "
                    "with its integer candidate_index. Use observations to improve quality "
                    "with low cost and latency. No extra keys.",
                ),
                ("human", json.dumps(payload)),
            ]
        )
        index = json.loads(response.content)["candidate_index"]
        if isinstance(index, bool) or index not in payload["available_configurations"]:
            raise ValueError("suggestion must select an available configuration")
        proposal = self.choices[index]
        search_space().validate(proposal)
        self.used_choices.add(index)
        self.valid += 1
        return proposal

    def fingerprint(self):
        return {"model": self.chat.model_name, "prompt_version": 2}


class PipelineBuilder:
    def __init__(self, documents, provider, framework, directory):
        from langchain_classic.embeddings import CacheBackedEmbeddings
        from langchain_classic.storage import LocalFileStore

        self.documents = documents
        self.provider = provider
        self.framework = framework
        self.built = []
        self.stores = {}
        self.outputs = []
        self.embeddings = CacheBackedEmbeddings.from_bytes_store(
            provider["embeddings"],
            LocalFileStore(str(directory / "embeddings")),
            namespace=getattr(provider["embeddings"], "model", "offline"),
            query_embedding_cache=True,
            key_encoder="sha256",
        )
        self.document_hash = content_hash(
            [{"text": item.page_content, "page": item.metadata["page"]} for item in documents]
        )

    def factory(self, candidate):
        from langchain_classic.chains import create_retrieval_chain
        from langchain_classic.chains.combine_documents import create_stuff_documents_chain
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.runnables import RunnablePassthrough
        from langchain_core.vectorstores import InMemoryVectorStore
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        parameters = dict(candidate.parameters)
        key = parameters["chunk_size"], parameters["overlap"]
        if key not in self.stores:
            chunks = RecursiveCharacterTextSplitter(
                chunk_size=key[0], chunk_overlap=key[1]
            ).split_documents(self.documents)
            assert chunks and all(item.page_content.strip() for item in chunks)
            self.stores[key] = InMemoryVectorStore.from_documents(chunks, self.embeddings)
        retriever = self.stores[key].as_retriever(
            search_type=parameters["search_type"], search_kwargs={"k": parameters["top_k"]}
        )
        style = (
            "Use concise sentences."
            if parameters["prompt_style"] == "brief"
            else "Use short bullet points with all requested facts."
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Answer only from the provided context. If unsupported, say the paper "
                    "does not provide the answer. Correct false premises. "
                    + style
                    + " Context: {context}",
                ),
                ("human", "{input}"),
            ]
        )
        chain = create_retrieval_chain(
            retriever,
            create_stuff_documents_chain(
                self.provider["chat"],
                prompt,
                output_parser=RunnablePassthrough(),
            ),
        )
        chain = (
            RunnablePassthrough.assign(started_at=lambda inputs: time.perf_counter())
            | chain
            | RunnablePassthrough.assign(
                latency_seconds=lambda raw: time.perf_counter() - raw["started_at"]
            )
        )
        if self.framework == "langgraph":
            from langgraph.graph import END, START, StateGraph
            from typing_extensions import TypedDict

            class RAGState(TypedDict):
                input: str
                answer: object
                context: list
                latency_seconds: float

            graph = StateGraph(RAGState)
            graph.add_node("rag", chain)
            graph.add_edge(START, "rag")
            graph.add_edge("rag", END)
            chain = graph.compile()
        self.built.append(parameters)
        return chain

    def adapter(self, revision=1):
        adapter_type = LangChainAdapter if self.framework == "langchain" else LangGraphAdapter

        def output_mapper(raw):
            message = raw["answer"]
            usage = message.usage_metadata or {}
            output = {
                "answer": message.content,
                "contexts": [item.page_content for item in raw["context"]],
                "pages": [str(item.metadata["page"] + 1) for item in raw["context"]],
                "latency_seconds": raw["latency_seconds"],
                "generation_cost_estimate": usage.get("input_tokens", 0) * 0.0000004
                + usage.get("output_tokens", 0) * 0.0000016,
            }
            assert output["answer"] and output["contexts"]
            self.outputs.append(output)
            return output

        return adapter_type(
            factory=self.factory,
            input_key="input",
            output_mapper=output_mapper,
            identity={
                "pdf": self.document_hash,
                "model": getattr(self.provider["chat"], "model_name", "offline"),
                "embedding_model": getattr(self.provider["embeddings"], "model", "offline"),
                "prompt_revision": revision,
            },
        )

    async def independent_run(self, candidate, example):
        start = time.perf_counter()
        raw = await self.factory(candidate).ainvoke({"input": example.query})
        message = raw["answer"]
        output = {
            "answer": message.content,
            "contexts": [item.page_content for item in raw["context"]],
            "pages": [str(item.metadata["page"] + 1) for item in raw["context"]],
            "latency_seconds": time.perf_counter() - start,
        }
        assert output["answer"] and len(output["contexts"]) <= candidate.parameters["top_k"]
        return output
