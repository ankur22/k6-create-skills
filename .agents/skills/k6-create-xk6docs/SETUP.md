# k6-create-xk6docs: Setup Guide

`k6 x docs` is not working in the current environment.

## k6 v1.7.0+ (recommended) — no build required

As of k6 v1.7.0, the docs subcommand is **auto-provisioned** on first use.

```bash
# Check your version
k6 version

# If v1.7.0+, just run (auto-downloads the extension binary on first use, ~30s):
k6 x docs --version v1.6.1 2>&1 | head -3
```

> **Why `--version v1.6.1`?** The v1.7.x doc bundle hasn't been published yet.
> Once it ships, you can drop the flag and `k6 x docs` will work without it.

If this succeeds, set `DOCS_CMD = k6 x docs --version v1.6.1` and continue.

---

## Older k6 — manual build

If you're on k6 < v1.7.0, build the binary manually:

### Step 1: Check if xk6 is installed

```bash
xk6 version
```

If not installed (requires Go 1.21+):
```bash
go install go.k6.io/xk6/cmd/xk6@latest
```

### Step 2: Build in the current directory

```bash
xk6 build --with github.com/grafana/xk6-subcommand-docs@latest -o ./k6-with-docs
```

Takes 30–60 seconds. Binary is created as `./k6-with-docs` — NOT installed globally.

### Step 3: Verify

```bash
./k6-with-docs x docs 2>&1 | head -3
```

If this succeeds, set `DOCS_CMD = ./k6-with-docs x docs` and continue.

---

## Note for this session

Tell the user:

> `k6 x docs` is not working in this environment.
>
> **If you have k6 v1.7.0+:** run `k6 x docs --version v1.6.1` — it auto-provisions everything.
>
> **If you have an older k6:** I can build `./k6-with-docs` if `xk6` and Go 1.21+ are available.
> Would you like me to try?
>
> If neither works, I'll fall back to web docs from grafana.com.
