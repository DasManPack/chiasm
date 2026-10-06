# Your First Chiasm Contribution

This page is for people who want to contribute **to the Chiasm repository** without first learning the whole project.

It is not another user or developer start page:

- listeners should use [Start Here](START_HERE.md);
- extension authors should use the [5-minute developer quickstart](DEVELOPER_QUICKSTART.md);
- contributors to Chiasm itself can use this page.

## Pick one small lane

Good first contributions have a narrow result that is easy to review.

| Interest | Good first contribution |
| --- | --- |
| Documentation | Fix one unclear page, broken explanation or missing cross-link |
| Testing | Add one regression test or one offline fixture |
| Provider SDK | Improve one validator, example or error message |
| Plugin ecosystem | Improve one source policy, review record or tutorial |
| Desktop | Fix one contained UI/diagnostic issue with a regression test |
| Android | Fix one contained client issue |
| Accessibility / UX | Improve one label, keyboard path, contrast issue or confusing flow |

You do **not** need to understand Flow, the resolver, Qt, Android and the provider protocol all at once.

## 1. Get the repository

```bash
git clone https://github.com/DasManPack/chiasm.git
cd chiasm
git checkout -b my-small-change
```

If you plan to open a pull request from your own fork, clone your fork instead.

## 2. Run the checks that match your change

For a documentation-only change, start with:

```bash
python scripts/docs_check.py
python scripts/navigation_check.py
python scripts/terminology_check.py
python scripts/ecosystem_check.py
```

For Provider SDK work:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e 'provider-sdk[dev]'

pytest -q provider-sdk/tests
melodex-registry validate provider-sdk/registry/registry.json
melodex-registry validate-reviews \
  provider-sdk/registry/registry.json \
  --reviews provider-sdk/registry/reviews
```

Windows PowerShell activation:

```powershell
.venv\Scripts\Activate.ps1
```

For desktop work, install the desktop dependencies and run:

```bash
python -m pip install -r desktop/requirements.txt pytest
PYTHONPATH=desktop pytest -q desktop/tests
```

The full repository CI also runs version, release, documentation, ecosystem and Provider SDK checks.

## 3. Make one understandable change

Prefer a pull request that a reviewer can describe in one sentence.

Good:

```text
Add a regression test for a provider redirect.
Clarify how secret plugin configuration is stored.
Add one missing review-history check.
Fix the Sources diagnostic export label.
```

Avoid combining unrelated cleanup, new architecture, UI redesign and documentation restructuring in one first PR.

## 4. Keep the trust boundaries intact

Before committing, check that your change does not accidentally:

- add credentials, tokens, cookies or private URLs;
- put source-specific integration logic into Melodex Core without a deliberate reason;
- describe a plugin as sandboxed when it is not;
- describe a registry-verified package/install as proof of cryptographic publisher identity;
- assume playback permission also grants download/offline permission;
- discard provenance for external metadata/artwork;
- introduce copyrighted media purely as a test fixture.

If your change touches a public source or plugin, read [Source and rights policy](developers/11_SOURCE_AND_RIGHTS_POLICY.md).

## 5. Open the pull request

Use the repository pull-request template.

A useful PR description says:

1. what changed;
2. why it is useful;
3. what you tested;
4. whether documentation changed;
5. whether source/rights/security assumptions changed.

Small PRs are welcome.

## Need help choosing something?

Use the repository issue chooser and select **Community / newcomer question**:

https://github.com/Cliff-Lee/melodex/issues/new/choose

You can describe what you are interested in without arriving with a complete design.

Also see:

- [Contributing](../CONTRIBUTING.md)
- [Community](COMMUNITY.md)
- [Code of Conduct](../CODE_OF_CONDUCT.md)
- [Status, stability and trust](developers/00_STATUS_AND_STABILITY.md)
