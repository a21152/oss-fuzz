# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests the functionality of the cifuzz module's functions:
1. Building fuzzers.
2. Running fuzzers.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

import parameterized

# pylint: disable=wrong-import-position
INFRA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(INFRA_DIR)

OSS_FUZZ_DIR = os.path.dirname(INFRA_DIR)

import cifuzz
import config_utils
import fuzz_target
import test_helpers

# NOTE: This integration test relies on
# https://github.com/google/oss-fuzz/tree/master/projects/example project.
EXAMPLE_PROJECT = 'example'

# Location of files used for testing.
TEST_FILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'test_files')

# An example fuzzer that triggers an crash.
# Binary is a copy of the example project's do_stuff_fuzzer and can be
# generated by running "python3 infra/helper.py build_fuzzers example".
EXAMPLE_CRASH_FUZZER = 'example_crash_fuzzer'

# An example fuzzer that does not trigger a crash.
# Binary is a modified version of example project's do_stuff_fuzzer. It is
# created by removing the bug in my_api.cpp.
EXAMPLE_NOCRASH_FUZZER = 'example_nocrash_fuzzer'

# A fuzzer to be built in build_fuzzers integration tests.
EXAMPLE_BUILD_FUZZER = 'do_stuff_fuzzer'

MEMORY_FUZZER_DIR = os.path.join(TEST_FILES_PATH, 'memory')
MEMORY_FUZZER = 'curl_fuzzer_memory'

UNDEFINED_FUZZER_DIR = os.path.join(TEST_FILES_PATH, 'undefined')
UNDEFINED_FUZZER = 'curl_fuzzer_undefined'

# pylint: disable=no-self-use,protected-access,too-few-public-methods


def create_config(**kwargs):
  """Creates a config object and then sets every attribute that is a key in
  |kwargs| to the corresponding value. Asserts that each key in |kwargs| is an
  attribute of Config."""
  with mock.patch('os.path.basename', return_value=None), mock.patch(
      'config_utils.get_project_src_path',
      return_value=None), mock.patch('config_utils._is_dry_run',
                                     return_value=True):
    config = config_utils.Config()

  for key, value in kwargs.items():
    assert hasattr(config, key), 'Config doesn\'t have attribute: ' + key
    setattr(config, key, value)
  return config


class BuildFuzzersTest(unittest.TestCase):
  """Unit tests for build_fuzzers."""

  @mock.patch('build_specified_commit.detect_main_repo',
              return_value=('example.com', '/path'))
  @mock.patch('repo_manager._clone', return_value=None)
  @mock.patch('cifuzz.checkout_specified_commit')
  @mock.patch('helper.docker_run')
  def test_cifuzz_env_var(self, mocked_docker_run, _, __, ___):
    """Tests that the CIFUZZ env var is set."""

    with tempfile.TemporaryDirectory() as tmp_dir:
      cifuzz.build_fuzzers(
          create_config(project_name=EXAMPLE_PROJECT,
                        project_repo_name=EXAMPLE_PROJECT,
                        workspace=tmp_dir,
                        pr_ref='refs/pull/1757/merge'))
    docker_run_command = mocked_docker_run.call_args_list[0][0][0]

    def command_has_env_var_arg(command, env_var_arg):
      for idx, element in enumerate(command):
        if idx == 0:
          continue

        if element == env_var_arg and command[idx - 1] == '-e':
          return True
      return False

    self.assertTrue(command_has_env_var_arg(docker_run_command, 'CIFUZZ=True'))


