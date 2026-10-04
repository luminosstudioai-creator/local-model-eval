# Security policy

This is a small demonstration utility, not a certified security product.
Only the latest source version is maintained. The README defines its trust
boundary and limitations. The core uses the Python standard library, makes no
network calls, executes no supplied code, and does not persist input data.
Packaging uses a pinned setuptools build dependency; GitHub Actions are pinned
by commit and run with read-only repository permissions.

Please do not put real secrets or customer data in issues or test fixtures.
For a suspected vulnerability, use GitHub private vulnerability reporting if
available, or open a minimal issue requesting a private reporting channel
without disclosing exploit details or sensitive inputs.

A passing test suite is evidence for those cases, not proof of complete security.
