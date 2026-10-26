# Plan

1. Confirm focused tests fail because the settings adapter does not exist.
2. Extract the safe unique-key YAML loader, implement local asset capture and
   validate settings through frozen execution records.
3. Test preservation, deletion/edit independence and meaningful malformed settings.
   Budget domain boundaries are already covered by slice 012.
4. Document local settings and run the full required validation before committing.
