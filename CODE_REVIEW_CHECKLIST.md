# Code review checklist — apply to any diff, regardless of which tool wrote it

Quick yes/no pass before accepting a change. Takes two minutes; catches the mistakes that are expensive to find later.

- [ ] Does this add a new LLM call inside something that should be deterministic routing?
- [ ] Does this write to `output` from anywhere other than `explanation_report`?
- [ ] Does any user-facing string contain "rank," "best," or "top"?
- [ ] Does anything here compute a number (premium, eligibility, sum insured) via an LLM instead of a `policy_terms` lookup?
- [ ] Does every claim in the output have a matching entry in `sources_per_claim`?
- [ ] Does this touch the state schema or the node graph's edges? If yes — stop, check against `tech-stack-hld-lld.md` yourself before accepting, regardless of how confident the tool sounds.
- [ ] Do the eval cases still pass?
- [ ] Was `PROGRESS.md` updated before this session ended?
