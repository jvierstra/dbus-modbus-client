import struct

import device
import probe
from register import *


class Reg_Mebay_ident(Reg):
    """The Mebay controller identifies itself by a combination
    of manufacturer code and model number."""

    def __init__(self):
        super().__init__(0x1048, 3)

    def decode(self, values):
        model_number = values[0]
        hw_version = values[1]
        sw_version = values[2]
        ident_str = f"{ model_number }-{ hw_version }-{ sw_version }"
        return self.update(ident_str)

# Mebay alarms code map; only one alarm at a time
alarm_codes = { # 0x1043
    1: "Over speed",
    2: "Under speed",
    3: "Low oil pressure sensor",
    4: "Low oil pressure switch",
    5: "High water temperature sensor",
    6: "High water temperature switch",
    7: "High oil temperature sensor",
    8: "High oil temperature switch",
    17: "Instant alarm switch",
    19: "RPM signal lost",
    20: "Oil pressure sensor open",
    21: "Water temperature sensor open",
    26: "Over frequency",
    27: "Under frequency",
    28: "Over voltage",
    29: "Under voltage",
    30: "Over current",
    32: "Over power",
    39: "Maintenance expire",
    44: "Low water switch level",
    46: "Emergency stop",
    47: "Crank failure",
    48: "Stop failure w/ RPM",
    49: "Stop failure w/ Hz",
    50: "Stop failure w/ oil pressure",
    51: "Stop failure w/ oil pressure switch",
}

warning_code_1 = { # 0x1047
    12: "Low fuel level sensor",
    13: "Low fuel level switch",
}

warning_code_2 = { # 0x1046
    0: "Instant alarm switch",
    2: "RPM signal lost",
    3: "Oil pressure sensor open",
    4: "Water temperature sensor open",
    8: "Fuel level sensor open",
    13: "Over current",
    15: "Over power",
}

warning_code_3 = { # 0x1045
    6: "Maintenance expire",
    12: "Over battery voltage",
    13: "Under battery voltage",
}

class Reg_Mebay_alarms(Reg):
    def __init__(self):
        super().__init__(0x1043, 5)

    def decode(self, values):
        """ Unpack values to unsigned int (16bit)
            0x1043 = alarm code (see dict above)
            0x1044 = warning code 4 (does not exist)
            0x1045 = warning code 3
            0x1046 = warning code 2
            0x1047 = warning code 1 """
        self.update([struct.unpack("H", struct.pack("H", v)) for v in values])

def unpack_bits(val):
    for i in range(15, 0, -1):
        yield (val >> i) & 1

