# Deployment and monetization activation

This repository began empty on 2026-11-07. The starter is packaged as source files; uploading a `.zip` itself to GitHub **does not install/unpack** the project. After connecting write access or using git locally, commit the extracted folder **including the hidden `.github/` directory** to branch `main`.

## 1. Push from local git (if GitHub integration is not authorized)

Extract the package, then in a terminal on Windows / macOS / Linux / Termux:

```sh
cd agent-economy-github-starter
git init
git branch -M main
git add .
git commit -m "Launch Agent Economy OS 2047 automated GitHub checks"
git remote add origin https://github.com/aymanaseriai-cell/agent-economy-os-2047.git
git push -u origin main
```

GitHub will require authentication for pushing. Use your own GitHub sign-in / credential manager. **Do not share your GitHub token or password in chat.** If the remote is already initialized, clone it first and copy in these files to avoid a non-fast-forward push.

## 2. Required repository settings

- Repository Settings → Actions → General: Allow relevant Actions; workflow permissions must permit the `issue-router.yml` workflow to write issue comments. The workflow explicitly grants `issues: write`.
- Settings → General: enable GitHub Issues if necessary.
- In Actions, inspect the `Test and verify` run. It should pass all unit tests and sample evidence checks.
- Open a free issue with a **public** repo URL. Verify the `Automatic inbound repo checks` workflow posts an automated response; do not publish secrets or private data.
- For the website, Settings → Pages → Deploy from branch → `main` → `/docs`. GitHub Pages may require appropriate plan/eligibility.

## 3. Funding, sales and payment reality

- Apply for GitHub Sponsors separately. Only **after approval** copy `FUNDING.example.yml` to `.github/FUNDING.yml` and put `github: [aymanaseriai-cell]` in it. Sponsors registration, banking/identity/tax verification cannot be done by code in the repo.
- Public GitHub Issue Forms can collect **leads**, not customer payments. The service quote is indicative and requires negotiation and a legally workable payment channel.
- A hosted subscription checkout is **not built or live**. Implement billing, purchase verification, and customer authentication before asserting that orders are 100% automatic.

## 4. Safety and operating limits

- No user API keys are included or needed for the free workflow.
- GitHub Actions schedules are best-effort; timings and free API quotas are not guaranteed.
- The daily opportunity report is a downloadable workflow artifact, not outreach or a verified customer pipeline.
- No bot auto-comments on unrelated third-party repositories.
