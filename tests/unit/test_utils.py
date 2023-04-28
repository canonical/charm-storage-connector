import utils


def test_init_is_systemd():
    assert utils.init_is_systemd("snap.foo.service")


def test_is_container(mocker):
    mocker.patch("utils.init_is_systemd", return_value=False)
    mock_exists = mocker.patch("utils.os.path.exists", return_value=True)

    result = utils.is_container()
    mock_exists.assert_called_once_with("/run/container_type")
    assert result
