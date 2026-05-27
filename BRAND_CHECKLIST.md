# Action 1 — Brand Claiming Checklist
## Complete these manually (Hours 0–4)

### Domains
- [ ] `racejudge.com` — primary domain (check Namecheap / Cloudflare Registrar)
- [ ] `racejudge.io` — backup
- [ ] `racejudge.app` — backup
- [ ] Set up Cloudflare DNS on whichever you register — free, fast, and needed for R2/Workers in Phase 1

### Social Handles
- [ ] `@racejudge` on **X / Twitter** — create account, add bio: "Every F1 stewards' decision, searchable. Coming soon."
- [ ] `@racejudge` on **Threads** (Meta) — mirror of X
- [ ] `@racejudge` on **Reddit** (u/racejudge) — reserve username
- [ ] `@racejudge` on **LinkedIn** — company page
- [ ] `@racejudge` on **Bluesky** — growing F1 community there

### GitHub
- [ ] Create GitHub organisation: `racejudge-hq` (private initially)
- [ ] Create repo: `racejudge-web` (private) — push this monorepo here
- [ ] Create repo: `racejudge-scraper` (public, MIT) — the FIA scraper open-source component
  - This is the goodwill seed: open-source the scraper to attract contributors and create backlinks
- [ ] Add description: "The Stewards' Precedent Engine — F1 stewarding decisions, searchable and explainable"
- [ ] Add topics: `formula1`, `f1`, `fia`, `nlp`, `stewarding`, `motorsport`, `python`

### Email
- [ ] Register `hello@racejudge.com` (Cloudflare Email Routing → Gmail, free)
- [ ] Register `legal@racejudge.com` — for DMCA/takedown notices
- [ ] Register `press@racejudge.com` — for journalist inquiries

### Trademark (do before launch, not urgent now)
- [ ] Search EUIPO + USPTO for "RACEJUDGE" — ensure no conflicting F1-adjacent trademark
- [ ] If clear: file in class 42 (Software as a service) — can be done around Phase 6

### Backup Name
If "RACEJUDGE" hits a trademark conflict:
- `PrecedentEngine.com` / `@precedentengine`
- `F1Stewards.com` / `@f1stewards`
- `StewardsDB.com` / `@stewardsdb`

---

## Quick wins while you have the tab open

After registering the domain, do these immediately:

1. **Point DNS to Cloudflare** — enables R2, Workers, and edge caching for free from day one
2. **Set up Cloudflare Email Routing** — `hello@`, `legal@`, `press@` all forward to your Gmail
3. **Enable DNSSEC** on the domain — one click in Cloudflare, good security hygiene

---

## Notes

- Do **not** announce publicly yet — reserve handles silently
- Set all accounts to private/limited until launch in Week 24
- The `racejudge-scraper` GitHub repo can go public in Week 1 as stated in the launch plan (seeds community trust)
