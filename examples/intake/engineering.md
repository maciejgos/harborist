# Engineering — version 1

Use spec.md as the acceptance contract. Inspect the target repository's operating
instructions before changing code. Keep changes focused on the requested outcome.

For behavior changes, write a focused failing test, implement the smallest correct
change and refactor with tests passing. Preserve domain/infrastructure boundaries.
BUILD may update plan.md but must not silently change spec.md.

Never infer verification from prose or process exit alone. Mandatory trusted checks
and independent REVIEW must evaluate the exact candidate commit. Document areas
that remain unverified. Do not depend on native-agent session continuity.
