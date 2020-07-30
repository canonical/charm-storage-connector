
"""Init mocking for unit tests."""

import sys

import mock


sys.path.append('src')

apt = mock.MagicMock()
sys.modules['apt'] = apt
