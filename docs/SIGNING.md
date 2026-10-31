# Code signing policy

**Rule:** Studio never claims a signature that Windows has not confirmed. Each release records the Authenticode status
of every shipped executable, as `Get-AuthenticodeSignature` reports it on the build machine. The status goes into
`desktop-manifest.json` (`signing.files`, `signing.overall`), and the release notes repeat it.

## Policies

| Policy | When | What a release says |
|---|---|---|
| `signed` | A code-signing identity is configured for the build | Every shipped `.exe` must report `Valid`; otherwise publication stops |
| `unsigned-prerelease` | No signing identity is available | The build is published unsigned, **as a GitHub prerelease**, and says so: Windows SmartScreen will warn, and users compare SHA-256 with `SHA256SUMS.txt` |

There is no third state. A mix of signed and unsigned files, or a status other than `Valid` / `NotSigned`, makes the
build not release-ready (`scripts/desktop_release.py`).

## Who decides

Choosing a policy is the repository owner's decision, not the pipeline's. The decision is a file,
`docs/releases/signing-decision.json` (`horizon-studio.signing-decision/1`), which records:
- the policy;
- who approved it, and when;
- where the approval was given.

The desktop build's `signing-decision` parity gate passes only when that file exists, is complete, and the build
actually matches it. An unsigned build never passes under `signed`. The gate cannot be passed by hand
(`--parity signing-decision` is refused).

No signing identity is invented or bought by automation. Adding one means:
- a certificate (an OV/EV code-signing certificate, or a cloud signing service) obtained by the owner;
- its secrets added to the repository;
- Tauri's `bundle.windows.signCommand` (and a signing step for the frozen core) wired to them;
- the decision record changed to `signed`.

## Status

As of engineering cycle 3 there is **no signing identity**. The repository owner chose `unsigned-prerelease`
(`docs/releases/signing-decision.json`), and 0.8.0 was published that way: every executable's Authenticode status is
`NotSigned` in `desktop-manifest.json`, and the release is a GitHub prerelease.
