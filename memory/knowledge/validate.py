# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Knowledge Graph Validation — Cross-document gap and contradiction detection.

Sub-validators:
  - find_contradictions() — same semantic_id with conflicting definitions across docs
  - find_gaps() — concept referenced but not defined (the "Layer 1.5" problem)
  - find_stale_references() — references to superseded versions
  - find_metric_conflicts() — same metric, different values across docs
"""

import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional

from .store import KnowledgeStore

logger = logging.getLogger("elara.knowledge.validate")


# ============================================================================
# Sub-validators
# ============================================================================

MAX_DOC_IDS = 100  # Guard against SQL placeholder DoS


def find_contradictions(store: KnowledgeStore, doc_ids: Optional[List[str]] = None) -> List[Dict]:
    """
    Find same semantic_id with conflicting definitions across documents.

    A contradiction = same concept defined differently in two docs.
    Uses both SQLite exact matching and ChromaDB similarity.
    """
    contradictions = []
    db = store._db()

    # Get all definitions, optionally filtered by doc
    if doc_ids:
        if len(doc_ids) > MAX_DOC_IDS:
            raise ValueError(f"doc_ids limit exceeded: {len(doc_ids)} > {MAX_DOC_IDS}")
        placeholders = ",".join("?" * len(doc_ids))
        rows = db.execute(
            f"SELECT * FROM nodes WHERE type = 'definition' AND source_doc IN ({placeholders})",
            doc_ids,
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM nodes WHERE type = 'definition'").fetchall()

    # Group definitions by semantic_id
    by_semantic = defaultdict(list)
    for row in rows:
        row = dict(row)
        by_semantic[row["semantic_id"]].append(row)

    # Check for cross-document definition conflicts
    for semantic_id, defs in by_semantic.items():
        # Group by source_doc
        by_doc = defaultdict(list)
        for d in defs:
            by_doc[d["source_doc"]].append(d)

        # Only flag when a concept is defined in multiple docs
        if len(by_doc) < 2:
            continue

        docs = list(by_doc.keys())
        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                doc_a, doc_b = docs[i], docs[j]
                defs_a = by_doc[doc_a]
                defs_b = by_doc[doc_b]

                # Compare content for conflicts
                for da in defs_a:
                    for db_item in defs_b:
                        if da["content"] and db_item["content"]:
                            # Simple heuristic: if content is substantially different
                            content_a = da["content"].lower().strip()
                            content_b = db_item["content"].lower().strip()
                            if content_a != content_b:
                                # Use semantic similarity if available
                                similarity = _text_similarity(content_a, content_b)
                                if similarity < 0.85:  # different enough to flag
                                    contradictions.append({
                                        "type": "definition_conflict",
                                        "semantic_id": semantic_id,
                                        "doc_a": doc_a,
                                        "doc_b": doc_b,
                                        "content_a": da["content"],
                                        "content_b": db_item["content"],
                                        "line_a": da.get("source_line"),
                                        "line_b": db_item.get("source_line"),
                                        "section_a": da.get("source_section"),
                                        "section_b": db_item.get("source_section"),
                                        "similarity": round(similarity, 4),
                                        "confidence": max(da["confidence"], db_item["confidence"]),
                                    })

    return contradictions


def find_gaps(store: KnowledgeStore, doc_ids: Optional[List[str]] = None) -> List[Dict]:
    """
    Find concepts referenced but never defined — the "Layer 1.5" problem.

    A gap = a reference node exists for a semantic_id, but no definition
    node exists in any of the indexed documents.
    """
    gaps = []
    db = store._db()

    # Get all references
    if doc_ids:
        if len(doc_ids) > MAX_DOC_IDS:
            raise ValueError(f"doc_ids limit exceeded: {len(doc_ids)} > {MAX_DOC_IDS}")
        placeholders = ",".join("?" * len(doc_ids))
        refs = db.execute(
            f"SELECT * FROM nodes WHERE type = 'reference' AND source_doc IN ({placeholders})",
            doc_ids,
        ).fetchall()
    else:
        refs = db.execute("SELECT * FROM nodes WHERE type = 'reference'").fetchall()

    # Get all definitions
    all_defs = db.execute("SELECT DISTINCT semantic_id FROM nodes WHERE type = 'definition'").fetchall()
    defined_ids = {r["semantic_id"] for r in all_defs}

    # Also check aliases — a reference might match a definition through an alias
    all_aliases = db.execute("SELECT semantic_id, alias FROM aliases").fetchall()
    alias_to_canonical = {}
    for row in all_aliases:
        alias_to_canonical[row["alias"]] = row["semantic_id"]

    # Group references by semantic_id
    ref_groups = defaultdict(list)
    for row in refs:
        row = dict(row)
        ref_groups[row["semantic_id"]].append(row)

    for semantic_id, ref_list in ref_groups.items():
        # Check if defined directly or through alias
        is_defined = semantic_id in defined_ids

        if not is_defined:
            # Check aliases
            canonical = alias_to_canonical.get(semantic_id)
            if canonical and canonical in defined_ids:
                is_defined = True

        if not is_defined:
            # Also check if the semantic_id itself is an alias for something defined
            for alias_row in all_aliases:
                if alias_row["alias"] == semantic_id and alias_row["semantic_id"] in defined_ids:
                    is_defined = True
                    break

        if not is_defined:
            # This concept is referenced but never defined — it's a gap
            ref_docs = list({r["source_doc"] for r in ref_list})
            gaps.append({
                "type": "undefined_reference",
                "semantic_id": semantic_id,
                "referenced_in": ref_docs,
                "reference_count": len(ref_list),
                "first_reference": {
                    "doc": ref_list[0]["source_doc"],
                    "section": ref_list[0].get("source_section"),
                    "line": ref_list[0].get("source_line"),
                    "content": ref_list[0].get("content", "")[:120],
                },
                "confidence": max(r["confidence"] for r in ref_list),
            })

    return gaps


def find_stale_references(store: KnowledgeStore, doc_ids: Optional[List[str]] = None) -> List[Dict]:
    """
    Find references to superseded versions within the same document family.

    Only flags when a doc references an older version of *itself* — e.g.,
    Protocol WP v0.2.8 mentioning "v0.2.7" is stale. But Protocol WP
    referencing "Hardware WP v0.1.4" is intentional cross-doc reference.
    """
    stale = []
    db = store._db()

    # Get all indexed documents with versions and paths
    docs = db.execute("SELECT doc_id, version, path FROM documents").fetchall()

    # Build doc family map: strip version suffixes to group related docs
    # e.g. "elara_protocol_whitepaper" and "elara_protocol_whitepaper_v0_2_7" are same family
    families = {}  # family_base → {version: doc_id, ...}
    for d in docs:
        did = d["doc_id"]
        ver = d["version"]
        # Strip version suffix from doc_id to get family
        base = re.sub(r"_v\d+_\d+_\d+$", "", did)
        if base not in families:
            families[base] = {}
        families[base][ver] = did

    # For each family, find the latest version
    family_latest = {}
    for base, versions in families.items():
        latest = max(versions.keys(), key=lambda v: [int(x) for x in v.lstrip("v").split(".")])
        family_latest[base] = latest

    # Build reverse map: doc_id → family base
    doc_to_family = {}
    for base, versions in families.items():
        for ver, did in versions.items():
            doc_to_family[did] = base

    # Find version references that are stale within their own doc family
    version_re = re.compile(r"v(\d+\.\d+\.\d+)")
    if doc_ids:
        if len(doc_ids) > MAX_DOC_IDS:
            raise ValueError(f"doc_ids limit exceeded: {len(doc_ids)} > {MAX_DOC_IDS}")
        placeholders = ",".join("?" * len(doc_ids))
        refs = db.execute(
            f"SELECT * FROM nodes WHERE type = 'reference' AND source_doc IN ({placeholders})",
            doc_ids,
        ).fetchall()
    else:
        refs = db.execute("SELECT * FROM nodes WHERE type = 'reference'").fetchall()

    for row in refs:
        row = dict(row)
        content = row.get("content", "")
        source_doc = row["source_doc"]
        source_family = doc_to_family.get(source_doc, source_doc)

        for m in version_re.finditer(content):
            ref_ver = m.group(0)
            # Only flag if this version is for the same document family
            # and is older than the latest version of that family
            latest = family_latest.get(source_family)
            if latest and _version_gt(latest, ref_ver) and ref_ver != latest:
                stale.append({
                    "type": "stale_version_reference",
                    "referenced_version": ref_ver,
                    "latest_version": latest,
                    "doc_family": source_family,
                    "found_in": source_doc,
                    "section": row.get("source_section"),
                    "line": row.get("source_line"),
                    "content": content[:120],
                })

    return stale


def find_metric_conflicts(store: KnowledgeStore, doc_ids: Optional[List[str]] = None) -> List[Dict]:
    """
    Find same metric with different values across documents.
    """
    conflicts = []
    db = store._db()

    if doc_ids:
        if len(doc_ids) > MAX_DOC_IDS:
            raise ValueError(f"doc_ids limit exceeded: {len(doc_ids)} > {MAX_DOC_IDS}")
        placeholders = ",".join("?" * len(doc_ids))
        metrics = db.execute(
            f"SELECT * FROM nodes WHERE type = 'metric' AND source_doc IN ({placeholders})",
            doc_ids,
        ).fetchall()
    else:
        metrics = db.execute("SELECT * FROM nodes WHERE type = 'metric'").fetchall()

    # Group by semantic_id
    by_semantic = defaultdict(list)
    for row in metrics:
        row = dict(row)
        by_semantic[row["semantic_id"]].append(row)

    # Check for cross-document conflicts
    for semantic_id, metric_list in by_semantic.items():
        by_doc = defaultdict(list)
        for m in metric_list:
            by_doc[m["source_doc"]].append(m)

        if len(by_doc) < 2:
            continue

        docs = list(by_doc.keys())
        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                doc_a, doc_b = docs[i], docs[j]
                for ma in by_doc[doc_a]:
                    for mb in by_doc[doc_b]:
                        # Extract numbers from content
                        nums_a = re.findall(r"(\d+(?:\.\d+)?)", ma.get("content", ""))
                        nums_b = re.findall(r"(\d+(?:\.\d+)?)", mb.get("content", ""))
                        if nums_a and nums_b and nums_a[0] != nums_b[0]:
                            conflicts.append({
                                "type": "metric_conflict",
                                "semantic_id": semantic_id,
                                "doc_a": doc_a,
                                "doc_b": doc_b,
                                "value_a": nums_a[0],
                                "value_b": nums_b[0],
                                "content_a": ma.get("content", "")[:120],
                                "content_b": mb.get("content", "")[:120],
                                "line_a": ma.get("source_line"),
                                "line_b": mb.get("source_line"),
                            })

    return conflicts


# ============================================================================
# Main validation function
# ============================================================================

def validate_corpus(
    store: KnowledgeStore,
    doc_ids: Optional[List[str]] = None,
) -> Dict:
    """
    Run all validators across the corpus.

    Returns:
        {contradictions, gaps, stale_refs, metric_conflicts, summary}
    """
    contradictions = find_contradictions(store, doc_ids)
    gaps = find_gaps(store, doc_ids)
    stale_refs = find_stale_references(store, doc_ids)
    metric_conflicts = find_metric_conflicts(store, doc_ids)

    total_issues = len(contradictions) + len(gaps) + len(stale_refs) + len(metric_conflicts)

    summary = {
        "total_issues": total_issues,
        "contradictions": len(contradictions),
        "gaps": len(gaps),
        "stale_references": len(stale_refs),
        "metric_conflicts": len(metric_conflicts),
        "status": "clean" if total_issues == 0 else "issues_found",
    }

    return {
        "contradictions": contradictions,
        "gaps": gaps,
        "stale_refs": stale_refs,
        "metric_conflicts": metric_conflicts,
        "summary": summary,
    }


# ============================================================================
# Helpers
# ============================================================================

def _text_similarity(a: str, b: str) -> float:
    """Simple Jaccard similarity between word sets."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def _version_gt(a: str, b: str) -> bool:
    """Compare semver strings. Returns True if a > b."""
    try:
        va = [int(x) for x in a.lstrip("v").split(".")]
        vb = [int(x) for x in b.lstrip("v").split(".")]
        return va > vb
    except (ValueError, AttributeError):
        return False
