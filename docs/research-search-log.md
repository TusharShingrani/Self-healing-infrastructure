# Literature search log

Date: 14 October 2026. This log makes the structured search traceable. It is not
a PRISMA screening flow or a count of every search-engine hit. The synthesis
includes 21 source entries, distinguishing full papers, abstracts, operational
guidance and specifications. Publication dates were taken from primary pages,
not relative search-result dates. The cutoff is this research date.

Representative queries actually used:

- self healing systems survey autonomic computing Kephart Chess 2003 vision autonomic computing
- site.usenix.org OSDI 2020 gray failures cloud systems repair metastable failures
- site.usenix.org "Gray Failure" differential observability
- site.microsoft.com research "Narya" predictive proactive failure mitigation
- site.usenix.org "Gandalf" deployment
- site.usenix.org "Predictive and Adaptive Failure Mitigation"
- site.sre.google workbook eliminating toil monitoring distributed systems automation simplicity
- site.arxiv.org AIOpsLab 2024 holistic evaluation autonomous agents
- site.usenix.org "Simple Testing Can Prevent" critical failures
- site.kubernetes.io docs concepts self-healing liveness readiness startup probes
- site.redis.io docs maxmemory noeviction OOM configuration
- site.freedesktop.org systemd.service Restart Watchdog MemoryMax CPUQuota
- site.usenix.org "Microreboot" Candea 2004
- site.arxiv.org "CHESS" "self-adaptive" 2303.07283
- site.usenix.org/conference "LLM" "self-healing" 2025 2026
- site.usenix.org/conference/usenixsecurity26 "AIOpsShield"
- "Verify, Augment, Improve" "Self-Adaptation"

Included: original studies with a relevant recovery, learning or evaluation
mechanism; primary publication pages; official documentation of mechanisms used
in the lab. Excluded as evidence: reposts, generic product marketing, unrelated
self-healing test selectors, secondary summaries, and headline accuracy without
an identifiable primary study. New preprints were retained as research context,
not treated as validated production evidence.

Full-paper sections inspected included Narya's safeguards and production
evaluation, metastable failure mechanisms and mitigation, AIOpsLab task-level
results and limitations, CHESS architecture/evaluation, and AIOpsDoom's threat
model and defence boundaries. PASE and IFSHM manuscript HTML was inspected.
The VAI repository abstract and conference metadata were available, but its
publisher PDF timed out. The low-parameter SEAMS study was assessed from the
conference abstract only. These access limits are explicitly recorded in the
synthesis. No inaccessible full paper is represented as fully reviewed.

Do not compare the 59.32% AIOpsLab result with the 96.67% SEAMS abstract result
as if they shared a dataset, task definition or success criterion. Do not
transfer Narya's production improvement to this lab. The lab measurements are
stored separately and only support claims about this controlled environment.
