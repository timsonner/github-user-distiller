# GitHub user distiller

`github_user_distiller.py` builds a short profile of a GitHub user's public code. It asks the GitHub API for that user's public repositories, shallow-clones a sample, and reads lightweight signals from README files, dependency manifests, and source file types. When the GitHub Copilot SDK can open a session, Copilot writes the profile. When the SDK cannot be imported or the session fails, the script writes a heuristic profile from those signals.

The profile text is printed to stdout. Pass `--output` to also save a JSON file.

## Prerequisites

- Python 3.12. The commands in this file were run with Python 3.12.3.
- Git on `PATH`. The commands in this file were run with Git 2.43.0.
- Network access to the GitHub API (`https://api.github.com`) and to the public `html_url` clone addresses the API returns.

`requirements.txt` lists one package, `github-copilot-sdk`. Every other import in the script is from the Python standard library. `python3 -m venv` needs a Python install that includes `ensurepip`. On the Ubuntu host used to check these commands, that meant installing the `python3.12-venv` package before the virtual environment could be created.

A Copilot-written profile needs the SDK installed and a GitHub Copilot CLI that is installed and signed in. A check with the SDK installed, no `copilot` executable, and no Copilot credentials still finished and printed the heuristic profile.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The heuristic profile runs with system Python when the `copilot` module is not installed:

```bash
python3 github_user_distiller.py USERNAME --max-repos 1
```

## Build and test

This repository has no build step and no test suite. A syntax check of the script is:

```bash
python3 -m py_compile github_user_distiller.py
```

## Run

Help (exit 0):

```bash
python3 github_user_distiller.py --help
```

`username` is required. With no arguments the script exits with status 2.

One repository, JSON file, using the virtualenv Python after the install above:

```bash
python github_user_distiller.py octocat --max-repos 1 --output profile.json
```

`profile.json` is listed in `.gitignore`.

The same flags with the default sample size:

```bash
python github_user_distiller.py USERNAME --max-repos 5
```

`--max-repos` defaults to 5, so this is the same as `python github_user_distiller.py USERNAME`.

## Usage

```bash
python github_user_distiller.py USERNAME [--max-repos N] [--output PATH] [--model MODEL]
```

| Argument | Meaning |
| --- | --- |
| `USERNAME` | GitHub user to analyze. Required. |
| `--max-repos N` | Maximum number of repositories to inspect. Default: `5`. |
| `--output PATH` | Also write the JSON result to this path. |
| `--model MODEL` | Copilot model name. If omitted, the script uses `COPILOT_MODEL`, then `GITHUB_COPILOT_MODEL`, then the SDK default. |
| `-h`, `--help` | Show argparse help. |

What a run does:

1. Loads public repositories from `https://api.github.com/users/<username>/repos` in pages of 100 and keeps the first `--max-repos` entries.
2. A 404 from that API raises `User '<username>' was not found`.
3. An empty repository list raises `No repositories found for '<username>'`.
4. Shallow-clones each selected repository with `git clone --depth 1` into a `github-user-distill-*` directory in the current working directory. The directory is deleted when the run finishes.
5. Prints `Skipping <repo>: ...` on stderr when a clone fails, then continues with the remaining repositories.
6. From each clone, keeps counts of text-like file suffixes, language counts, one dependency manifest excerpt, and one README excerpt. Scanned suffixes are `.py`, `.md`, `.txt`, `.json`, `.toml`, `.yml`, `.yaml`, `.ini`, `.cfg`, `.sh`, `.ps1`, `.js`, `.ts`, `.tsx`, `.jsx`, `.go`, `.rs`, `.java`, `.rb`, `.php`, `.c`, `.cpp`, `.h`, `.hpp`, and extensionless files. Paths inside `.git`, `node_modules`, `__pycache__`, or `.venv` are skipped. Language counts cover Python, JavaScript/TypeScript, Go, Rust, Java, Ruby, and C/C++. The manifest is the first existing file among `pyproject.toml`, `requirements.txt`, `package.json`, `setup.py`, `Cargo.toml`, `go.mod`, and `Pipfile`, truncated to 800 characters. The README excerpt is the `readme*` file nearest the repository root, truncated to 2000 characters.
7. Asks Copilot for a short profile of recurring themes, preferred languages, likely intentions, and style. The session appends a system message that asks for coding style, likely interests, and project intentions. If the requested model is rejected as unavailable, the script retries once without a model name.
8. Prints the profile text to stdout.
9. With `--output`, writes JSON with `user`, `repo_count`, `repos` (`repo_name`, `description`, `languages`, `file_types`, and `manifest_summary` truncated to 400 characters), and `profile`.

When Copilot is not used, the heuristic profile names the user and can include:

- preferred languages that were counted
- a line when Python files were present
- a line when JavaScript or TypeScript files were present
- a line when a dependency manifest was present

If `copilot` cannot be imported, stderr includes `Copilot SDK import warning: ...` and `Note: Copilot SDK authentication is not available, so the script used a heuristic profile fallback.` If the import works and the session fails, stderr includes `Copilot SDK path failed: ...` and `Falling back to heuristic profile because Copilot authentication is unavailable.`

## Layout

```text
github_user_distiller.py
requirements.txt
.gitignore
README.md
.github/skills/copilot-sdk-python-distilled/SKILL.md
```

`github_user_distiller.py` is the program. `requirements.txt` lists `github-copilot-sdk` with no version. `.gitignore` ignores virtual environments, `__pycache__`, `profile.json`, `*.log`, and `github-user-distill-*/`.

`.github/skills/copilot-sdk-python-distilled/SKILL.md` is standalone reference notes for the GitHub Copilot SDK for Python (client, sessions, tools, hooks, MCP, custom agents, and skills). The distiller talks to Copilot through `CopilotClient` in `github_user_distiller.py`.

This repository has no license file.
