# k6-create-xk6docs: Setup Guide

Neither `k6 x docs` nor `./k6-with-docs` is available in the current environment.
This skill uses a k6 binary built with the xk6-docs extension.

## Step 1: Check if xk6 is installed

```bash
xk6 version
```

If not installed:
```bash
go install go.k6.io/xk6/cmd/xk6@latest
```

Go 1.21+ is required. Install from https://go.dev/dl/ if needed.

## Step 2: Build the binary in the current directory

```bash
xk6 build --with github.com/grafana/xk6-subcommand-docs@latest -o ./k6-with-docs
```

This takes 30–60 seconds. The binary is created as `./k6-with-docs` in
the current working directory — it is NOT installed globally.

## Step 3: Verify (using the local binary, not k6)

```bash
./k6-with-docs x docs 2>&1 | head -3
```

Expected output: a list of k6 documentation topics.

## Step 4: Using the binary

All doc lookups use `./k6-with-docs x docs` (not `k6 x docs`).
All script validation also uses `./k6-with-docs run` — it is a full k6 binary.

---

## Note for this session

Tell the user:

> `k6 x docs` is not available, and `./k6-with-docs` was not found in the
> current directory.
>
> To enable live documentation lookup, I can build `./k6-with-docs` now.
> This requires `xk6` and Go 1.21+ to be installed.
>
> **Would you like me to build it?**
> - Yes → I'll run the build command above, then continue with doc lookups available.
> - No → I'll continue in examples-only mode. The built-in examples cover all
>   common k6 patterns without needing live docs.

If the user says yes: run Step 2, verify with Step 3, then set the docs command
to `./k6-with-docs x docs` for all subsequent lookups.
If the user says no: skip all doc lookups and work from examples only.
