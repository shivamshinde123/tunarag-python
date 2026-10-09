from tunarag import GoogleADKAdapter
from tunarag.serialization import content_hash

from .test_google_adk import adk_model


class ToolPipeline:
    def __init__(self, vectors, chat):
        self.vectors = vectors
        self.chat = chat
        self.runners = {}
        self.calls = []
        self.sessions = set()
        self.active = 0
        self.peak = 0

    def factory(self, candidate):
        from google.adk.agents import Agent
        from google.adk.integrations.langchain import LangchainTool
        from google.adk.runners import InMemoryRunner
        from google.genai import types
        from langchain_core.tools import create_retriever_tool

        key = content_hash(candidate.parameters)
        if key in self.runners:
            return self.runners[key]
        top_k = candidate.parameters["top_k"]
        tool = LangchainTool(
            create_retriever_tool(
                self.vectors.as_retriever(search_kwargs={"k": top_k}),
                name="search_paper",
                description="Retrieve relevant excerpts from the approved paper.",
                document_separator="\n---CHUNK---\n",
            )
        )

        def start(callback_context):
            session = callback_context.session.id
            assert session not in self.sessions
            self.sessions.add(session)
            self.active += 1
            self.peak = max(self.peak, self.active)
            callback_context.state["owner"] = session
            callback_context.state["calls"] = 0

        def before(callback_context, llm_request):
            assert callback_context.state["owner"] == callback_context.session.id
            count = callback_context.state["calls"]
            if count >= 2:
                raise RuntimeError("Two-call ADK allowance exhausted before sending")
            callback_context.state["calls"] = count + 1
            llm_request.config.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY" if count == 0 else "NONE",
                    allowed_function_names=["search_paper"] if count == 0 else None,
                )
            )

        def after_tool(tool, args, tool_context, tool_response):
            assert tool.name == "search_paper"
            assert tool_context.state["owner"] == tool_context.session.id
            text = tool_response if isinstance(tool_response, str) else tool_response["result"]
            contexts = text.split("\n---CHUNK---\n")
            assert len(contexts) == top_k
            tool_context.state["contexts"] = contexts
            self.calls.append(
                {
                    "session": tool_context.session.id,
                    "query": args["query"],
                    "top_k": top_k,
                    "count": len(contexts),
                }
            )

        def after_model(callback_context, llm_response):
            if callback_context.state["calls"] == 2:
                assert callback_context.state["owner"] == callback_context.session.id
                llm_response.custom_metadata = {
                    "contexts": callback_context.state["contexts"],
                    "session": callback_context.session.id,
                }
                self.active -= 1

        style = (
            "Use concise sentences."
            if candidate.parameters["prompt_style"] == "brief"
            else "Use bullets covering all requested facts."
        )
        runner = InMemoryRunner(
            app_name="tunarag_tool_test",
            agent=Agent(
                name="paper_rag",
                model=adk_model(self.chat),
                tools=[tool],
                instruction=(
                    "Retrieve first. Answer only from retrieved excerpts; "
                    "abstain if unsupported. " + style
                ),
                generate_content_config=types.GenerateContentConfig(
                    temperature=0, max_output_tokens=512
                ),
                before_agent_callback=start,
                before_model_callback=before,
                after_tool_callback=after_tool,
                after_model_callback=after_model,
            ),
        )
        self.runners[key] = runner
        return runner

    def adapter(self):
        def output(event):
            return {
                "answer": "".join(
                    part.text or "" for part in event.content.parts if not part.thought
                ),
                **event.custom_metadata,
            }

        return GoogleADKAdapter(
            factory=self.factory,
            output_mapper=output,
            identity={"model": self.chat.model_name, "tools": "search_paper-v1"},
        )

    async def close(self):
        for runner in self.runners.values():
            sessions = await runner.session_service.list_sessions(
                app_name=runner.app_name, user_id="tunarag-evaluation"
            )
            assert not sessions.sessions
            await runner.close()
