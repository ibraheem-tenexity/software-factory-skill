# This box has ROS pytest plugins on the global path that break collection.
# Disabling third-party plugin autoload isolates our suite.
PYTEST = PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest

.PHONY: test test-live
test:        ## unit + eval (no real money, runs anywhere)
	$(PYTEST) -q
test-live:   ## full end-to-end slice against real infra (spends real money)
	$(PYTEST) -q -m live
