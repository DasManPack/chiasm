# Contributing to Chiasm

Thanks for helping build Chiasm, an experimental spatial-first project derived from Melodex.

Product changes should make collection exploration clearer, quieter, and easier to navigate. The current tree retains Melodex-derived host systems and extension contracts; references to those internals are intentional and do not define Chiasm's product direction.

If this is your first contribution to the repository, start with **[Your First Contribution](docs/FIRST_CONTRIBUTION.md)**.

If your goal is to build a provider or enrichment plugin, start with the **[5-minute developer quickstart](docs/DEVELOPER_QUICKSTART.md)** rather than reading the whole repository.

The project welcomes small focused contributions. You do not need to understand the whole player before contributing.

## Choose your contribution path

### Player / UI
Work mainly in `desktop/` or `android/`.

### Music provider
Use the inherited Provider SDK in `provider-sdk/`. Keep source-specific web/API logic in providers rather than coupling it to Chiasm's spatial field.

Start with `docs/tutorials/BUILD_A_PROVIDER.md`.

### Metadata / artwork / identity extension
Use the experimental capability contracts.

Start with `docs/tutorials/BUILD_AN_ENRICHMENT_PLUGIN.md`.

### API / automation
Use REST/OpenAPI, MCP or OpenAI function tools.

Start with `docs/DEVELOPERS.md`.

### Plugin registry
Publish your provider/extension independently, then propose a registry entry.

Start with `docs/tutorials/ADD_PLUGIN_TO_REGISTRY.md` and `docs/developers/17_REGISTRY_GOVERNANCE.md`.

### Documentation / testing
Documentation, fixtures and testing improvements are first-class contributions.

Keep the documentation hierarchy intentional:

```text
README.md                    project landing page
docs/README.md               friendly route-by-goal map
docs/START_HERE.md           first-use path for users
docs/DEVELOPERS.md           developer gateway / choose an interface
docs/developers/README.md    deep developer reference index
docs/ALL_DOCUMENTATION.md    exhaustive index
```

When adding a new page, link it from the appropriate existing router rather than creating another competing "start here" page.

User-facing instructions should use exact current UI labels where practical.

## Before coding

For a substantial architectural change, open an issue first. Small fixes, docs and focused tests can usually go directly to a PR.

## Tests

Desktop:

```bash
cd desktop
PYTHONPATH=. pytest -q tests
```

Provider SDK:

```bash
cd provider-sdk
pytest -q tests
melodex-registry validate registry/registry.json
melodex-registry verify-packages registry/registry.json --packages registry/packages
melodex-registry validate-reviews registry/registry.json --reviews registry/reviews
```

Repository checks:

```bash
python scripts/docs_check.py
python scripts/navigation_check.py
python scripts/ecosystem_check.py
python scripts/version_check.py
python scripts/release_check.py
```

## Provider/plugin contributions

Public extensions should include a README, licence, tests/fixtures and `SOURCE_POLICY.md`.

The source policy should document the upstream API/access method, authentication, rate limit, data/media rights, caching/offline restrictions, commercial restrictions and attribution requirements.

See `docs/developers/11_SOURCE_AND_RIGHTS_POLICY.md`.

## Security

Never commit API keys, passwords, cookies, Bridge tokens, MCP tokens, private signed media URLs or copyrighted media used only as a test fixture.

## Pull requests

Keep PRs focused. Explain:

1. what changed;
2. why it is useful;
3. how it was tested;
4. documentation impact;
5. source/rights implications, when relevant.

## Design principles

- Core stays source-neutral.
- Providers own source-specific logic.
- Capability plugins should do one job well.
- AI integrations use high-level Melodex actions.
- Playback permission does not automatically imply download permission.
- External metadata/artwork should retain provenance where practical.

See [Community](docs/COMMUNITY.md) for non-code contribution paths and [Code of Conduct](CODE_OF_CONDUCT.md) for participation expectations.


## Truth over polish

If documentation claims a feature is verified, reviewed, stable, sandboxed, built in, shipped, signed, secure, or otherwise stronger than the code supports, treat the mismatch as a bug.

Use [Terminology and claim policy](docs/developers/02_TERMINOLOGY_AND_CLAIMS.md) for canonical wording.

Use [Status, stability and trust](docs/developers/00_STATUS_AND_STABILITY.md) as the canonical maturity/security summary.
