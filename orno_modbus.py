# -*- coding:utf-8 -*-

# Collectd-orno - Collectd plugin for Orno power meters
# Copyleft 2024 - Nicolas AGIUS <nicolas.agius@lps-it.fr>

###########################################################################
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###########################################################################


# Depends on
# pip install pyserial minimalmodbus

# Inspired by https://github.com/gituser-rk/orno-modbus-mqtt
# Only tested with WE-514 and WE-525. Might work with other similar models.

import collectd
import minimalmodbus
import struct
import serial

# Global variables
VERBOSE_LOGGING = False
DEVICE = '/dev/ttyUSB0'
ORNO = None
MODEL = None

def log_verbose(msg):
    if not VERBOSE_LOGGING:
        return
    collectd.info('orno_modbus plugin [verbose]: %s' % msg)

def get_parity(model):
    if model == 'WE-514':
        return serial.PARITY_EVEN
    elif model == 'WE-525':
        return serial.PARITY_NONE
    else:
        collectd.error('orno_modbus plugin: Unknown model %s' % model)
        raise Exception("Configuration error, Unknown model %s" % model)
        
def configure_callback(conf):
    global VERBOSE_LOGGING, DEVICE, MODEL
    for c in conf.children:
        if c.key == 'Verbose':
            VERBOSE_LOGGING = bool(c.values[0])
        elif c.key == 'Device':
            DEVICE = c.values[0]
        elif c.key == 'Model':
            MODEL = c.values[0]
        else:
            collectd.warning ('orno_modbus plugin: Unknown config key: %s.' % c.key)

def init_callback():
    global ORNO

    log_verbose('init callback called')

    # See https://minimalmodbus.readthedocs.io/en/stable/apiminimalmodbus.html
    ORNO = minimalmodbus.Instrument(DEVICE, 1, mode = minimalmodbus.MODE_RTU)
    ORNO.debug = VERBOSE_LOGGING

    # Factory setting for 
    #  - Orno WE-514 : 9600 8E1
    #  - Orno WE-525 : 9600 8N1
    ORNO.serial.baudrate = 9600        
    ORNO.serial.bytesize = 8
    ORNO.serial.parity   = get_parity(MODEL)
    ORNO.serial.stopbits = 1
    ORNO.serial.timeout  = 0.20          # seconds

def shutdown_callback():
    log_verbose('Shutdown callback called')
    ORNO.serial.close()

def dispatch_value(value, name, type):
    log_verbose('Sending value: %s=%s' % (name, value))
    val = collectd.Values(plugin='orno_modbus')
    val.plugin_instance = "orno0"   # TODO manage multiple devices on same bus
    val.type = type
    val.type_instance = name
    val.values = [value]
    val.dispatch()

def convert_to_kWh(energy):
    # Response from meter is: [0, 130, 0, 130, 0, 0, 0, 0, 0, 0]
    # which means: Total Energy 1.3kWh, T1 Energy 1.3kWh, T2 Energy 0.0kWh, T3 Energy 0.0kWh, T4 Energy 0.0kWh

    bits = (energy[0] << 16) + energy[1]	# combining Total Energy valuepair
    s = struct.pack('>i', bits) 			# write to string an interpret as int
    value = struct.unpack('>L', s)[0] 		# extract from string and interpret as unsigned long
    return float(value/100)

def dispatch_we514():
    log_verbose('Dispatch called for WE-514')

    # Frequency (Hz)
    dispatch_value(ORNO.read_register(304, 2, 3, True), 'frequency', 'frequency')

    # Voltage (V)
    dispatch_value(ORNO.read_register(305, 2, 3, True), 'voltage', 'voltage')

    # Current (A)
    dispatch_value(ORNO.read_long(313, 3, False, 0)/1000, 'current', 'current')

    # Active Power (W)
    dispatch_value(ORNO.read_long(320, 3, False, 0), 'active_power', 'power')

    # Reactive Power (Var)
    dispatch_value(ORNO.read_long(328, 3, False, 0), 'reactive_power', 'power')

    # Apparent Power (VA)
    dispatch_value(ORNO.read_long(336, 3, False, 0), 'apparent_power', 'power')

    # Power Factor
    dispatch_value(ORNO.read_register(344, 3, 3, True), 'power_factor', 'gauge')

    # Active Enery (kWh)
    dispatch_value(convert_to_kWh(ORNO.read_registers(40960, 10, 3)), 'active_energy', 'energy')

    # Reactive Enery (kVarh)
    dispatch_value(convert_to_kWh(ORNO.read_registers(40990, 10, 3)), 'reactive_energy', 'energy')

def dispatch_we525():
    log_verbose('Dispatch called for WE-525')

    # Frequency (Hz)
    dispatch_value(ORNO.read_register(266, 1, 3, False), 'frequency', 'frequency')

    # Voltage (V)
    dispatch_value(ORNO.read_long(256, 3, False)/1000, 'voltage', 'voltage')

    # Current (A)
    dispatch_value(ORNO.read_long(258, 3, True)/1000, 'current', 'current')

    # Active Power (W)
    dispatch_value(ORNO.read_long(260, 3, False), 'active_power', 'power')

    # Reactive Power (Var)
    dispatch_value(ORNO.read_long(264, 3, True), 'reactive_power', 'power')

    # Apparent Power (VA)
    dispatch_value(ORNO.read_long(262, 3, True), 'apparent_power', 'power')

    # Power Factor
    dispatch_value(ORNO.read_register(267, 3, 3, True), 'power_factor', 'gauge')

    # Forward Active Enery (kWh)
    dispatch_value(ORNO.read_long(270, 3, False)/100, 'active_energy', 'energy')

    # Forward Reactive Enery (kVarh)
    dispatch_value(ORNO.read_long(304, 3, False)/100, 'reactive_energy', 'energy')

    # Reverse Active Enery (kWh)
    dispatch_value(ORNO.read_long(280, 3, False)/100, 'reverse_active_energy', 'energy')

    # Reverse Reactive Enery (kVarh)
    dispatch_value(ORNO.read_long(310, 3, False)/100, 'reverse_reactive_energy', 'energy')

def read_callback():
    log_verbose('Read callback called')

    if MODEL == 'WE-514':
        dispatch_we514()
    elif MODEL == 'WE-525':
        dispatch_we525()

collectd.register_config(configure_callback)
collectd.register_init(init_callback)
collectd.register_read(read_callback)
collectd.register_shutdown(shutdown_callback)

# vim: ts=4:sw=4:ai
