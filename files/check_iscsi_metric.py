#!/usr/bin/env python3
#
# Copyright 2022 Canonical Ltd
#
# Authors: Nicholas Malacarne <nicholas.malacarne@canonical.com>
#          Mert Kırpıcı       <mert.kirpici@canonical.com>
#
"""NRPE check script for iscsi metrics."""
import re
import subprocess
import sys
from argparse import ArgumentParser, Namespace
from typing import Dict, List
from urllib.request import urlopen

NAGIOS_STATUS_OK = 0
NAGIOS_STATUS_WARNING = 1
NAGIOS_STATUS_CRITICAL = 2
NAGIOS_STATUS_UNKNOWN = 3

NAGIOS_STATUS = {
    NAGIOS_STATUS_OK: "OK",
    NAGIOS_STATUS_WARNING: "WARNING",
    NAGIOS_STATUS_CRITICAL: "CRITICAL",
    NAGIOS_STATUS_UNKNOWN: "NAGIOS_STATUS_UNKNOWN",
}


def get_metrics(name: str) -> List[str]:
    """Get the metrics from the exporter."""
    with urlopen("http://127.0.0.1:9090/") as response:
        response = response.read().decode()

    metrics = [line.split() for line in response.splitlines() if line.startswith(name)]
    if not metrics:
        raise RuntimeError(f"Metric: {name} not found")

    return metrics


def get_total_paths_per_alias(metrics: List[str]) -> Dict[str, int]:
    """Get the total paths per alias.

    Each line of metrics coming from the exporter are of the following form:

    iscsi_multipath_path_total{alias="mpatha",wwid="3624..."} 4.0

    Return a dictionary of the form:
    {"mpatha": 4}
    """
    result = {}
    for metric in metrics:
        alias = re.findall(r'alias="\w+"', metric[0])[0].split("=")[1].strip('"')
        paths = int(float(metric[1]))
        result[alias] = paths
    return result


def parse_args() -> Namespace:
    """Parse the command line."""
    parser = ArgumentParser(description="Check Multipath status.")
    parser.add_argument(
        "--expected_num",
        "-n",
        type=int,
        help="The expected number of paths per volume.",
        default=0,
    )
    return parser.parse_args()


def main() -> None:
    """Check multipath for correct number of paths per volume and alert."""
    args = parse_args()
    try:
        output = get_total_paths_per_alias(get_metrics("iscsi_multipath_path_total"))
        for alias, num_paths in output.items():
            if num_paths != args.expected_num:
                message = f"Expected {args.expected_num} paths for {alias} but found {num_paths}."
                print(f"{NAGIOS_STATUS[NAGIOS_STATUS_CRITICAL]}: {message}")
                sys.exit(NAGIOS_STATUS_CRITICAL)

        print(f"{NAGIOS_STATUS[NAGIOS_STATUS_OK]}: Correct number of paths found.")
        sys.exit(NAGIOS_STATUS_OK)

    except (
        RuntimeError,
        FileNotFoundError,
        PermissionError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"{NAGIOS_STATUS[NAGIOS_STATUS_CRITICAL]}: {str(error)}")
        sys.exit(NAGIOS_STATUS_CRITICAL)


if __name__ == "__main__":
    main()
