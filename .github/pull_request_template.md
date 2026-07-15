## Summary

- Describe the user-visible change and its scope.

## Verification

- [ ] `PYTHONPATH=src python -m compileall -q src tests`
- [ ] `PYTHONPATH=src python -m unittest discover -s tests`
- [ ] `ruff check src tests`

## Notes

- Include screenshots for Web UI changes.
- Do not include API keys, cookies, generated outputs, logs, or downloaded media.
