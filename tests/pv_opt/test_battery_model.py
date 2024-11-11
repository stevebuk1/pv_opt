import pytest
from apps.pv_opt.pvpy import BatteryModel

def test_requires_args():
    # Dummy test to ensure that the pytest setup works.
    with pytest.raises(TypeError):
        BatteryModel()

def test_default_values():
    # Ensure that the default values are set correctly and if they're ever changed, we get a warning with a failing test.
    battery = BatteryModel(capacity=1000)

    assert 0.15 == battery.max_dod
    assert 1000 == battery.capacity
    assert 100 == battery.current_limit_amps
    assert 50 == battery.voltage

def test_max_charge_power_calculated_correctly():
    # Ensure that the charge_power() calculation is correct.
    expected : int = 1250 # 25V * 50A = 1250W
    battery = BatteryModel(capacity=1000, current_limit_amps=50, voltage=25)

    assert expected == battery.max_charge_power

def test_max_discharge_power_calculated_correctly():
    # Ensure that the charge_power() calculation is correct.
    expected : int = 1250 # 25V * 50A = 1250W
    battery = BatteryModel(capacity=1000, current_limit_amps=50, voltage=25)

    assert expected == battery.max_discharge_power