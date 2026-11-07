# Contributing

Contributions to the offline evidence verifier, public-repo readiness scanner, tests, and documentation are welcome. Open a focused issue or pull request describing the change and tests. Keep Python functionality dependency-free where practical.

Before submitting, run:

```sh
python -m unittest discover -s tests -v
python verifier.py evidence-manifest.json --root .
```

Never include secrets, customer credentials, private customer data or unpublished code. Public issue submissions are not orders and do not establish any payment obligation.
