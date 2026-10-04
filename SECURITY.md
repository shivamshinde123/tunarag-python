# Security Policy

## Supported versions

Security fixes are applied to the latest released 0.x version. Before 1.0, users should upgrade
to the newest patch release rather than expect parallel maintenance branches.

## Reporting

Do not open a public issue for a suspected vulnerability or include provider keys, private
datasets, prompts, retrieved content, or database files in reports. Use GitHub's private
security-advisory reporting for this repository. If that channel is unavailable, contact the
repository owner privately through their GitHub profile.

Include the affected version, minimal reproduction, impact, and whether untrusted input or a
third-party provider is required. Use synthetic data and revoked credentials only.

## Boundaries

TunaRAG redacts known secret values and sensitive keys from package-controlled diagnostics and
exports, but user adapters, evaluators, callbacks, provider clients, and MLflow servers are
separate trust boundaries. Callers remain responsible for data permissions, provider retention,
network policy, encrypted storage, access control, and safe callback implementations. SQLite
and cache files are not encrypted by TunaRAG; protect their containing directory accordingly.
