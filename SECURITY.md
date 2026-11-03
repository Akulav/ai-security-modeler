# Security policy

This app holds a map of how your accounts could be attacked, so please treat that data as sensitive.

## Reporting a problem

Please report vulnerabilities through [GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-security-vulnerabilities/privately-reporting-a-security-vulnerability) on this repository, not in a public issue. Don't include real account data in a report.

## What's protected

- **Network access:** the server binds to `127.0.0.1` only. `Host` header checks and restricted CORS stop other websites from reaching it through your browser.
- **Secrets:** the HaveIBeenPwned key stays on the backend. The app has no field for passwords.
- **The LLM:** it sees masked data, and its web queries are blocked if they contain your addresses. Web results are labelled as untrusted in its prompts.
- **Downloads:** Ollama runtime archives are checked against the checksums published with the release.
- **Rendering:** model and breach text is treated as plain text in the app and escaped in the PDF.

## Known limits

- **No login:** any program running on your computer can reach the API. Don't expose it with a proxy or port forward.
- **No encryption at rest:** `data/modeler.db`, its backups and exports are readable by anyone with file access. Use disk encryption.
- **Web searches reveal service names:** a query can name a service you use, and it goes to DuckDuckGo. You can turn web search off.
- **Prompt injection:** a web page could try to steer the model, and the default model has had its refusal behaviour removed. Treat AI advice as unverified.
- **Checksums prove integrity, not origin:** they're fetched from the same release as the archive. Model files aren't checked by this app beyond what Ollama does.
- **Findings reflect what you enter:** this tool doesn't scan your accounts or network, so it can't detect a setting you recorded incorrectly.

## Before committing

`.gitignore` excludes `.env`, `data/`, `llm/`, exports and reports. Check `git status` before your first commit, and never force-add those files.
