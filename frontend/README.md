# Assurely frontend

Next.js application with the existing light/dark design and connected health-cover workspaces.

- `/workspace`: questions, selected policy context, durable case status, recovery and reviewed release.
- `/advisor`: authorized independent report review, approval, expiry and revocation.
- `/sign-in` and `/sign-up`: Clerk account flows, with profile/sign-out controls.
- `/intake`: controlled guided questions, explicit processing consent receipt and actual case submission.
- `/comparison`: owner-only current report lookup and fresh sourced release.
- `/handoff`: actual turn/report status without fabricated contact promises.
- Workspace privacy controls: explicit consent grant/revoke and confirmed saved-profile deletion.

Run `npm ci` and `npm run dev`. Configure Clerk using the [operator guide](../docs/clerk-authentication.md); never add secrets to Git. The frontend calls its own `/api/backend` gateway, which obtains a Clerk session token per request. FastAPI independently verifies that token and maps its subject to a stable local UUID. Every owner, advisor and report-release check remains enforced. The previous encrypted-cookie OIDC flow is available only through the explicit `legacy_oidc` rollback switch.

`npm run build`, `npx tsc --noEmit` and ESLint validate the application. The repository browser journey script exercises the synthetic HTTPS identity provider, actual backend graph/release operations and dark mobile layout. It does not approve real policies or certify a live deployment.

Full setup, test constraints and remaining external approvals: [release gates](../docs/release-gates.md).
API coverage, runtime validation, negative/race tests and deliberately separate
operator APIs: [frontend integration audit](../docs/frontend-api-integration.md).
Run `npm run test:contracts` for transport/contract and mocked Clerk/Next boundary checks.
Real Clerk account E2E requires configured provider credentials and is not implied
by mocked tests. Voice remains separate future work and cannot replace human review.

For the existing `assurely.shubair.in` Vercel deployment and proposed Back4App
backend, use the [deployment guide](../docs/production-deployment.md) and
`deploy/vercel.env.example`. The backend gateway requires its server-only shared
key in production and uses a 150-second function budget with a 120-second upstream
deadline. Live identity/hosting configuration still needs verification.
