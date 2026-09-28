# Copyright 2026 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""The Watcher agent: one graph node, all four tools.

A single tool-calling watcher for the four-well drilling operation. No advance
node, no playhead - the full hour is available from any message and each tool is
stateless.
"""

import litellm
from datarobot_genai.core.agents import make_system_prompt
from datarobot_genai.langgraph.agent import datarobot_agent_class_from_langgraph
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph

from agent.drilling.prompt import SYSTEM_PROMPT
from agent.drilling.tools import build_tools

litellm.modify_params = True

# The operator's message passes through unchanged; all behavior lives in the
# node's system prompt.
prompt_template = ChatPromptTemplate.from_messages(
    [
        ("user", "{topic}"),
    ]
)


def graph_factory(
    llm: BaseChatModel, tools: list[BaseTool], verbose: bool = False
) -> StateGraph[MessagesState]:
    all_tools = [*build_tools(), *tools]

    watcher = create_agent(
        llm,
        tools=all_tools,
        system_prompt=make_system_prompt(SYSTEM_PROMPT),
        name="watcher_agent",
        debug=verbose,
    )

    langgraph_workflow = StateGraph(MessagesState)
    langgraph_workflow.add_node("watcher_node", watcher)
    langgraph_workflow.add_edge(START, "watcher_node")
    langgraph_workflow.add_edge("watcher_node", END)
    return langgraph_workflow


MyAgent = datarobot_agent_class_from_langgraph(graph_factory, prompt_template)
