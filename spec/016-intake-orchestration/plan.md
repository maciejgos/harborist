# Plan

1. Write integration tests first and observe the missing use-case import failure.
2. Compose existing boundaries through explicit parameters. Share existing real Git
   test helpers instead of importing another test module.
3. Verify resolve-once behavior, exact-base loading despite dirty checkout,
   historical refs, durable file and GitHub captures, and pre-publication failure.
   Use a small fake gh executable for one real subprocess capture integration.
4. Update documentation and run full pytest, Ruff and Pyright before committing.