class InternalGithubBuilderTest(unittest.TestCase):
  """Tests for building OSS-Fuzz projects on GitHub actions."""
  PROJECT_NAME = 'myproject'
  PROJECT_REPO_NAME = 'myproject'
  SANITIZER = 'address'
  COMMIT_SHA = 'fake'
  PR_REF = 'fake'

  def _create_builder(self, tmp_dir):
    """Creates an InternalGithubBuilder and returns it."""
    config = create_config(project_name=self.PROJECT_NAME,
                           project_repo_name=self.PROJECT_REPO_NAME,
                           workspace=tmp_dir,
                           sanitizer=self.SANITIZER,
                           commit_sha=self.COMMIT_SHA,
                           pr_ref=self.PR_REF)
    return cifuzz.InternalGithubBuilder(config)

  @mock.patch('repo_manager._clone', side_effect=None)
  @mock.patch('cifuzz.checkout_specified_commit', side_effect=None)
  def test_correct_host_repo_path(self, _, __):
    """Tests that the correct self.host_repo_path is set by
    build_image_and_checkout_src. Specifically, we want the name of the
    directory the repo is in to match the name used in the docker
    image/container, so that it will replace the host's copy properly."""
    image_repo_path = '/src/repo_dir'
    with tempfile.TemporaryDirectory() as tmp_dir, mock.patch(
        'build_specified_commit.detect_main_repo',
        return_value=('inferred_url', image_repo_path)):
      builder = self._create_builder(tmp_dir)
      builder.build_image_and_checkout_src()

    self.assertEqual(os.path.basename(builder.host_repo_path),
                     os.path.basename(image_repo_path))


@unittest.skipIf(not os.getenv('INTEGRATION_TESTS'),
                 'INTEGRATION_TESTS=1 not set')
class BuildFuzzersIntegrationTest(unittest.TestCase):
  """Integration tests for build_fuzzers."""

  def setUp(self):
    test_helpers.patch_environ(self)

  def test_external_project(self):
    """Tests building fuzzers from an external project."""
    project_name = 'external-project'
    project_src_path = os.path.join(TEST_FILES_PATH, project_name)
    build_integration_path = os.path.join(project_src_path, 'oss-fuzz')
    with tempfile.TemporaryDirectory() as tmp_dir:
      out_path = os.path.join(tmp_dir, 'out')
      os.mkdir(out_path)
      config = create_config(project_name=project_name,
                             project_repo_name=project_name,
                             workspace=tmp_dir,
                             project_src_path=project_src_path,
                             build_integration_path=build_integration_path,
                             commit_sha='HEAD')
      self.assertTrue(cifuzz.build_fuzzers(config))
      self.assertTrue(
          os.path.exists(os.path.join(out_path, EXAMPLE_BUILD_FUZZER)))

  def test_valid_commit(self):
    """Tests building fuzzers with valid inputs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      out_path = os.path.join(tmp_dir, 'out')
      os.mkdir(out_path)
      config = create_config(
          project_name=EXAMPLE_PROJECT,
          project_repo_name='oss-fuzz',
          workspace=tmp_dir,
          commit_sha='0b95fe1039ed7c38fea1f97078316bfc1030c523')
      self.assertTrue(cifuzz.build_fuzzers(config))

      self.assertTrue(
          os.path.exists(os.path.join(out_path, EXAMPLE_BUILD_FUZZER)))

  def test_valid_pull_request(self):
    """Tests building fuzzers with valid pull request."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      out_path = os.path.join(tmp_dir, 'out')
      os.mkdir(out_path)
      # TODO(metzman): What happens when this branch closes?
      config = create_config(project_name=EXAMPLE_PROJECT,
                             project_repo_name='oss-fuzz',
                             workspace=tmp_dir,
                             pr_ref='refs/pull/1757/merge',
                             base_ref='master')
      self.assertTrue(cifuzz.build_fuzzers(config))
      self.assertTrue(
          os.path.exists(os.path.join(out_path, EXAMPLE_BUILD_FUZZER)))

  def test_invalid_pull_request(self):
    """Tests building fuzzers with invalid pull request."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      out_path = os.path.join(tmp_dir, 'out')
      os.mkdir(out_path)
      config = create_config(project_name=EXAMPLE_PROJECT,
                             project_repo_name='oss-fuzz',
                             workspace=tmp_dir,
                             pr_ref='ref-1/merge',
                             base_ref='master')
      self.assertTrue(cifuzz.build_fuzzers(config))

  def test_invalid_project_name(self):
    """Tests building fuzzers with invalid project name."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      config = create_config(
          project_name='not_a_valid_project',
          project_repo_name='oss-fuzz',
          workspace=tmp_dir,
          commit_sha='0b95fe1039ed7c38fea1f97078316bfc1030c523')
      self.assertFalse(cifuzz.build_fuzzers(config))

  def test_invalid_repo_name(self):
    """Tests building fuzzers with invalid repo name."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      config = create_config(
          project_name=EXAMPLE_PROJECT,
          project_repo_name='not-real-repo',
          workspace=tmp_dir,
          commit_sha='0b95fe1039ed7c38fea1f97078316bfc1030c523')
      self.assertFalse(cifuzz.build_fuzzers(config))

  def test_invalid_commit_sha(self):
    """Tests building fuzzers with invalid commit SHA."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      config = create_config(project_name=EXAMPLE_PROJECT,
                             project_repo_name='oss-fuzz',
                             workspace=tmp_dir,
                             commit_sha='')
      with self.assertRaises(AssertionError):
        cifuzz.build_fuzzers(config)

  def test_invalid_workspace(self):
    """Tests building fuzzers with invalid workspace."""
    config = create_config(
        project_name=EXAMPLE_PROJECT,
        project_repo_name='oss-fuzz',
        workspace='not/a/dir',
        commit_sha='0b95fe1039ed7c38fea1f97078316bfc1030c523')
    self.assertFalse(cifuzz.build_fuzzers(config))


