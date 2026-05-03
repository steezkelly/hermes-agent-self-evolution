**Reviewing a feature PR with bug detection**

(Input)
```
Review GitHub pull request #234 in repository octocat/Hello-World. The PR adds a new user authentication endpoint. Focus on logical bugs, error handling, and API contract violations.
```

(Output/Result)
```
PR Review Summary for #234: New User Authentication Endpoint

CRITICAL ISSUES:
- Line 47: Race condition in token generation - concurrent requests may receive duplicate tokens. Consider using atomic operations or adding database-level unique constraints.
- Line 89: Error message leaks internal implementation details ('psql connection pool exhausted'). Should return generic 'Service temporarily unavailable' to clients.

MODERATE ISSUES:
- Line 112: Missing input validation on email field - accepts malformed addresses like 'test@'. Add regex validation or use a validation library.
- Line 156: Inconsistent HTTP status codes - returns 200 for successful login but 201 for registration. Standardize to 200 for all success responses.


RECOMMENDATIONS:
- Line 78: Consider adding rate limiting to prevent brute-force attacks on /auth/login
- Add unit tests for edge cases: expired tokens, concurrent requests, database connection failures

✓ Inline comments posted to PR via GitHub API
```

---

**Security-focused review of dependency update PR**

(Input)
```
Review PR #567 in acme-corp/api-service that updates 5 npm packages to latest versions. Focus on security vulnerabilities, supply chain risks, and breaking changes that could introduce security issues.
```

(Output/Result)
```
Security Review for Dependencies PR #567

⚠️ HIGH RISK - Package: lodash@4.17.21
- Known prototype pollution vulnerability (CVE-2021-23337)
- Recommend upgrading to 4.17.22 or migrating to lodash-es

⚠️ MEDIUM RISK - Package: axios@1.6.0
- SSRF vulnerability if using default config
- Ensure axios requests are validated against allowlist
- Breaking change: removed 'proxy' option, verify proxy setup still works

✅ LOW RISK - Packages: express@4.18.2, jsonwebtoken@9.0.2, bcrypt@5.1.1
- No known vulnerabilities
- Breaking changes reviewed - no security implications

RECOMMENDATIONS:
- Add package-lock.json update to ensure reproducible builds
- Run npm audit after merging to confirm no transitive vulnerabilities

✓ Security findings commented on PR with references to CVEs and documentation
```


---

**Performance review of database query PR**
(Input)
```
Review PR #891 in data-pipeline/reporting-service. The PR modifies several database queries used in the weekly report generation. Focus on query performance, indexing, and N+1 query patterns.
```

(Output/Result)
```
Performance Review for Query Changes PR #891

🔥 N+1 QUERY PATTERN - Lines 23-45
- Loop at line 34 calls getUserMetrics() for each user
- With 10,000 users, this triggers 10,001 queries
- Recommended fix: Batch query with WHERE id IN (...) or use JOIN


🐌 MISSING INDEX - Line 67
- Query filters on 'created_at' and 'status' columns
- Table has 50M+ rows; full table scan detected
- Recommended: CREATE INDEX idx_report_created_status ON reports(created_at, status)

🐌 MISSING INDEX - Line 112
- JOIN on 'user_preferences' table without indexed column
- Estimated 2.3s per query at current scale
- Recommended: Add index on user_id column

✅ OPTIMIZED QUERIES:
- Line 78: Aggregation query now uses LIMIT effectively
- Line 145: Proper use of EXISTS vs IN for correlated subquery

RECOMMENDATIONS:
- Add EXPLAIN ANALYZE results to PR description for verification
- Consider caching report metadata since it changes weekly
- Estimated improvement: 15-20 seconds reduction in report generation time

✓ Performance findings posted with EXPLAIN output snippets as inline comments
```