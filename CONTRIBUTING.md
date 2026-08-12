# Contributing

## The most useful things you can do

1. **Publish a real Cut Profile** for a garment you own or make, and open an issue with
   what the schema could not express. Schema gaps found against real garments are worth more than
   any amount of design discussion.
2. **Take an open question** from `spec/05-open-questions.md` and answer it with sources.
3. **Break the matcher.** A body and a garment where the answer is obviously wrong, as a
   failing test, is the single most valuable pull request in this repository.

## Ground rules

- Sign off your commits: `git commit -s` (DCO).
- Contributions are accepted under the repository licences: CC BY 4.0 for the specification,
  Apache 2.0 for the code. There is no CLA. See `LICENSING.md`.
- Schema changes need an example document and a test.
- Do not add a field without writing why it exists. Every field in v0.1 has a reason in `spec/`,
  and that property is worth keeping.
- Do not contribute measurement data about real people, yours included. Examples are synthetic and
  must stay that way.

## Running the tests

```bash
cd reference
pip install -e ".[dev]"
pytest
```
