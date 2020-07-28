import mock
import sys

sys.path.append('src')

apt = mock.MagicMock()
sys.modules['apt'] = apt