class RunFuzzerIntegrationTestMixin:  # pylint: disable=too-few-public-methods,invalid-name
  """Mixin for integration test classes that runbuild_fuzzers on builds of a
  specific sanitizer."""
  # These must be defined by children.
  FUZZER_DIR = None
  FUZZER = None

  def _test_run_with_sanitizer(self, fuzzer_dir, sanitizer):
    """Calls run_fuzzers on fuzzer_dir and |sanitizer| and asserts
    the run succeeded and that no bug was found."""
    with test_helpers.temp_dir_copy(fuzzer_dir) as fuzzer_dir_copy:
      run_success, bug_found = cifuzz.run_fuzzers(10,
                                                  fuzzer_dir_copy,
                                                  'curl',
                                                  sanitizer=sanitizer)
    self.assertTrue(run_success)
    self.assertFalse(bug_found)


class RunMemoryFuzzerIntegrationTest(RunFuzzerIntegrationTestMixin,
                                     unittest.TestCase):
  """Integration test for build_fuzzers with an MSAN build."""
  FUZZER_DIR = MEMORY_FUZZER_DIR
  FUZZER = MEMORY_FUZZER

  @unittest.skipIf(not os.getenv('INTEGRATION_TESTS'),
                   'INTEGRATION_TESTS=1 not set')
  def test_run_with_memory_sanitizer(self):
    """Tests run_fuzzers with a valid MSAN build."""
    self._test_run_with_sanitizer(self.FUZZER_DIR, 'memory')


class RunUndefinedFuzzerIntegrationTest(RunFuzzerIntegrationTestMixin,
                                        unittest.TestCase):
  """Integration test for build_fuzzers with an UBSAN build."""
  FUZZER_DIR = UNDEFINED_FUZZER_DIR
  FUZZER = UNDEFINED_FUZZER

  @unittest.skipIf(not os.getenv('INTEGRATION_TESTS'),
                   'INTEGRATION_TESTS=1 not set')
  def test_run_with_undefined_sanitizer(self):
    """Tests run_fuzzers with a valid UBSAN build."""
    self._test_run_with_sanitizer(self.FUZZER_DIR, 'undefined')


