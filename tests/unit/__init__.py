"""Init mocking for unit tests."""
import sys
from unittest import mock

apt = mock.MagicMock()
sys.modules["apt"] = apt
