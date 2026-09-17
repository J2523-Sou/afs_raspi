import unittest
from unittest.mock import patch

import air_cylinder as air


class AirCylinderTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.frames = []
        self.start_patch("time.monotonic", lambda: self.now)
        self.start_patch("time.sleep", self.sleep)
        self.start_patch("afs_send", self.send)
        self.start_patch("controller_state.get_values", lambda: [0, 0, 0])
        self.start_patch("controller_state.is_emergency_stopped", lambda: False)
        self.start_patch("_get_fire_permissions", lambda: (True, True))

    def start_patch(self, name, value):
        patcher = patch("air_cylinder." + name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def sleep(self, seconds):
        self.now += seconds

    def send(self, device, payload):
        self.assertEqual(device, air.UART_DEVICE)
        self.frames.append((self.now, list(payload)))

    def test_each_pair_fires_returns_then_turns_off(self):
        for cylinder, first, second in ((1, 2, 3), (2, 4, 5)):
            with self.subTest(cylinder=cylinder):
                self.now = 0.0
                self.frames.clear()
                self.assertTrue(air._fire_and_return(cylinder, 0.25))
                for timestamp, payload in self.frames[:-1]:
                    expected = [0] * 8
                    expected[first if timestamp < air.FIRE_TIME else second] = 255
                    self.assertEqual(payload, expected)
                self.assertEqual(self.frames[0][0], 0.0)
                self.assertIn((air.FIRE_TIME, air._build_action_payload(cylinder, True)), self.frames)
                self.assertEqual(self.frames[-1], (air.FIRE_TIME + air.RETURN_TIME, [0] * 8))

    def test_emergency_and_disconnect_interrupt_before_return(self):
        for cause in ("emergency", "disconnect"):
            with self.subTest(cause=cause):
                self.now = 0.0
                self.frames.clear()
                with patch.object(air.controller_state, "is_emergency_stopped",
                                  lambda: cause == "emergency" and self.now >= 0.25), \
                     patch.object(air.controller_state, "get_values",
                                  lambda: [] if cause == "disconnect" and self.now >= 0.25 else [0, 0, 0]):
                    self.assertFalse(air._fire_and_return(1, 0.25))
                self.assertEqual(self.frames[-1], (0.25, [0] * 8))
                self.assertTrue(all(payload[3] == 0 for _, payload in self.frames))

    def test_uart_error_still_attempts_off(self):
        with patch.object(air, "afs_send", side_effect=[OSError("UART"), None]) as send:
            with self.assertRaises(OSError):
                air._fire_and_return(1, 0.25)
        self.assertEqual(send.call_args_list[-1].args, (air.UART_DEVICE, [0] * 8))

    def test_button_mapping_and_no_repeat_on_hold(self):
        values = [[0, 2, 0], [0, 2, 0], [0, 0, 0], [0, 4, 0]]
        with patch.object(air.controller_state, "get_values", side_effect=values + [KeyboardInterrupt]), \
             patch.object(air, "_fire_and_return", return_value=True) as fire:
            air.run_air_cylinder()
        self.assertEqual([call.args[0] for call in fire.call_args_list], [1, 2])

    def test_button_does_not_fire_without_side_permission(self):
        values = [[0, 2, 0], [0, 4, 0], KeyboardInterrupt]
        with patch.object(air.controller_state, "get_values", side_effect=values), \
             patch.object(air, "_get_fire_permissions", return_value=(False, True)), \
             patch.object(air, "_fire_and_return", return_value=True) as fire:
            air.run_air_cylinder()
        self.assertEqual([call.args[0] for call in fire.call_args_list], [2])

    def test_idle_outputs_are_all_off(self):
        with patch.object(air.controller_state, "get_values", side_effect=[[], KeyboardInterrupt]):
            air.run_air_cylinder()
        self.assertEqual(self.frames, [(0.0, [0] * 8)])


if __name__ == "__main__":
    unittest.main()