class RunAddressFuzzersIntegrationTest(RunFuzzerIntegrationTestMixin,
                                       unittest.TestCase):
  """Integration tests for build_fuzzers with an ASAN build."""

  @unittest.skipIf(not os.getenv('INTEGRATION_TESTS'),
                   'INTEGRATION_TESTS=1 not set')
  def test_new_bug_found(self):
    """Tests run_fuzzers with a valid ASAN build."""
    # Set the first return value to True, then the second to False to
    # emulate a bug existing in the current PR but not on the downloaded
    # OSS-Fuzz build.
    with mock.patch.object(fuzz_target.FuzzTarget,
                           'is_reproducible',
                           side_effect=[True, False]):
      run_success, bug_found = cifuzz.run_fuzzers(10, TEST_FILES_PATH,
                                                  EXAMPLE_PROJECT)
      build_dir = os.path.join(TEST_FILES_PATH, 'out', 'oss_fuzz_latest')
      self.assertTrue(os.path.exists(build_dir))
      self.assertNotEqual(0, len(os.listdir(build_dir)))
      self.assertTrue(run_success)
      self.assertTrue(bug_found)

  @unittest.skipIf(not os.getenv('INTEGRATION_TESTS'),
                   'INTEGRATION_TESTS=1 not set')
  def test_old_bug_found(self):
    """Tests run_fuzzers with a bug found in OSS-Fuzz before."""
    with mock.patch.object(fuzz_target.FuzzTarget,
                           'is_reproducible',
                           side_effect=[True, True]):
      run_success, bug_found = cifuzz.run_fuzzers(10, TEST_FILES_PATH,
                                                  EXAMPLE_PROJECT)
      build_dir = os.path.join(TEST_FILES_PATH, 'out', 'oss_fuzz_latest')
      self.assertTrue(os.path.exists(build_dir))
      self.assertNotEqual(0, len(os.listdir(build_dir)))
      self.assertTrue(run_success)
      self.assertFalse(bug_found)

  def test_invalid_build(self):
    """Tests run_fuzzers with an invalid ASAN build."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      out_path = os.path.join(tmp_dir, 'out')
      os.mkdir(out_path)
      run_success, bug_found = cifuzz.run_fuzzers(10, tmp_dir, EXAMPLE_PROJECT)
    self.assertFalse(run_success)
    self.assertFalse(bug_found)

  def test_invalid_fuzz_seconds(self):
    """Tests run_fuzzers with an invalid fuzz seconds."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      out_path = os.path.join(tmp_dir, 'out')
      os.mkdir(out_path)
      run_success, bug_found = cifuzz.run_fuzzers(0, tmp_dir, EXAMPLE_PROJECT)
    self.assertFalse(run_success)
    self.assertFalse(bug_found)

  def test_invalid_out_dir(self):
    """Tests run_fuzzers with an invalid out directory."""
    run_success, bug_found = cifuzz.run_fuzzers(10, 'not/a/valid/path',
                                                EXAMPLE_PROJECT)
    self.assertFalse(run_success)
    self.assertFalse(bug_found)


