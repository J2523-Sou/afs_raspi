import air_cylinder


def test_button_mapping_uses_r1_for_first_action_and_l1_for_second_action():
    assert air_cylinder._is_pressed([0, 0b00000100], 0b00000100)
    assert air_cylinder._is_pressed([0, 0b00000010], 0b00000010)


def test_payload_uses_default_patterns_from_the_control_table():
    payload = air_cylinder._build_payload([0, 0])

    assert payload == [0, 0, 255, 0, 255, 0, 0, 0]


def test_payload_uses_second_pattern_for_each_cylinder():
    payload = air_cylinder._build_payload([1, 1])

    assert payload == [0, 0, 0, 255, 0, 255, 0, 0]


def test_every_action_pattern_matches_its_output_pair():
    for action_number, (_button, _mask, output_indexes, patterns) in enumerate(
        air_cylinder.CYLINDER_ACTIONS
    ):
        for pattern_number, output_values in enumerate(patterns):
            selected_actions = [0] * len(air_cylinder.CYLINDER_ACTIONS)
            selected_actions[action_number] = pattern_number

            payload = air_cylinder._build_payload(selected_actions)

            assert [payload[index] for index in output_indexes] == list(output_values)
