Haan—ab tak humne **Assurely ka health-insurance advisory MVP** kaafi had tak build kiya hai. Iska core idea hai: **LLM ko samjhaane aur user ki baat samajhne do; policy ke pakke facts, calculations aur routing deterministic code se control karo.**

### System architecture

```
This Mermaid diagram uses features the terminal renderer doesn't support.
flowchart LR
    U["User<br/>Web chat"] --> FE["Next.js frontend<br/>Comparison, policy detail, theme"]
    FE --> API["FastAPI v1<br/>Message, consent, session APIs"]
    API --> AUTH["Auth + request boundary<br/>Verified JWT where required<br/>Correlation IDs, rate limits"]
    AUTH --> GRAPH["LangGraph orchestration<br/>State + deterministic routing"]

    GRAPH --> INTAKE["Validate + intake<br/>Collect missing profile fields"]
    INTAKE --> ROUTER["Intent router"]
    ROUTER -->|health| FAN["Parallel health analysis"]
    ROUTER -->|life / unclear| SCOPE["Deferred or clarification path"]

    FAN --> HEALTH["Health domain agent<br/>Clause explanations"]
    FAN --> RISK["Risk analysis<br/>Deterministic calculator"]
    HEALTH --> VERIFY["compare_verify<br/>Policy facts + evidence"]
    RISK --> VERIFY
    VERIFY --> GUARD["guardrail<br/>Compliance and provenance checks"]
    GUARD --> REPORT["explanation_report<br/>Writes sourced output"]
    REPORT --> ESC["escalate<br/>Advisor notification + delivery hold"]
    ESC --> PERSIST["persist_memory<br/>Decision trace every turn"]
    SCOPE --> PERSIST

    PERSIST --> GATE["API delivery gate<br/>Redacts held response fields"]
    GATE --> FE

    VERIFY --> PG["Postgres<br/>policy_terms, sessions,<br/>decision_trace, consent"]
    HEALTH --> CHROMA["Chroma<br/>Policy-clause retrieval"]
    CHROMA --> SCREEN["Ingestion screening<br/>Before vector-store admission"]
    GRAPH --> LLM["LLM fallback chain<br/>Configured providers"]
    GRAPH --> LF["Langfuse<br/>Sanitized traces"]
    API --> ERR["Restricted exception sink<br/>Sanitized diagnostics"]
```

### Is design ko kaise samjhein

- **Frontend** user se conversation leta hai aur comparison/policy-detail jaise screens dikhata hai. Yeh Next.js frontend scaffold aur major UI flows ke saath bana hua hai.
- **FastAPI** frontend aur backend ke beech API layer hai. Message, session aur consent-related endpoints yahan hain. Protected profile-memory operations verified JWT maangte hain; identity provider configure na ho to woh fail closed hote hain.
- **LangGraph** conversation ka workflow chalata hai. Kaunsa node agla chalega, yeh explicit state aur deterministic code decide karte hain—LLM nahi.
- **Intake aur intent routing** profile ke missing fields identify karte hain aur request ko health, deferred ya clarification path par bhejte hain.
- **Health analysis aur risk calculation** parallel chal sakte hain. Clause explanation ke liye retrieval use hota hai; age, limits, premium ya eligibility jaise ek sahi jawab wale facts ko database/rules se lena chahiye.
- **compare\_verify** retrieved evidence aur policy terms ko milata hai. **guardrail** provenance/compliance check karta hai. **explanation\_report** sourced report banata hai.
- **escalate** advisor notification aur delivery hold handle karta hai. Report generate hona aur user ko report dena alag controls hain: hold active ho to API sensitive output release nahi kare.
- **persist\_memory** har turn ka operational decision trace store karta hai; family/profile memory alag hai aur consent ke bina save nahi honi chahiye.
- **Exception sink** normal application logs se alag restricted destination hai. Ab free-form error messages redact hote hain; sirf limited structured diagnostics rakhe jaate hain.

### Data kahan jaata hai

| Store/service | Kaam |
|---|---|
| **Postgres** | Policy ke deterministic terms, sessions, consent, decision traces aur consent-gated profile memory |
| **Chroma** | Policy clauses aur wording ke liye vector retrieval |
| **Langfuse** | AI workflow ki sanitized tracing/observability |
| **Restricted exception sink** | Debugging ke liye sanitized exception class, stack locations aur correlation identifiers |

Policy ke numeric terms aur retrieval ko mix nahi karna important hai: **exact policy number database se, clause ki wording/explanation retrieval se.**

### Abhi tak complete kiya hua kaam

Phase 1 ke main workflow nodes—intent routing, health analysis, risk analysis, comparison verification, guardrail, explanation report, escalation aur persistence—implement aur tests ke through verify kiye gaye hain. Frontend bhi scaffolded hai.

Latest maintenance mein:

- `GET /v1/session/{id}` ko wahi delivery gate diya jo `/v1/message` use karta hai. Hold ke dauran citations aur calculator outputs empty rehte hain.
- API test POST se held session banata hai, phir GET karke check karta hai ki woh data wapas nahi aata. Har hold condition ka separate test bhi hai.
- Exception scrubbing ka root cause mila: allowlisted exceptions pehle profile-message scrubber ko skip kar sakte the; nested profile fields bhi collect nahi ho rahe the. Ab nested values scrub hote hain aur arbitrary free-form exception text redact hota hai.
- Postgres par depend karne wala exception test synthetic SQLAlchemy error use karta hai, taaki test environment ke database par nirbhar na ho.
- Backend suite **255 tests pass**, targeted suite **28 tests pass**, aur Ruff checks pass hue.

### Abhi jo pending hai

**Correlation clarification abhi unresolved hai:** `screen_document()` apne andar `correlation_scope()` nahi banata. Main application middleware request ke dauran correlation scope banata hai, lekin screening filhaal `ingest_document()` aur vector-store seeding jaise direct paths se bhi call ho sakti hai. Isliye standalone call mein request ka `session_id` nahi hota; naya trace ID scope abhi screening khud create nahi karti. Is path ko correlation scope dena aur test karna abhi baaki hai.

Pehle ke independent reviewer ka process review result nahi de saka. Aapke kehne par us reviewer ko dobara try kiya gaya; woh attempt bhi complete review ke bina ruk gaya. Isliye delivery-hold aur exception-privacy fixes ko **independently confirmed/closed nahi** keh raha hoon. Aapne kaha hai ki same reviewer ke process ki repeated failure ko batakar teesri koshish se pehle rukna hai, isliye abhi teesri koshish nahi ki gayi.

Aapke review ke baad hi ingestion integrity items par jaana hai: PDF hash mismatch aur quarantine permissions/reload. Chroma fallback aur retrieved version-hash waale alag findings bhi deferred hain. Confidence score abhi heuristic hai, calibrated probability nahi; production advisor destination aur policy/calculator source verification bhi pending hain. Stage 5 par aage ka kaam review ke baad hi hona chahiye.