class ParseOutputTest(unittest.TestCase):
  """Tests parse_fuzzer_output."""

  def test_parse_valid_output(self):
    """Checks that the parse fuzzer output can correctly parse output."""
    test_output_path = os.path.join(TEST_FILES_PATH,
                                    'example_crash_fuzzer_output.txt')
    test_summary_path = os.path.join(TEST_FILES_PATH, 'bug_summary_example.txt')
    with tempfile.TemporaryDirectory() as tmp_dir:
      with open(test_output_path, 'rb') as test_fuzz_output:
        cifuzz.parse_fuzzer_output(test_fuzz_output.read(), tmp_dir)
      result_files = ['bug_summary.txt']
      self.assertCountEqual(os.listdir(tmp_dir), result_files)

      # Compare the bug summaries.
      with open(os.path.join(tmp_dir, 'bug_summary.txt')) as bug_summary:
        detected_summary = bug_summary.read()
      with open(test_summary_path) as bug_summary:
        real_summary = bug_summary.read()
      self.assertEqual(detected_summary, real_summary)

  def test_parse_invalid_output(self):
    """Checks that no files are created when an invalid input was given."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      cifuzz.parse_fuzzer_output(b'not a valid output_string', tmp_dir)
      self.assertEqual(len(os.listdir(tmp_dir)), 0)


class CheckFuzzerBuildTest(unittest.TestCase):
  """Tests the check_fuzzer_build function in the cifuzz module."""

  def test_correct_fuzzer_build(self):
    """Checks check_fuzzer_build function returns True for valid fuzzers."""
    test_fuzzer_dir = os.path.join(TEST_FILES_PATH, 'out')
    self.assertTrue(cifuzz.check_fuzzer_build(test_fuzzer_dir))

  def test_not_a_valid_fuzz_path(self):
    """Tests that False is returned when a bad path is given."""
    self.assertFalse(cifuzz.check_fuzzer_build('not/a/valid/path'))

  def test_not_a_valid_fuzzer(self):
    """Checks a directory that exists but does not have fuzzers is False."""
    self.assertFalse(cifuzz.check_fuzzer_build(TEST_FILES_PATH))

  @mock.patch('helper.docker_run')
  def test_allow_broken_fuzz_targets_percentage(self, mocked_docker_run):
    """Tests that ALLOWED_BROKEN_TARGETS_PERCENTAGE is set when running
    docker if passed to check_fuzzer_build."""
    mocked_docker_run.return_value = 0
    test_fuzzer_dir = os.path.join(TEST_FILES_PATH, 'out')
    cifuzz.check_fuzzer_build(test_fuzzer_dir,
                              allowed_broken_targets_percentage='0')
    self.assertIn('-e ALLOWED_BROKEN_TARGETS_PERCENTAGE=0',
                  ' '.join(mocked_docker_run.call_args[0][0]))


@unittest.skip('Test is too long to be run with presubmit.')
class BuildSantizerIntegrationTest(unittest.TestCase):
  """Integration tests for the build_fuzzers.
    Note: This test relies on "curl" being an OSS-Fuzz project."""
  PROJECT_NAME = 'curl'
  PR_REF = 'fake_pr'

  @classmethod
  def _create_config(cls, tmp_dir, sanitizer):
    return create_config(project_name=cls.PROJECT_NAME,
                         project_repo_name=cls.PROJECT_NAME,
                         workspace=tmp_dir,
                         pr_ref=cls.PR_REF,
                         sanitizer=sanitizer)

  @parameterized.parameterized.expand([('memory',), ('undefined',)])
  def test_valid_project_curl(self, sanitizer):
    """Tests that MSAN can be detected from project.yaml"""
    with tempfile.TemporaryDirectory() as tmp_dir:
      self.assertTrue(
          cifuzz.build_fuzzers(self._create_config(tmp_dir, sanitizer)))


class GetDockerBuildFuzzersArgsContainerTest(unittest.TestCase):
  """Tests that _get_docker_build_fuzzers_args_container works as intended."""

  def test_get_docker_build_fuzzers_args_container(self):
    """Tests that _get_docker_build_fuzzers_args_container works as intended."""
    out_dir = '/my/out'
    container = 'my-container'
    result = cifuzz._get_docker_build_fuzzers_args_container(out_dir, container)
    self.assertEqual(result, ['-e', 'OUT=/my/out', '--volumes-from', container])


class GetDockerBuildFuzzersArgsNotContainerTest(unittest.TestCase):
  """Tests that _get_docker_build_fuzzers_args_not_container works as
  intended."""

  def test_get_docker_build_fuzzers_args_no_container(self):
    """Tests that _get_docker_build_fuzzers_args_not_container works
    as intended."""
    host_out_dir = '/cifuzz/out'
    host_repo_path = '/host/repo'
    result = cifuzz._get_docker_build_fuzzers_args_not_container(
        host_out_dir, host_repo_path)
    expected_result = [
        '-e', 'OUT=/out', '-v', '/cifuzz/out:/out', '-v',
        '/host/repo:/host/repo'
    ]
    self.assertEqual(result, expected_result)


class GetDockerBuildFuzzersArgsMsanTest(unittest.TestCase):
  """Tests that _get_docker_build_fuzzers_args_msan works as intended."""

  def test_get_docker_build_fuzzers_args_msan(self):
    """Tests that _get_docker_build_fuzzers_args_msan works as intended."""
    work_dir = '/work_dir'
    result = cifuzz._get_docker_build_fuzzers_args_msan(work_dir)
    expected_result = ['-e', 'MSAN_LIBS_PATH=/work_dir/msan']
    self.assertEqual(result, expected_result)


if __name__ == '__main__':
  unittest.main()
