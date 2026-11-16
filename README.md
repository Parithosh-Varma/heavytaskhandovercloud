# heavytaskhandovercloud

`hth` — hand long-running tasks off from your laptop to a **Google Cloud Shell** session, controlled entirely via the `gcloud` CLI.

Scraping, extraction, heavy compute: start it locally, let Cloud Shell run it in `tmux`, pull the `./output/` back when it's done. Jobs survive local disconnects. No servers, no project ids hardcoded, stdlib-only Python.

## Install

Requires Python 3.9+ and the [gcloud CLI](https://cloud.google.com/sdk/docs/install) with an account that can use Cloud Shell.

```bash
git clone https://github.com/Parithosh-Varma/heavytaskhandovercloud.git
cd heavytaskhandovercloud
chmod +x hth
# add to PATH (pick one):
export PATH="$PWD:$PATH"
# or
sudo ln -s "$PWD/hth" /usr/local/bin/hth
```

Verify:

```bash
hth --help
hth init --dry-run   # prints gcloud commands without running them
```

## Quickstart

```bash
# 1. one-time setup: checks gcloud, starts Cloud Shell, creates ~/hth/jobs
hth init

# 2. run a command detached (prints a job id)
hth run "python3 -u examples/scrape_example.py"

# 3. run a script file + extra data files
hth run examples/scrape_example.py --files data/urls.txt

# 4. watch it
hth status
hth status <id>
hth logs <id> -f

# 5. get results (remote output/ -> ./results/<id>/)
hth pull <id>

# 6. stop / clean
hth kill <id>
hth clean <id>
hth clean --yes   # all jobs
```

Example job:

```bash
hth run examples/scrape_example.py
# 20261116-122635-52596f
hth logs 20261116-122635-52596f -f
hth pull 20261116-122635-52596f
ls results/20261116-122635-52596f/
```

`--keepalive` keeps the VM awake while your job runs:

```bash
hth run "bash long_job.sh" --keepalive
```

`--dry-run` on any command prints the `gcloud` invocations instead of running them — useful for testing / CI without Cloud Shell:

```bash
hth init --dry-run
hth run "echo hi" --dry-run
```

## Command reference

| Command | What it does |
|---|---|
| `hth init` | Checks `gcloud` exists + logged in. Runs `gcloud cloud-shell ssh --authorize-session --command "echo ready"` to start Cloud Shell, then `mkdir -p ~/hth/jobs`. Creates `~/.hth/jobs.json`. |
| `hth run <cmd\|file> [--files F...] [--setup FILE] [--keepalive]` | Creates job id `YYYYMMDD-HHMMSS-<6hex>`. `scp`s the script + `--files` to `~/hth/jobs/<id>/` via `gcloud cloud-shell scp`. Writes a `run.sh` wrapper (runs `setup.sh` first if present), launches it detached in `tmux new-session -d -s <id>` with stdout/stderr → `out.log`, exit → `exit_code`. Prints the id. Never blocks. |
| `hth status [id]` | One `ssh` probe per listing. `running` = tmux session alive. `done`/`failed` = `exit_code` is `0`/non-zero. `lost` = dir exists but tmux gone and no `exit_code` (VM reset/slept). `missing` = dir gone. Updates `~/.hth/jobs.json`. |
| `hth logs <id> [-f] [-n N]` | `tail -n N ~/hth/jobs/<id>/out.log` over ssh. `-f` polls every 2s (`tail -c +OFFSET`) until the job finishes or Ctrl-C. |
| `hth pull <id> [--dest DIR]` | `gcloud cloud-shell scp --recurse cloudshell:~/hth/jobs/<id>/output localhost:./results/<id>`. Default dest `./results/<id>/`. |
| `hth kill <id>` | `tmux kill-session -t <id>`. Marks job `killed` locally, stops its keepalive. |
| `hth clean [id] [-y]` | With id: `rm -rf ~/hth/jobs/<id>` + drop from local state. Without id: `rm -rf ~/hth/jobs && mkdir -p ~/hth/jobs` + clear state (asks unless `-y`). |

Global flags: `--project P` (or `HTH_PROJECT` env) is passed as `--project=P` to every gcloud call. `--dry-run` works globally (`hth --dry-run run ...`) or per-command (`hth run ... --dry-run`). Display: `--no-color` (or `NO_COLOR=1`) disables colors/spinners for pipes and CI; `--debug` shows raw tracebacks.

Local state: `~/.hth/jobs.json` maps `id -> {id, command, start_time, last_known_status, exit_code?}`. Remote layout per job:

```
~/hth/jobs/<id>/
  run.sh      # generated wrapper (setup.sh + main)
  setup.sh    # optional, runs first; fail aborts job
  out.log     # stdout+stderr
  exit_code   # written when wrapper finishes
  output/     # your job writes here; `hth pull` fetches it
```

## Limitations of Cloud Shell

- **Ephemeral VM, persistent `$HOME`.** Only `$HOME` survives restarts. `hth` stores everything under `~/hth/jobs`, but `tmux` sessions die on reset. A job whose dir exists with no tmux and no `exit_code` is reported as `lost` — re-run it. `hth` re-creates `~/hth/jobs` automatically when it notices a reset.
- **Sleeps after inactivity.** The VM sleeps after ~20 min without interaction (exact behavior changes). Long idle jobs can be frozen/killed. Use `hth run ... --keepalive` to ping every 4 min, or keep a `hth status`/`hth logs -f` polling loop open.
- **Quotas.** Free Cloud Shell has weekly/CPU quotas. On `quota/exhausted` errors `hth` exits with a friendly message — wait and retry, or switch account/project. See https://cloud.google.com/shell/quotas.
- **Noisy neighbors + timeouts.** Cloud Shell is not a batch system: ~no SLA, limited CPU/RAM/disk, 60-day inactivity cleanup, and `ssh`/`scp` can flap. Keep jobs idempotent, checkpoint to `output/`, and `hth pull` incrementally.
- **Network egress.** Fetching the public internet works, but aggressive scraping can be throttled. Be polite (timeouts, retries, small concurrency — see `examples/scrape_example.py`).

## Development

Stdlib only: `hth` plus `lib/ui.py` (terminal styling, no dependencies). Test without Cloud Shell:

```bash
./hth init --dry-run
./hth run "echo hi" --dry-run
./hth run examples/scrape_example.py --files README.md --keepalive --dry-run
./hth status --dry-run
./hth logs abc123 -f --dry-run
./hth pull abc123 --dry-run
./hth kill abc123 --dry-run
./hth clean abc123 --dry-run
python3 examples/scrape_example.py  # real local fetch -> ./output/
```

`--dry-run` prints every `gcloud cloud-shell ssh/scp` invocation with `+ ` prefix and touches nothing remote.
