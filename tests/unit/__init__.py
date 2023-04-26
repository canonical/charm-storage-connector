"""Init mocking for unit tests."""

import sys
from unittest import mock

from ops import testing

testing.SIMULATE_CAN_CONNECT = True

sys.path.append("src")

apt = mock.MagicMock()
sys.modules["apt"] = apt