class Mebay_Generator(device.CustomName, device.ErrorId, device.Genset):
    vendor_id = "mebay"
    vendor_name = "Mebay"
    productid = 0xB046
    productname = "Mebay genset controller"
    min_timeout = 1  # Increased timeout for less corrupted messages

    init_status_code = None

    # MEBAY Control Function keys
    SCF_PASSWORD = 7623
    SCF_SELECT_MANUAL_MODE = 0x2222  # Select manual mode
    SCF_SELECT_AUTO_MODE = 0x3333  # Select Auto mode
    SCF_TELEMETRY_START = 0x5555  # Telemetry start if in auto mode
    SCF_TELEMETRY_STOP = 0x1111  # Cancel telemetry start in auto mode

    def __init__(self, *args):
        super().__init__(*args)

        self.running_status_reg = Reg_mapu16(
            0x1041,
            "/StatusCode",
            {
                0: 0,  # Stop idle speed = Stopped
                1: 0,  # Under stop = Stopped
                2: 0,  # Waiting = Stopped
                3: 9,  # Crank cancel = Stopping
                4: 9,  # Crank ready =
                5: 0,  # Alarm reset =
                6: 0,  # Standby = Stopped
                7: 0,  # Pre-heat = Starting
                8: 0,  # Pre-oil supply = Starting
                9: 0,  # Crank delay = Starting
                10: 0,  # Crank ready = Starting
                11: 0,  # In crank = Starting
                12: 0,  # Safety delay = Starting
                13: 0,  # Idle speed = Starting
                14: 0,  # Speed-up = Starting
                15: 0,  # Tempurature-up = Starting
                16: 0,  # Volt-buildup = Starting
                17: 0,  # High-speed warning = Error
                18: 0,  # Rated running = Running
                19: 0,  # Mains revert =
                20: 0,  # Cooling running = Stopping
                21: 0,  # Gen return =
                22: 0,  # Under stop by radiator = Stopping
                23: 0,  # Switching =
            },
        )

        self.engine_speed_reg = Reg_u16(0x1000, "/Engine/Speed", 1, "%.0f RPM")

        self.info_regs = [
            Reg_u16(0x104A, "/FirmwareVersion"),  # Software version
        ]

    def alarm_changed(self, reg):
        eids = []
        # alarms -- shutdown
        if reg.value[0] in alarm_codes:
            eids.append( ("e", reg.value[0]) )
    
        # table 1
        for v in enumerate(unpack_bits(reg.value[4])):
            if v[1]:
                eids.append( ("w", 0x0 + v[0]) )

        # table 2
        for v in enumerate(unpack_bits(reg.value[3])):
            if v[1]:
                eids.append( ("w", 0x10 + v[0]) )

        # table 3
        for v in enumerate(unpack_bits(reg.value[2])):
            if v[1]:
                eids.append( ("w", 0x20 + v[0]))

        # table 4
        for v in enumerate(unpack_bits(reg.value[1])):
            if v[1]:
                eids.append( ("w", 0x30 + v[0]))

        self.set_error_ids(eids)

    def device_init(self):
        self.data_regs = [
            self.running_status_reg,
            Reg_u16(0x101B, "/Ac/Power", 1, "%.0f W"),
            Reg_u16(0x1018, "/Ac/L1/Power", 1, "%.0f W"),
            Reg_u16(0x1019, "/Ac/L2/Power", 1, "%.0f W"),
            Reg_u16(0x101A, "/Ac/L3/Power", 1, "%.0f W"),
            Reg_u16(0x100A, "/Ac/L1/Voltage", 1, "%.0f V"),
            Reg_u16(0x100B, "/Ac/L2/Voltage", 1, "%.0f V"),
            Reg_u16(0x100C, "/Ac/L3/Voltage", 1, "%.0f V"),
            Reg_u16(0x1010, "/Ac/L1/Current", 1, "%.0f A"),
            Reg_u16(0x1011, "/Ac/L2/Current", 1, "%.0f A"),
            Reg_u16(0x1012, "/Ac/L3/Current", 1, "%.0f A"),
            Reg_u16(0x1009, "/Ac/Frequency", 10, "%.1f Hz"),
            self.engine_speed_reg,
            Reg_u16(0x1054, "/Engine/CoolantTemperature", 1, "%.1f C"),
            Reg_u16(0x1053, "/Engine/OilPressure", 1, "%.0f kPa"),
            Reg_u16(0x1039, "/Engine/Load", 1, "%.0f %%"),
            Reg_u16(0x1035, "/Engine/Starts", 1, "%.0f"),
            Reg_u32b(0x1036, "/Engine/OperatingHours", 1 / 3600, "%.1f s"),
            Reg_u16(0x1001, "/StarterVoltage", 10, "%.1f V"),
            Reg_map(
                0x103F,
                "/RemoteStartModeEnabled",
                {
                    0x0033: 0,  # Stop mode
                    0x0066: 0,  # Manual mode
                    0x0099: 1,  # Auto mode
                    0x00CC: 0,  # Test on load mode
                },
            ),

            Reg_Mebay_alarms(),
        ]

        # Check, if status register is implemented on controller
        self.init_status_code = self.read_register(self.running_status_reg)

    def device_init_late(self):
        super().device_init_late()

        # Additional static paths
        if "/FirmwareVersion" not in self.dbus:
            self.dbus.add_path("/FirmwareVersion", None)

        is_running = self.init_status_code > 0

        # Add /Start path, if GenComm System Control Functions
        self.dbus.add_path(
            "/Start",
            1 if is_running else 0,
            writeable=True,
            onchangecallback=self._start_genset,
        )

        # Add /EnableRemoteStartMode path, if GenComm System Control Function
        self.dbus.add_path(
            "/EnableRemoteStartMode",
            0,
            writeable=True,
            onchangecallback=self._set_remote_start_mode,
        )

    def _start_genset(self, _, value):
        if value:
            self.modbus.write_registers(
                0x2000, [self.SCF_PASSWORD, self.SCF_TELEMETRY_START], unit=self.unit
            )
        else:
            self.modbus.write_registers(
                0x2000, [self.SCF_PASSWORD, self.SCF_TELEMETRY_STOP], unit=self.unit
            )
        return True

    def _set_remote_start_mode(self, _, value):
        if value == 1:
            self.modbus.write_registers(
                0x2000, [self.SCF_PASSWORD, self.SCF_SELECT_AUTO_MODE], unit=self.unit
            )
        return True


class Mebay_DC40x_Generator(Mebay_Generator):
    pass

models = {
    "1-4623": {
        "model": "DC40x",
        "handler": Mebay_DC40x_Generator,
    },
}


probe.add_handler(
    probe.ModelRegister(Reg_Mebay_ident(), models, methods=["rtu"], units=[16])
)
