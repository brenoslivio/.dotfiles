# Tested updates

## GitHub setup

1. Publish the workflows and run CI before enabling required checks.
2. Enable Actions and “Allow GitHub Actions to create and approve pull requests”.
3. Enable automatic deletion of merged proposal branches. An orphan proposal
   branch is deliberately not overwritten.
4. Protect `main`: require PRs, require `ahimsa-ready`, require branches to be
   current, apply rules to administrators, and disallow force pushes/deletion.
   Zero required reviewers permits solo maintenance; CI remains required.
5. Authenticate locally with `gh auth login` (repository and Actions read access).

`scripts/configure-github.sh` applies repository settings with an authenticated
administrator account after the first CI run. Review its JSON policy first.
Use an account able to administer this repository; the updater itself needs
only read access. No extra App key is required: proposal automation explicitly
dispatches CI using `GITHUB_TOKEN`.

Friday proposals run at 15:23 UTC (12:23 São Paulo). Existing PRs, failures, and
manual fixes are retained; another scheduled run retries CI without rewriting
that proposal. Merge or close it and delete its branch before the next proposal.
The Actions “Run workflow” button can request an earlier proposal.

## First activation

The previously installed `up` does not enforce this policy. After merging this
implementation and passing the **push** CI run on `main`, use the new updater:

```console
git switch main
git pull --ff-only
nix shell --no-update-lock-file --inputs-from . nixpkgs#gh -c gh auth login
nix run --no-update-lock-file "git+file://$PWD?rev=$(git rev-parse HEAD)#updater" -- up
```

Start from a clean checkout. This bootstrap still verifies the exact commit and
build path before activation. Once activated, the normal Fish commands use the
installed updater. No automatic activation is part of CI or repository setup.

## What CI proves

The same `scripts/check.sh` runs locally and in CI. Full checks evaluate the
flake, build `ahimsa` and standalone Home Manager, validate generated files,
exercise updater failure cases, and boot a VM using the shared system modules.
`dotfiles-check quick` omits system/Home Manager builds and VM execution.

Generated-file checks cover Fish, Lua, Hyprland's native config validation,
shell syntax, JSONC, TOML, wlogout JSON, and desktop entries. They do not establish
that every application behaves correctly at runtime. The VM checks console login, Home Manager activation,
NetworkManager, D-Bus, CUPS, rootless Podman, and PipeWire/WirePlumber.

VM differences: virtual hardware, disposable credentials, disabled SDDM/X server,
no personal VPN profile, and disabled update notifications/automatic GC.
Graphical SDDM/Hyprland login is not yet a required VM test. Verify GPU, monitors,
Wi-Fi/Bluetooth, audio, lock/unlock, and suspend on the physical machine.

The hosted runner removes unused preinstalled SDKs and requires 40 GiB free
before building. The existing system closure is approximately 27 GiB. Actual
CI capacity and duration must be confirmed by the first hosted run; use a larger
runner if the capacity check or full build fails. Never bypass checks to fit.
Only upstream binary caches are configured. A project cache is optional future
infrastructure; local installations can build missing outputs themselves.

## Installation gate

Only a successful `push` run of `.github/workflows/ci.yml` on the exact current
`main` SHA qualifies. Both `checks` and `ahimsa-ready` must actually succeed.
PR/dispatch runs, skipped jobs, missing evidence, and unsuccessful newer runs do
not qualify. Evidence identifies repository, SHA, host, platform, user, run,
attempt, and system/Home Manager output paths. Evidence expires after 90 days;
rerun the original push run if needed. A manual dispatch is not a replacement.

`up` checks a clean `main`, fetches, verifies CI, fast-forwards, and builds an
immutable Git snapshot without updating `flake.lock`. It compares the output
path to CI evidence, displays package changes and an activation preview, then
asks when to activate. GitHub/API failure stops normal updates.

Matching store paths establish the same Nix derivation/output identity, not an
independent byte-for-byte reproducibility audit of locally rebuilt packages.

## Activation and recovery

- **Apply now:** switch system and next-boot default; kernel changes need reboot.
- **Next boot:** change the boot default without switching the running system.
- **Later:** retain the candidate without changing either current selection.

“Later” preserves an update already scheduled for boot. Git checkout state,
active system, boot default, and standalone Home Manager activation are distinct.
`dotfiles-status` shows actual system links plus recorded intent; after an
interrupted activation those actual links are authoritative.

Candidates have garbage-collection roots under `~/.local/state/dotfiles`.
Before the first activation, the current system is protected in
`/nix/var/nix/profiles/dotfiles-known-good`. After hardware verification, run
`dotfiles-mark-good` to replace that protected baseline. Daily cleanup removes
ordinary generations older than 60 days. The protected baseline is available
through `rollback-good`; ordinary retained generations appear in the boot menu.

`rollback` and `rollback-good` require no network or CI. They restore system
configuration, not mutable application data. Standalone `home` activations have
separate Home Manager generations; use `home-manager generations` to inspect
those when recovering user-only changes.

Notifications check eligibility without fetching or changing dependencies.
Daily and Friday timers suppress duplicate notices for the same revision/state.
Pending or failed CI is logged to `journalctl --user -u flakeUpdate`.
