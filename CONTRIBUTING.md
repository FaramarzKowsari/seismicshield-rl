# Contributing

Contributions must preserve the research contract. Any change to objectives, metric definitions, earthquake splits, evaluation budgets or confirmatory statistics must be explicit in a pull request and versioned before a confirmatory run.

For code changes:

```bash
pip install -e ".[dev,api]"
pytest -q
ruff check src tests scripts
```

Do not commit restricted earthquake records or data whose redistribution terms are unclear.
