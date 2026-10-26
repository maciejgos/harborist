# Plan

1. Write focused parser/version tests and observe the missing-module failure.
2. Add frozen skill metadata and content-bound identity records; implement shared
   Markdown/front-matter parsing through the existing safe YAML loader.
3. Test declarations, exact content, metadata mismatch, topology/hook rejection,
   unsafe/ambiguous YAML and meaningful version boundaries.
4. Document the compilation boundary and run full validation before committing.
