**Example 1: Identifying a missing null check in TypeScript**  
**Input:** A pull request adds `getUserDisplayName(user: User | null): string` that directly accesses `user.name` without null validation.  
**Output/Result:** The skill posts an inline comment on the `user.name` line: “Consider handling the null case – `user?.name ?? 'Anonymous'` prevents a potential runtime error.” It also adds a PR summary comment: “Found 1 null safety issue: missing check in `getUserDisplayName`”.

**Example 2: Finding a SQL injection vulnerability in Node.js**  
**Input:** A PR includes an API route that builds a query with `SELECT * FROM users WHERE id = ${req.query.id}`.  
**Output/Result:** The skill posts an inline comment with severity **critical**: “Use parameterized queries (e.g., `?` placeholder) or an ORM to prevent SQL injection. See OWASP A03:2021.” A PR‑level comment adds: “1 security vulnerability detected – SQL injection in `/users/:id`.”

**Example 3: Spotting an N+1 query in Rails**  
**Input:** A view controller iterates `User.all.each { |u| u.orders.recent }`, causing a separate query per user.  
**Output/Result:** The skill comments on that line: “Eager load orders with `User.includes(:orders)` to eliminate N+1 – reduces database calls from O(N) to O(1).” A performance note is added to the PR: “N+1 query detected in `UsersController#index`.”