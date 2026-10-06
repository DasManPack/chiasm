# Responsible use and source policy

Chiasm is an experimental spatial interface for exploring music collections. It reuses parts of Melodex's local playback and provider foundations and is designed to work with music and media that a user is authorized to access.

## What is built into the desktop app

The desktop application includes:

- local-file playback for media you control or are permitted to use;
- the Jamendo reference integration using Jamendo's documented public API and a user-supplied developer client ID;
- source-neutral provider/runtime infrastructure;
- Provider Bridge support for authorized local/LAN access;
- optional LLM integrations for player control.

“Built into the app” is different from “present in the repository” or “available in the Plugin Directory”.

## What else the public repository includes

The repository also contains project-maintained/reference material built on the same public extension interfaces, including:

- an Internet Archive reference provider for publicly accessible material;
- registry example packages for Radio Browser and LibriVox;
- registry example extensions for MusicBrainz and Wikimedia Commons;
- the inherited Melodex Provider Protocol (MPP), Provider SDK, capability-extension contracts, and registry tooling.

A reference/example integration does **not** imply that every item exposed by the upstream service has identical rights or licence terms.

## What the public project does not include

The public repository does not include:

- credentials, private API keys, bearer tokens, cookies, or account secrets;
- source-specific access-control or DRM circumvention code;
- provider code intended to obtain media without authorization;
- undocumented private endpoints copied from third-party services for bypass purposes;
- copyrighted music files or sample libraries that are not redistributable.

## Third-party providers and extensions

Third-party providers/extensions are separate software.

Compatibility with Melodex, presence in the registry, or mention in documentation does not by itself mean Melodex endorses a package or guarantees that every use of the upstream service is permitted.

Registry status and installation terminology have specific meanings:

- **example** — learning/reference registry entry;
- **community** — community-published registry entry;
- **reviewed** — current Melodex technical/source-policy review was applied;
- **registry-verified install** — downloaded package size/SHA-256 and package ID/version matched registry metadata.

None of those terms means cryptographic publisher signing, legal certification, or blanket rights approval.

Provider authors and users remain responsible for checking relevant service terms, licences, permissions, and applicable law.

Melodex maintainers may decline links, packages, instructions, issues, or pull requests that add source-specific bypass logic, expose credentials, redistribute copyrighted media without permission, or are primarily intended to facilitate unauthorized access.

## Security

Desktop `.mdxprovider` and `.mdxplugin` packages can contain executable third-party code.

Process separation improves failure isolation but is not a complete operating-system sandbox.

Review the publisher, declared permissions, source code, registry status, and source policy where available before installing third-party code.

See [SECURITY.md](SECURITY.md) and the [terminology and claim policy](docs/developers/02_TERMINOLOGY_AND_CLAIMS.md).

## LLM privacy

LLM support is optional. Ask Melodex reduces track data through a positive allowlist before model submission.

See [Privacy](docs/PRIVACY.md) for the current context and credential-storage behavior.

## Reporting concerns

For security-sensitive concerns, follow [SECURITY.md](SECURITY.md).

For source-policy questions, open an issue without posting credentials, access tokens, copyrighted media, or instructions for bypassing access controls.
