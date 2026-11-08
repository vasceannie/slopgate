"""Fake native-manager CLIs used by host installer tests."""

from tests.native.omp_fake import read_fake_state, write_fake_omp
from tests.native.pi_fake import FakePi

__all__ = ["FakePi", "read_fake_state", "write_fake_omp"]
