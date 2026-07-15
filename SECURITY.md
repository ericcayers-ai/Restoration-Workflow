# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for a security vulnerability. Instead, use
[GitHub's private vulnerability reporting](https://github.com/ericcayers-ai/Restoration-Workflow/security/advisories/new)
for this repository. If you cannot use advisories, contact the maintainer privately via
the path listed on [@ericcayers-ai](https://github.com/ericcayers-ai) (see also
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) for non-security private reports).

Include enough detail to reproduce (affected version, request/input that triggers it,
expected vs. actual behavior).

You should expect an initial response within a few days. This is a small, independently
maintained project — there is no bug bounty, but real reports are taken seriously and
credited in the fix.

## Supported versions

The `main` branch and the latest tagged release receive fixes. Older releases are not
patched individually; upgrade to the latest release to pick up a fix. Current line:
**0.6.0**.

## What this app already does about it

This app downloads and executes third-party neural network weights, and runs a local
HTTP/WebSocket server — two things worth being deliberate about. The relevant design
decisions live in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (Weight Manager /
local binding sections) and are enforced in code, not just written down:

- **Weights are never unpickled.** Checkpoints are read with `torch.load(...,
  weights_only=True)` or `safetensors.torch.load_file` — both refuse a file that carries
  pickled Python objects instead of plain tensors. `spandrel.ModelLoader.load_from_file`
  (which permits arbitrary pickle globals) is never called anywhere in this codebase; see
  `backend/src/restoration/nodes/_torch.py`. A checkpoint that turns out to be a Lightning
  training artifact or a TorchScript archive is *rejected*, not silently loaded — that's
  the reason LaMa's and RestoreFormer's weight manifests point at re-exported files rather
  than the most commonly mirrored ones (documented in `docs/MODEL_STACK.md`).
- **A checksum proves identity, not safety — both gates exist, neither is optional.**
  Every in-box weight file's manifest pins a sha256 computed from a real download. Where
  an upstream publishes no checksum of its own, the `WeightManager` pins the hash on first
  download (trust-on-first-use) and verifies against that pin on every use after
  (`backend/src/restoration/core/weights.py`).
- **Non-permissively-licensed models require an explicit, recorded acknowledgement**
  before their weights download, and Simple Mode's default automatic pipeline is
  validated at startup (`RuleTable.validate()`) to never depend on one.
- **The server binds to `127.0.0.1` only**, never `0.0.0.0` — `restore serve` and the
  packaged Windows PyInstaller build are both local-only by default; there is no built-in
  remote access or authentication layer, because there is no remote surface to authenticate.
- **Pipeline JSON is structurally validated** before it reaches the executor
  (`core/executor.parse_pipeline`) — unknown node types, malformed edges, and multi-sink
  graphs are rejected with a typed error, not passed through to code that assumes
  well-formed input.

## Reporting something in this list that's actually wrong

If you find a real gap in one of the guarantees above — a code path that does unpickle
something it shouldn't, a checksum that's checked too late to matter, anything that
contradicts what's written here — that's exactly the kind of report this policy is for.
