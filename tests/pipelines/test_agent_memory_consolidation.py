"""Memory consolidation: dedupe, summarize, discard low-relevance."""

from __future__ import annotations

from pathlib import Path

import services.agent.memory.consolidate as cons_mod
from services.agent.memory.consolidate import (
    MAX_SEMANTIC_FACTS,
    ConsolidationReport,
    consolidate_store,
)
from services.agent.memory.interface import AgentMemory
from services.agent.memory.store import MemoryStore


def test_near_deduplicate_keeps_richer_fact(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "sem.sqlite")
    store.upsert(
        text="Locations must keep 3 days of main protein inventory.",
        kind="supplier_ordering",
        source="t",
    )
    store.upsert(
        text="Locations must keep 3 days of main protein inventory always.",
        kind="supplier_ordering",
        source="t",
    )
    assert store.count() == 2
    report = consolidate_store(store)
    assert report.deduplicated_ids
    assert store.count() == 1
    remaining = store.list_records()[0]
    assert "3 days" in remaining.text and "protein" in remaining.text


def test_summarize_cluster_of_related_same_kind_facts(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "sem.sqlite")
    facts = [
        "Weekly orders to suppliers have a delivery lead time of 3 days.",
        "Weekly orders for suppliers use a delivery lead time of 3 days.",
        "Supplier weekly orders require a delivery lead time of 3 days.",
    ]
    for text in facts:
        store.upsert(text=text, kind="supplier_ordering", source="t")
    assert store.count() == 3
    report = consolidate_store(store)
    assert report.summarized_ids or report.deduplicated_ids
    # After consolidate, cluster collapses toward one fact.
    assert store.count() == 1
    summary = store.list_records()[0]
    assert "lead" in summary.text.casefold() or "weekly" in summary.text.casefold()
    if report.summary_ids:
        assert summary.source == "consolidation_summary"
        assert summary.metadata.get("consolidated") is True


def test_discard_low_relevance_when_over_cap(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(cons_mod, "MAX_SEMANTIC_FACTS", 5)
    monkeypatch.setattr(cons_mod, "SUMMARY_MIN_CLUSTER", 99)  # disable summarize
    monkeypatch.setattr(cons_mod, "DEDUP_JACCARD", 0.99)  # disable near-dedupe

    store = MemoryStore(tmp_path / "sem.sqlite")
    # Distinct allergen facts (low pairwise overlap) to fill past the cap.
    allergens = [
        "House Sauce contains soy and sulfites per the allergen catalog.",
        "Customer allergy protocol requires manager escalation for peanut reports.",
        "Gluten-free limitations apply to shared fryers in the kitchen.",
        "Dairy allergen labeling must follow the menu allergen sheet wording.",
        "Cross-contamination controls apply for nut allergens on the line.",
        "Soy allergen notes on House Sauce must stay as written in the catalog.",
        "Peanut protocol training is part of the customer allergy procedure.",
    ]
    for i, text in enumerate(allergens):
        store.upsert(
            text=text,
            kind="allergen",
            source="t",
            metadata={"access_count": 10 if i == 0 else 0},
        )
    assert store.count() == 7
    report = consolidate_store(store)
    assert store.count() <= 5
    assert report.discarded_low_relevance_ids
    # High-access fact should survive.
    texts = " ".join(r.text for r in store.list_records())
    assert "House Sauce contains soy" in texts


def test_write_triggers_consolidation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cons_mod, "MAX_SEMANTIC_FACTS", 3)
    monkeypatch.setattr(cons_mod, "SUMMARY_MIN_CLUSTER", 99)
    monkeypatch.setattr(cons_mod, "DEDUP_JACCARD", 0.99)

    memory = AgentMemory(MemoryStore(tmp_path / "sem.sqlite"))
    facts = [
        "Waste categories include spoilage and prep trim for daily logging.",
        "Daily logging of waste feeds escalation thresholds for operations.",
        "Operational targets for waste are reviewed against daily logging.",
        "Escalation thresholds for waste go to the operations director role.",
    ]
    last = None
    for text in facts:
        last = memory.write(text, source="test")
        assert last.ok
    assert last is not None
    assert last.consolidation is not None
    assert isinstance(last.consolidation, ConsolidationReport)
    assert memory._store.count() <= 3


def test_consolidation_docs_exist() -> None:
    doc = Path("docs/agent/MEMORY_CONSOLIDATION.md")
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "deduplicat" in text.casefold()
    assert "summar" in text.casefold()
    assert "low-relevance" in text.casefold() or "discard" in text.casefold()
    assert str(MAX_SEMANTIC_FACTS) in text or "MAX_FACTS" in text
