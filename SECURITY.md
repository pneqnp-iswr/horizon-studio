# Security Policy

## Supported versions

Horizon Studio is in **alpha**, and security fixes will target the latest version of the `main` branch.

## Reporting a vulnerability

Please **do not** disclose an exploit publicly before maintainers can investigate. Use the repository's **Private vulnerability reporting** feature (Settings → Security → Code security and analysis) if enabled. If it is unavailable, open a public issue requesting a private channel, **without including exploit details**.

This tool processes untrusted JSON projects and images; do not open files from unknown sources without care. The local server binds to loopback only. Native Horizon mods may execute code with broad privileges: review them independently before installation.
