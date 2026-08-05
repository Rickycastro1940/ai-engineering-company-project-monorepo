"""Pipeline test configuration for LangGraph / RAG / tool evals."""

collect_ignore = [
    # Prefects/Supabase telemetry pipeline — unrelated to LangGraph agent evals;
    # requires optional deps not installed in the agent eval environment.
    "test_pipeline.py",
]
