#!/usr/bin/env python3
"""
Review the Elara Protocol whitepaper using qwen2.5:32b.

Splits the paper into chunks, runs each through the model with a
critical reviewer prompt, saves individual + combined review.
"""

import re, json, time, os, sys
from datetime import datetime
from daemon.llm import _api_call, is_available
import daemon.llm as llm_mod

# Force fresh Ollama check
llm_mod._last_check = 0

if not is_available():
    print("ERROR: Ollama not available!")
    sys.exit(1)

print(f"[{datetime.now().strftime('%H:%M:%S')}] Ollama OK — starting whitepaper review")

# Read whitepaper
WP_PATH = os.path.expanduser("~/Desktop/ELARA-PROTOCOL-WHITEPAPER.md")
with open(WP_PATH) as f:
    text = f.read()

# Split into sections
sections = re.split(r'\n(?=## \d)', text)

# Group into review chunks (~12K chars each, except section 11 which gets split)
chunks = []
current = ""
current_titles = []

for i, s in enumerate(sections):
    first_line = s.strip().split('\n')[0][:80]

    if len(s) > 15000:
        if current:
            chunks.append({"text": current, "titles": current_titles})
            current = ""
            current_titles = []

        subsections = re.split(r'\n(?=### \d)', s)
        sub_chunk = ""
        sub_titles = [first_line]
        for sub in subsections:
            sub_first = sub.strip().split('\n')[0][:60]
            if len(sub_chunk) + len(sub) > 12000 and sub_chunk:
                chunks.append({"text": sub_chunk, "titles": sub_titles})
                sub_chunk = sub
                sub_titles = [first_line + " (cont.)", sub_first]
            else:
                sub_chunk += "\n" + sub
                if sub_first not in sub_titles:
                    sub_titles.append(sub_first)
        if sub_chunk:
            chunks.append({"text": sub_chunk, "titles": sub_titles})
    else:
        if len(current) + len(s) > 12000 and current:
            chunks.append({"text": current, "titles": current_titles})
            current = s
            current_titles = [first_line]
        else:
            current += "\n" + s
            current_titles.append(first_line)

if current:
    chunks.append({"text": current, "titles": current_titles})

print(f"Chunks: {len(chunks)}")
for i, c in enumerate(chunks):
    print(f"  Chunk {i+1}: {len(c['text']):,} chars — {', '.join(c['titles'][:3])}")

# Output dir
out_dir = os.path.expanduser("~/.claude/overnight/whitepaper-review")
os.makedirs(out_dir, exist_ok=True)

SYSTEM = """You are a senior protocol reviewer with deep expertise in distributed systems, \
cryptography, and blockchain architecture. You are reviewing a whitepaper for the \
"Elara Protocol" — a post-quantum universal validation layer for digital work.

Your job is to be brutally honest. Find:
1. **Technical errors** — wrong algorithms, impossible claims, math that doesn't work
2. **Logical gaps** — assumptions that aren't justified, steps that are hand-waved
3. **Overclaims** — things stated as facts that are actually aspirational
4. **Missing details** — things that would need to be specified for implementation
5. **Strengths** — what's genuinely novel or well-designed

Be specific. Quote the exact text that has issues. Rate severity: CRITICAL / HIGH / MEDIUM / LOW."""

all_reviews = []
total_start = time.time()

# Resume support: skip already-completed chunks
SKIP_TO = int(os.environ.get("RESUME_FROM", "1"))  # 1-indexed, default=start from beginning

for i, chunk in enumerate(chunks):
    chunk_num = i + 1
    if chunk_num < SKIP_TO:
        # Load existing review if available
        existing = os.path.join(out_dir, f"chunk-{chunk_num:02d}.json")
        if os.path.exists(existing):
            with open(existing) as f:
                all_reviews.append(json.load(f))
            print(f"  [SKIP] Chunk {chunk_num} — loaded from cache")
        continue

    section_names = ', '.join(chunk['titles'][:2])
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Chunk {chunk_num}/{len(chunks)}: {section_names}")
    sys.stdout.flush()

    prompt = f"""Review this section of the Elara Protocol whitepaper:

{chunk['text'][:12000]}

Provide your review with specific findings. For each issue:
- Quote the relevant text
- Explain the problem
- Rate severity (CRITICAL/HIGH/MEDIUM/LOW)
- Suggest a fix if possible

End with a brief "Strengths" section for anything genuinely well-done."""

    start = time.time()
    result = _api_call("/api/generate", {
        "model": "qwen2.5:32b",
        "prompt": prompt,
        "system": SYSTEM,
        "stream": False,
        "options": {
            "temperature": 0.4,
            "num_predict": 2048,
            "num_ctx": 16384,
        },
    }, timeout=900)
    elapsed = time.time() - start

    if result and "response" in result:
        output = result["response"].strip()
        tokens = result.get("eval_count", 0)
        tok_s = tokens / elapsed if elapsed > 0 else 0
        print(f"  Done: {elapsed:.0f}s, {len(output):,} chars, {tokens} tokens ({tok_s:.1f} tok/s)")

        review = {
            "chunk": i+1,
            "sections": chunk["titles"],
            "review": output,
            "duration_s": round(elapsed, 1),
            "tokens": tokens,
        }
        all_reviews.append(review)

        path = os.path.join(out_dir, f"chunk-{i+1:02d}.json")
        with open(path, "w") as f:
            json.dump(review, f, indent=2)
        print(f"  Saved → chunk-{i+1:02d}.json")
    else:
        print(f"  FAILED — no response after {elapsed:.0f}s")
        all_reviews.append({"chunk": i+1, "sections": chunk["titles"], "review": "FAILED", "duration_s": 0})

    sys.stdout.flush()

total_elapsed = time.time() - total_start
print(f"\n=== REVIEW COMPLETE ===")
print(f"Total time: {total_elapsed/60:.1f} minutes")
print(f"Chunks reviewed: {len([r for r in all_reviews if r['review'] != 'FAILED'])}/{len(all_reviews)}")

# Count issues by severity
all_text = " ".join(r["review"] for r in all_reviews)
for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
    count = all_text.upper().count(sev)
    if count:
        print(f"  {sev}: ~{count} mentions")

# Write combined review
combined_path = os.path.join(out_dir, "full-review.md")
with open(combined_path, "w") as f:
    f.write(f"# Whitepaper Review — qwen2.5:32b\n\n")
    f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    f.write(f"*Chunks reviewed: {len(all_reviews)}*\n")
    f.write(f"*Total time: {total_elapsed/60:.1f} minutes*\n\n")
    for r in all_reviews:
        f.write(f"---\n\n")
        f.write(f"## Chunk {r['chunk']}: {', '.join(r['sections'][:2])}\n\n")
        f.write(r["review"] + "\n\n")

print(f"\nFull review → {combined_path}")
