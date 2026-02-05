# Elara Future Upgrades (Nice to Have, Don't Ship Products)

Saved: 2026-02-05. Build these AFTER revenue projects are shipping.

## 1. Memory Consolidation (Dream Mode)
- Batch process that finds patterns across memories
- "You always drift into philosophy after midnight"
- "HandyBill stalls when PlanPulse gets attention"
- Run: on demand or at session end, NOT cron
- Input: last 50-100 memories + last 5 episodes
- Output: insights.json

## 2. Self-Reflection Tool (elara_reflect)
- Meta-analysis of own patterns, corrections, mood correlations
- What topics dominate, what corrections repeat, what mood = best work
- Generates self-report monthly
- Run: on demand during conversation

## 3. Narrative Threading
- Connect episodes into story arcs spanning multiple sessions
- Auto-group by overlapping projects and related milestones
- Each thread gets a living summary
- "The Architecture Evolution" = sessions 22-33
- "The Medium Story" = sessions 7-9, 23

## Token Cost Notes
- These don't need cron or background jobs
- Just run them during a conversation when it's time
- Layer 1+2 (goals, corrections, dev mode) ship products
- Layer 3 (these) improve self-awareness. Build later.
