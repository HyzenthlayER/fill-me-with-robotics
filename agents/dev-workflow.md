# catbrain dev-workflow skill

"Agent" here means the AI coding agent working in this repository, not a reinforcement-learning policy.

[catbrain](https://github.com/ziwenzhuang/catbrain) is an external skill repository. Its `dev-workflow` skill collects the safety rules and run conventions one robotics engineer applies to training, testing, and deployment work: dry-run defaults and motor-control boundaries on real robots, per-run log folders with provenance, dataset/code/configuration separation, host layouts, and isolation for parallel agents.

The skill is optional. This file asks the agent to find out whether it is available and to offer the installation. It does not make the skill, or any layout it describes, a requirement for this repository.

## Check

Before work that involves robot training, testing, or deployment conventions, look for the skill on the agent host:

1. If the host loads skills from a directory, look for a skill named `dev-workflow`, that is a `SKILL.md` at `<host-skill-dir>/dev-workflow/SKILL.md`. Common skill directories include `~/.config/opencode/skills`, `~/.claude/skills`, `~/.agents/skills`, and `~/.codex/skills`; use the host's actual directory instead of assuming one of these.
2. Also check a stable checkout such as `~/skills/catbrain/skills/dev-workflow/SKILL.md`.
3. Report the result to the user in one line. Do not install anything yet.

## Install, with the user's approval

Installation writes outside this repository, so show the commands first and install only after the user agrees.

```bash
git clone https://github.com/ziwenzhuang/catbrain.git ~/skills/catbrain
ln -s ~/skills/catbrain/skills/dev-workflow <host-skill-dir>/dev-workflow
```

Then reload the agent so it rescans skills, and confirm that `dev-workflow` resolves. The skill requires reading `skills/dev-workflow/core-coding-principle.md` before it is used.

If the user declines, or the host has no skill mechanism, continue with the task. Say that these conventions were not applied instead of implying that they were.

## Boundaries

- Do not copy the skill's text into this repository or restate it as project documentation. The upstream repository declares no license, so link to it instead.
- Nothing here authorizes movement of physical equipment, or installation on a robot host. `AGENTS.md` still requires explicit authorization for those actions, and the skill's deployment guide only adds restrictions.
- Keep an installation in the user's skill directory, never inside this checkout and never in a commit.
