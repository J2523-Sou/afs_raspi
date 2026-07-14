import unittest
from unittest.mock import patch

from cylinder import (
    TRIGGER_THRESHOLD,
    _get_values,
    build_pic_payload,
    cylinder_pwm_from_triggers,
    send_pic_payload,
)


class CylinderControlTests(unittest.TestCase):
    def test_truth_table(self):
        self.assertEqual(cylinder_pwm_from_triggers(0.0, 1.0), (255, 0))
        self.assertEqual(cylinder_pwm_from_triggers(1.0, 0.0), (0, 255))
        self.assertEqual(cylinder_pwm_from_triggers(0.0, 0.0), (0, 0))
        self.assertEqual(cylinder_pwm_from_triggers(1.0, 1.0), (0, 0))

    def test_threshold_is_inclusive(self):
        below = TRIGGER_THRESHOLD - 0.001
        self.assertEqual(cylinder_pwm_from_triggers(below, below), (0, 0))
        self.assertEqual(cylinder_pwm_from_triggers(0.0, TRIGGER_THRESHOLD), (255, 0))
        self.assertEqual(cylinder_pwm_from_triggers(TRIGGER_THRESHOLD, 0.0), (0, 255))

    def test_payload_uses_pwm3_and_pwm4(self):
        base = [0, 0, 0, 128, 128, 128, 128]
        self.assertEqual(build_pic_payload(base + [0, 255])[2:4], [255, 0])
        self.assertEqual(build_pic_payload(base + [255, 0])[2:4], [0, 255])
        self.assertEqual(build_pic_payload(base + [255, 255])[2:4], [0, 0])

    def test_pwm3_and_pwm4_are_never_high_together(self):
        base = [0, 0, 0, 128, 128, 128, 128]
        for l2 in range(256):
            for r2 in range(256):
                pwm3, pwm4 = build_pic_payload(base + [l2, r2])[2:4]
                self.assertFalse(pwm3 and pwm4)

    def test_legacy_state_without_analog_triggers_stops(self):
        self.assertEqual(build_pic_payload(list(range(1, 8)))[2:4], [0, 0])

    @patch("cylinder.controller_state.get_values", return_value=[1, 2, 3])
    def test_values_are_read_from_controller_state(self, mock_get_values):
        self.assertEqual(_get_values(), [1, 2, 3])
        mock_get_values.assert_called_once_with()

    @patch("cylinder.afs_uart")
    def test_payload_is_sent_with_shared_afs_uart(self, mock_afs_uart):
        payload = [0, 0, 255, 0, 0, 0, 0, 0]
        send_pic_payload(payload)
        mock_afs_uart.assert_called_once_with(2, payload)


if __name__ == "__main__":
    unittest.main()
