"""Pair one selected device, forwarding BlueZ agent questions to the open panel."""
import json
import signal
import sys

from gi.repository import Gio, GLib, GLibUnix


AGENT = "/org/dotfiles/PairingAgent"
METHODS = {
    "Release": ("", ""), "Cancel": ("", ""),
    "RequestPinCode": ("o", "s"), "DisplayPinCode": ("os", ""),
    "RequestPasskey": ("o", "u"), "DisplayPasskey": ("ouq", ""),
    "RequestConfirmation": ("ou", ""), "RequestAuthorization": ("o", ""),
    "AuthorizeService": ("os", ""),
}


def agent_interface():
    methods = []
    for name, (inputs, outputs) in METHODS.items():
        args = "".join(f'<arg type="{t}" direction="{d}"/>' for d, types in
                       (("in", inputs), ("out", outputs)) for t in types)
        methods.append(f'<method name="{name}">{args}</method>')
    xml = '<node><interface name="org.bluez.Agent1">' + "".join(methods) + '</interface></node>'
    return Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0]


def emit(kind, message):
    print(json.dumps({"kind": kind, "message": message}), flush=True)


class Pairing:
    def __init__(self, path):
        self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        self.loop = GLib.MainLoop()
        self.path = path
        self.pending = None
        self.kind = ""
        self.manager = Gio.DBusProxy.new_sync(self.bus, Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
                                              None, "org.bluez", "/org/bluez", "org.bluez.AgentManager1")

    def agent_call(self, bus, sender, path, interface, method, params, reply):
        values = params.unpack()
        if sender != self.manager.get_name_owner() or (values and values[0] != self.path):
            reply.return_dbus_error("org.bluez.Error.Rejected", "Unexpected pairing request")
            return
        if method in ("Cancel", "Release"):
            self.reject()
            reply.return_value(None)
            return
        if method.startswith("Display"):
            code = values[1] if method == "DisplayPinCode" else f"{values[1]:06d}"
            emit("display", f"Enter {code} on the device.")
            reply.return_value(None)
            return
        self.reject()
        self.pending = reply
        self.kind = method
        if method == "RequestConfirmation":
            emit("confirm", f"Does {values[1]:06d} match the code on your device?")
        elif method in ("RequestPinCode", "RequestPasskey"):
            emit("input", "Enter the PIN shown on the device." if method == "RequestPinCode"
                 else "Enter the six-digit passkey.")
        else:
            emit("confirm", "Allow this device to connect?")

    def reject(self):
        if self.pending:
            self.pending.return_dbus_error("org.bluez.Error.Canceled", "Pairing canceled")
            self.pending = None

    def cancel(self, *_):
        self.reject()
        try:
            self.bus.call_sync("org.bluez", self.path, "org.bluez.Device1", "CancelPairing",
                               None, None, Gio.DBusCallFlags.NONE, 1500, None)
        except GLib.Error:
            pass
        self.loop.quit()
        return False

    def answer(self, source, condition):
        line = sys.stdin.readline()
        if not line:
            return self.cancel()
        value = json.loads(line)
        if value is None:
            return self.cancel()
        if not self.pending:
            return True
        if self.kind == "RequestPasskey":
            if not isinstance(value, str) or not value.isascii() or not value.isdigit() or len(value) > 6:
                emit("input", "Enter a numeric passkey of up to six digits.")
                return True
            result = GLib.Variant("(u)", (int(value),))
        elif self.kind == "RequestPinCode":
            if not isinstance(value, str) or not 1 <= len(value) <= 16:
                emit("input", "Enter a PIN of 1 to 16 characters.")
                return True
            result = GLib.Variant("(s)", (value,))
        elif value is True:
            result = None
        else:
            return self.cancel()
        self.pending.return_value(result)
        self.pending = None
        emit("progress", "Finishing pairing…")
        return True

    def completed(self, bus, result, method):
        try:
            bus.call_finish(result)
        except GLib.Error as error:
            if method == "Connect" and Gio.DBusError.get_remote_error(error) == "org.bluez.Error.AlreadyConnected":
                emit("done", "Paired and connected")
                self.loop.quit()
                return
            emit("error", ("Paired, but connection failed" if method == "Connect" else "Pairing failed")
                 + " · " + (Gio.DBusError.get_remote_error(error) or "Timed out").split(".")[-1])
        else:
            if method == "Pair":
                self.device_call("Connect")
                return
            emit("done", "Paired and connected")
        self.loop.quit()

    def device_call(self, method):
        self.bus.call("org.bluez", self.path, "org.bluez.Device1", method, None, None,
                      Gio.DBusCallFlags.NONE, 90000, None, self.completed, method)

    def run(self):
        self.bus.register_object(AGENT, agent_interface(), self.agent_call)
        self.manager.RegisterAgent("(os)", AGENT, "KeyboardDisplay")
        GLib.io_add_watch(sys.stdin, GLib.PRIORITY_DEFAULT, GLib.IO_IN | GLib.IO_HUP, self.answer)
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.cancel)
        self.device_call("Pair")
        self.loop.run()


if __name__ == "__main__":
    try:
        Pairing(sys.argv[1]).run()
    except GLib.Error:
        emit("error", "Bluetooth is unavailable. Check the adapter and try again.")
        sys.exit(1)
