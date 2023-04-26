from unittest import TestCase
from unittest.mock import patch

import utils


class TestUtils(TestCase):
    def test_init_is_systemd(self):
        service = "snap.foo.service"
        self.assertTrue(utils.init_is_systemd(service))

    @patch("utils.init_is_systemd")
    @patch("utils.os.path.exists")
    def test_is_container(self, mock_exists, mock_init_is_systemd):
        mock_init_is_systemd.return_value = False
        mock_exists.return_value = True
        result = utils.is_container()
        mock_exists.assert_called_once_with("/run/container_type")
        self.assertTrue(result)
