"""Allow ``python -m personalize`` to invoke the CLI."""

from .cli import main

raise SystemExit(main())
