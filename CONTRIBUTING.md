# Contributing

**Any PR related to robotics software is welcome.**

Open a PR directly. Use English for project documentation, code comments, and contribution descriptions. Authors are responsible for their submissions, including AI-assisted work. Use a draft PR if you are not ready for it to be merged.

## The rules

1. **Stay within scope.** Explain the contribution's connection to robotics software. Supporting material must serve that software. Hardware deliverables are outside scope.
2. **Respect existing work and other contributors.** Explain removals and breaking changes. Do not erase others' work without justification. No harassment, spam, or disclosure of private information.
3. **Report validation honestly.** State what you checked and the result, or say it is untested. Keep claims within the evidence provided. Checks should fit the change; incomplete validation must be disclosed, not disguised.
4. **Respect sources and licenses.** Original contributions use the root Apache License 2.0. Identify third-party sources, confirm redistribution is permitted, and preserve required notices. Clearly separate and label material under another license.
5. **Keep execution deliberate.** Do not include secrets, malware, credential collection, or concealed side effects. Software that operates physical equipment must document prerequisites, limits, and how to stop it, and require an explicit user action to start operation. Do not silently bypass existing protections.
6. **Keep governance transparent.** Explicitly describe changes to rules, licensing, review guidance, or automation, including their reason and effect. There is no required stack, architecture, or development direction.

## PR description

Explain the change, its connection to robotics software, how to use or inspect it, what you checked, and any relevant risks or sources. Remove template sections that do not apply.

Document any required setup with the affected contribution. There is no repository-wide build system at the start.

## Review and merging

Codex automatic review is the intended first pass after the owner enables it. Fix concrete defects and rule violations, or explain why a finding does not apply. Authors can request another pass with `@codex review` once the GitHub integration is connected. A review is advice, not a promise of correctness or hardware safety.

The owner handles merging with a bias toward accepting contributions within scope that follow these rules. Suggestions about style or architecture should not become additional admission rules. No response from a bot does not authorize a merge; follow up in the PR if review is missing.

Rules can evolve through PRs. Explain the proposal openly and preserve prior work in Git history. If a contribution is reverted or declined, leave a concrete reason in the PR so the experiment remains understandable.
