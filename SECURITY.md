# Security

Chiasm reuses Melodex-derived provider and package systems. Some internal modules still use the `melodex` namespace; that code remains subject to these notes.

Please report security issues privately rather than opening a public issue containing exploit details.

## Third-party plugin trust

Desktop `.mdxprovider` and `.mdxplugin` packages contain executable third-party code.

Melodex runs them out-of-process, which improves crash/failure isolation, but they still run with the operating-system permissions of the current user unless additional OS sandboxing is configured.

Declared plugin permissions are not universal OS-level enforcement. Melodex does enforce a narrower provider playback-host allowlist in its HTTP(S) Playback Gateway, including redirect checks.

Install third-party code only from publishers/sources you trust.

## Registry integrity

Plugin Directory installs require an HTTPS package URL plus registry-recorded byte size and SHA-256.

Melodex verifies those values before installing the package.

This verifies package integrity relative to the registry. It is **not publisher signing**.

Cryptographic publisher identity/signatures are planned but not implemented.

## Installation provenance

For new installs, Melodex records whether a package came from:

- the registry (registry-verified against size/SHA-256 and package ID/version); or
- a manual file (local hash recorded, not registry-verified).

This provenance improves transparency and update diagnostics; it is not a sandbox.

## Process environment

Third-party provider and capability-extension subprocesses are started with a scrubbed environment rather than inheriting the complete Melodex process environment.

Melodex forwards only a small set of ordinary operating-system/runtime variables plus the package identity and package-local Python path. Arbitrary parent API keys, tokens, cookies, provider credentials and parent `PYTHONPATH` values are not forwarded by default.

This reduces accidental secret exposure; it is **not** an operating-system sandbox.

## Plugin configuration and credentials

Third-party providers and capability extensions may declare `string`, `secret` and `boolean` configuration fields.

Melodex brokers only declared values to that plugin at runtime. Secret fields use the operating-system credential store when a usable keyring backend is available. If secure persistent storage is unavailable, secret values are kept in session memory rather than written to ordinary JSON configuration.

This is configuration brokerage, not a general OAuth/session vault and not a sandbox.

## Credentials

Do not commit API keys, provider credentials, Bridge bearer tokens, signing keys or LLM secrets.

Do not place credentials in manifests, capability descriptors, registry entries, provenance, playlists, fixtures or public diagnostic output.

GitHub Actions signing secrets should use repository/environment Secrets.

## Mobile

Android does not execute arbitrary downloaded provider/plugin code; it accesses remote provider functionality through the Bridge model.

## Source-integrity boundary

Security reports may also cover plugin packages that unexpectedly request credentials, expose tokens, access undeclared destinations or attempt to bypass access controls.

The public Melodex repository intentionally keeps source-specific integration logic outside Core unless it is an approved, documented reference integration.

See [Status, stability and trust](docs/developers/00_STATUS_AND_STABILITY.md) for the precise current trust model.
