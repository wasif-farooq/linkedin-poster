"""Entry point for `langgraph dev` / LangGraph Studio (the platform supplies persistence)."""

from app.graph.builder import build_graph

graph = build_graph()
