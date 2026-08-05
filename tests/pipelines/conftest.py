"""Pipeline test configuration for Part 1 LangGraph / RAG evals."""

collect_ignore = [
    # Prefects/Supabase telemetry pipeline — unrelated to LangGraph Part 1;
    # requires optional deps not installed in the agent eval environment.
    "test_pipeline.py",
]
