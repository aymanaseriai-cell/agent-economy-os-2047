# Security and limits

**Do not disclose secrets or personal information in public issues.** When available, use GitHub's private vulnerability reporting feature for responsible disclosure. This project performs read-only metadata checks on public GitHub repositories and offline SHA-256 digest comparisons; it does not execute third-party code.

Matching a digest does not prove that an AI agent performed a task, that the manifest is authentic, that the produced result is accurate, or that a repository is secure. The readiness score checks only the *presence* of a few public repository practices.

Never put GitHub tokens, bank details or API credentials in this repository. Built-in Actions GITHUB_TOKEN is used for public-issue responses and has the minimum workflow permissions needed.
