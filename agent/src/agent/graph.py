"""Recommendation graph — catalog-driven elicitation loop.

    ingest -+-> ask_bootstrap -> END            (no line yet; options come from
            |                                    MCP list_product_lines, only
            |                                    lines with published policies)
            +-> match -> decide -+-> ask_question -> END   (question that best
                                 |                          splits candidates)
                                 +-> verify -> explain
                                     -> verify_explanations -> present -> END

Each user turn re-enters at ingest; answers narrow the candidate set until a
line has <= TARGET_RESULTS candidates, no discriminating question remains, or
the question budget is spent. An empty candidate set is an honest no-match.
"""

from langgraph.graph import END, START, StateGraph

from agent import nodes
from agent.state import AgentState


def build_graph(checkpointer=None):
    graph = StateGraph(AgentState)
    graph.add_node("ingest", nodes.ingest)
    graph.add_node("ask_bootstrap", nodes.ask_bootstrap)
    graph.add_node("match", nodes.match)
    graph.add_node("decide", nodes.decide)
    graph.add_node("ask_question", nodes.ask_question)
    graph.add_node("verify", nodes.verify)
    graph.add_node("explain", nodes.explain)
    graph.add_node("verify_explanations", nodes.verify_explanations)
    graph.add_node("present", nodes.present)

    graph.add_edge(START, "ingest")
    graph.add_conditional_edges(
        "ingest", nodes.route_ingest, {"bootstrap": "ask_bootstrap", "match": "match"}
    )
    graph.add_edge("ask_bootstrap", END)
    graph.add_edge("match", "decide")
    graph.add_conditional_edges(
        "decide", nodes.route_decide, {"ask_question": "ask_question", "verify": "verify"}
    )
    graph.add_edge("ask_question", END)
    graph.add_edge("verify", "explain")
    graph.add_edge("explain", "verify_explanations")
    graph.add_edge("verify_explanations", "present")
    graph.add_edge("present", END)

    return graph.compile(checkpointer=checkpointer)
