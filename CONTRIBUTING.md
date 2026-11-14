<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/anosys-new-white-darkmode.svg">
      <img src="assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

# Contributing

Thanks for helping improve the Anosys.ai SDK. Bug reports, fixes and new integrations are all welcome.

## Before you start

- For a bug, [open an issue](https://github.com/Anosys-AI/anosys-sdk/issues) with the package, its version, what you expected and what happened.
- For a larger change, such as a new integration, open an issue first so we can agree on the approach.
- Report security problems privately, as described in [SECURITY.md](SECURITY.md).
- Everyone taking part follows our [code of conduct](CODE_OF_CONDUCT.md).

## Set up

You need Python 3.10 or later and Node.js 18 or later.

```bash
git clone https://github.com/Anosys-AI/anosys-sdk.git
cd anosys-sdk
make install-dev   # Python packages in editable mode, plus the JavaScript workspace
```

## Test

```bash
make test          # Python and JavaScript unit tests
make lint          # ruff
```

Every package has its own tests under `packages/<language>/<package>/tests` or `test`. Add a test for the behaviour you change.

## Pull requests

- Keep each pull request to one change, and describe what it does and why.
- Keep the Python and JavaScript versions of an integration in step: a change to one usually needs the same change in the other.
- Never commit real API keys, prompts or customer data, including in tests and notebooks.
- CI must pass before a pull request is merged.

By contributing, you agree that your contribution is licensed under the [Apache License 2.0](LICENSE).
