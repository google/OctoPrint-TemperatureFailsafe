#
# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# coding=utf-8

from __future__ import absolute_import

import octoprint.plugin
from octoprint.util import RepeatedTimer
from easyprocess import EasyProcess

class TemperatureFailsafe(octoprint.plugin.AssetPlugin,
						  octoprint.plugin.SettingsPlugin,
						  octoprint.plugin.ShutdownPlugin,
						  octoprint.plugin.StartupPlugin,
						  octoprint.plugin.TemplatePlugin):

	def __init__(self):
		self._checkTempTimer = None

	def _restartTimer(self):
		# stop the timer
		if self._checkTempTimer:
			self._logger.debug(u"Stopping Timer...")
			self._checkTempTimer.cancel()
			self._checkTempTimer = None

		# start a new timer
		interval = self._settings.get_int(['interval'])
		if self._settings.get_boolean(['enabled']) and interval:
			self._logger.debug(u"Starting Timer...")
			self._checkTempTimer = RepeatedTimer(interval, self.CheckTemps, None, None, True)
			self._checkTempTimer.start()

	def _executeFailsafe(self, env):
		# cancel the print and shut down all the heaters
		# TODO: Wrap in a try/except block to make sure the shell command still runs.
		if self._printer.is_operational():
			if self._printer.is_printing() and self._settings.get_int(['cancel_print']):
					self._logger.error(u"Canceling print")
					# TODO: verify this is async
					self._printer.cancel_print()
			if self._settings.get_int(['disable_heaters']):
				self._logger.error(u"Disabling heaters")
				for k in self._printer.get_current_temperatures().keys():
					# TODO: verify this is async
					self._printer.set_temperature(k, 0)

		# execute the shell command
		cmd = self._settings.get(['command'])

		timeout = self._settings.get_int(['read_timeout'])
		# 0 implies no timeout
		if timeout == 0:
			timeout = None

		if cmd:
			self._logger.info(u"Executing Shell Command: %r" % (cmd,))
			p = EasyProcess(cmd, env=env).call(timeout=timeout)
			# TODO: perform a octoprint popup with the shell command response
			self._logger.info(u"Exit Code from Shell Command: %r" % (p.return_code,))
			self._logger.info(u"Response from Shell Command: %r" % (p.stdout,))

	def CheckTemps(self):
		temps = self._printer.get_current_temperatures()
		self._logger.debug(u"CheckTemps(): %r" % (temps,))
		if not temps:
			self._logger.debug(u"No Temperature Data")
			return

		for k in temps.keys():
			# example dictionary from octoprint
			# {
			#   'bed': {'actual': 0.9, 'target': 0.0, 'offset': 0},
			#   'tool0': {'actual': 0.0, 'target': 0.0, 'offset': 0},
			#   'tool1': {'actual': 0.0, 'target': 0.0, 'offset': 0}
			# }
			if k == 'bed':
				threshold_high = self._settings.get_int(['bed'])
				threshold_low = self._settings.get_int(['bed_low'])
			else:
				threshold_high = self._settings.get_int(['hotend'])
				threshold_low = self._settings.get_int(['hotend_low'])

			violation = False
			errmsg = u"TemperatureFailSafe violation, heater: {heater}: {temp}C {exp} {threshold}C"
			if threshold_high and temps[k]['actual'] > threshold_high:
				errmsg = errmsg.format(heater=k, temp=temps[k]['actual'], exp=">", threshold=threshold_high)
				violation = True

			# only check the low thresholds if we are currently printing, or else ignore it
			if self._printer.is_printing() and threshold_low and temps[k]['actual'] < threshold_low:
				errmsg = errmsg.format(heater=k, temp=temps[k]['actual'], exp="<", threshold=threshold_low)
				violation = True

			if violation:
				# alert the user
				self._logger.error(errmsg)
				self._plugin_manager.send_plugin_message(__plugin_name__, dict(type="popup", msg=errmsg))

				env = {}
				env["TEMPERATURE_FAILSAFE_FAULT_TOOL"] = str(k)
				env["TEMPERATURE_FAILSAFE_FAULT_HIGH_THRESHOLD"] = str(threshold_high)
				env["TEMPERATURE_FAILSAFE_FAULT_LOW_THRESHOLD"] = str(threshold_low)

				# place the temperatures into an environment dictionary to pass to the remote program
				for t in temps.keys():
					env["TEMPERATURE_FAILSAFE_%s_ACTUAL" % t.upper()] = str(temps[t]['actual'])
					env["TEMPERATURE_FAILSAFE_%s_TARGET" % t.upper()] = str(temps[t]['target'])

				self._executeFailsafe(env)

	##-- StartupPlugin hooks

	def on_after_startup(self):
		self._logger.info(u"Starting up...")
		self._restartTimer()

	##-- ShutdownPlugin hooks

	def on_shutdown(self):
		self._logger.info(u"Shutting down...")
		# RepeatedTimer is a daemon thread, and won't block process exit?

	##-- AssetPlugin hooks

	def get_assets(self):
		return dict(js=["js/Temperaturefailsafe.js"])

	##~~ SettingsPlugin mixin

	def get_settings_version(self):
		return 1

	def get_template_configs(self):
		return [
			dict(type="settings", name="Temperature Failsafe", custom_bindings=False)
		]

	def get_settings_defaults(self):
		return dict(
		    enabled=False,
		    interval=5,
		    read_timeout=5,
		    bed=0,
		    bed_low=0,
		    hotend=0,
		    hotend_low=0,
		    command=None,
		    cancel_print=True,
		    disable_heaters=True
		)

	def on_settings_initialized(self):
		self._logger.debug(u"TemperatureFailsafe on_settings_initialized()")
		self._restartTimer()

	def on_settings_save(self, data):
		# make sure we don't get negative values
		for k in ('bed', 'bed_low', 'hotend', 'hotend_low', 'read_timeout', 'interval'):
			if data.get(k): data[k] = max(0, int(data[k]))
		self._logger.debug(u"TemperatureFailsafe on_settings_save(%r)" % (data,))

		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
		self._restartTimer()


	##~~ Softwareupdate hook

	def get_update_information(self):
		return dict(
			emergencyaction=dict(
				displayName="Temperature Failsafe Plugin",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="google",
				repo="OctoPrint-TemperatureFailsafe",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/google/OctoPrint-TemperatureFailsafe/archive/{target_version}.zip"
			)
		)

__plugin_name__ = "TemperatureFailsafe"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = TemperatureFailsafe()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
	}

