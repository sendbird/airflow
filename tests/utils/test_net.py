# -*- coding: utf-8 -*-
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import unittest
import mock
import six

from airflow.utils import net
from tests.test_utils.config import conf_vars
from airflow.exceptions import AirflowConfigException
import re


def get_hostname():
    return 'awesomehostname'


class GetHostname(unittest.TestCase):

    @mock.patch('airflow.utils.net.socket')
    @mock.patch('airflow.utils.net.conf')
    def test_get_hostname_unset(self, patched_conf, patched_socket):
        patched_conf.get = mock.Mock(return_value=None)
        patched_socket.getfqdn = mock.Mock(return_value='first')
        self.assertTrue(net.get_hostname() == 'first')

    @mock.patch('airflow.utils.net.conf')
    def test_get_hostname_set(self, patched_conf):
        patched_conf.get = mock.Mock(
            return_value='tests.utils.test_net:get_hostname'
        )
        self.assertTrue(net.get_hostname() == 'awesomehostname')

    @conf_vars({('core', 'hostname_callable'): 'tests.utils.test_net'})
    def test_get_hostname_set_incorrect(self):
        with self.assertRaises(TypeError):
            net.get_hostname()

    @mock.patch('airflow.utils.net.conf')
    def test_get_hostname_set_missing(self, patched_conf):
        patched_conf.get = mock.Mock(
            return_value='tests.utils.test_net:missing_func'
        )
        with self.assertRaises(AttributeError):
            net.get_hostname()

    @mock.patch('socket.getfqdn', return_value='first')
    @conf_vars({('core', 'hostname_callable'): None})
    def test_get_hostname_unset_2_0(self, mock_getfqdn):
        self.assertEqual('first', net.get_hostname())

    @conf_vars({('core', 'hostname_callable'): 'tests.utils.test_net.get_hostname'})
    def test_get_hostname_set_2_0(self):
        self.assertEqual('awesomehostname', net.get_hostname())

    @conf_vars({('core', 'hostname_callable'): 'tests.utils.test_net'})
    def test_get_hostname_set_incorrect_2_0(self):
        with self.assertRaises(TypeError):
            net.get_hostname()

    @conf_vars({('core', 'hostname_callable'): 'tests.utils.test_net.missing_func'})
    def test_get_hostname_set_missing_2_0(self):
        with six.assertRaisesRegex(
            self,
            AirflowConfigException,
            re.escape(
                'The object could not be loaded. Please check "hostname_callable" key in "core" section. '
                'Current value: "tests.utils.test_net.missing_func"'
            ),
        ):
            net.get_hostname()
