# Security policy

## Reporting a vulnerability

Please do not publish secrets, exploit steps or private server logs in a public issue.

If private vulnerability reporting is enabled for this repository, use the repository Security tab. If it is unavailable, open a brief issue asking maintainers to enable a private reporting route; do not include exploit details or credentials in that public issue.

Include the affected version/commit, operating system, Python version, and a minimal reproduction with sensitive information removed. Never include RCON credentials, player passwords, access tokens or private customer information.

## Scope and safe defaults

amxtriage is a local log-analysis utility and optional diagnostic alert bridge. It is not a DDoS scrubbing service. Report suspected unsafe path handling, execution of log-derived input, authorization bypass in the bridge, or unintended source modification.

No response-time SLA is promised by this file.
