# created by Tom Stesco tom.s@ecobee.com

import attr
import pandas as pd
import numpy as np

from BuildingControlsSimulator.StateEstimatorModels.StateEstimatorModel import (
    StateEstimatorModel,
)
from BuildingControlsSimulator.DataClients.DataStates import STATES
from BuildingControlsSimulator.Conversions.Conversions import Conversions


@attr.s
class LowPassFilter(StateEstimatorModel):
    """LowPassFilter state estimator model"""

    # default is no filtering, use current measurement 100%
    alpha_temperature = attr.ib(default=1.0)
    alpha_humidity = attr.ib(default=1.0)
    step_output = attr.ib(factory=dict)
    step_size_seconds = attr.ib(default=None)
    current_t_idx = attr.ib(default=None)

    output = attr.ib(factory=dict)

    # for reference on how attr defaults wor for mutable types (e.g. list) see:
    # https://www.attrs.org/en/stable/init.html#defaults
    input_states = attr.ib()
    output_states = attr.ib()

    @input_states.default
    def get_input_states(self):
        return [
            STATES.THERMOSTAT_TEMPERATURE,
            STATES.THERMOSTAT_HUMIDITY,
            STATES.THERMOSTAT_MOTION,
        ]

    @output_states.default
    def get_output_states(self):
        return [
            STATES.THERMOSTAT_TEMPERATURE_ESTIMATE,
            STATES.THERMOSTAT_HUMIDITY_ESTIMATE,
            STATES.THERMOSTAT_MOTION_ESTIMATE,
        ]

    def get_model_name(self):
        _model_name = "LowPass"
        _model_name = _model_name.replace(".", "_")
        return _model_name

    def initialize(
        self,
        start_utc,
        t_start,
        t_end,
        t_step,
        data_spec,
        categories_dict,
    ):
        """"""
        self.current_t_idx = 0
        self.step_size_seconds = t_step
        self.allocate_output_memory(
            t_start=t_start,
            t_end=t_end,
            t_step=t_step,
            data_spec=data_spec,
            categories_dict=categories_dict,
        )
        self.init_step_output()

    def allocate_output_memory(
        self, t_start, t_end, t_step, data_spec, categories_dict
    ):
        """preallocate output memory to speed up simulation"""
        # reset output
        self.output = {}

        self.output = {
            STATES.SIMULATION_TIME: np.arange(
                t_start, t_end + t_step, t_step, dtype="int64"
            )
        }
        n_s = len(self.output[STATES.SIMULATION_TIME])

        # add state variables
        for state in self.output_states:
            if data_spec.full.spec[state]["dtype"] == "category":
                self.output[state] = pd.Series(
                    pd.Categorical(
                        pd.Series(index=np.arange(n_s)),
                        categories=categories_dict[state],
                    )
                )
            else:
                (
                    np_default_value,
                    np_dtype,
                ) = Conversions.numpy_down_cast_default_value_dtype(
                    data_spec.full.spec[state]["dtype"]
                )
                self.output[state] = np.full(
                    n_s,
                    np_default_value,
                    dtype=np_dtype,
                )

        self.output[STATES.STEP_STATUS] = np.full(n_s, 0, dtype="int8")

    def tear_down(self):
        """tear down FMU"""
        pass

    def init_step_output(self):
        # initialize all off
        self.step_output = {state: None for state in self.output_states}

    def calc_t_control(self, step_sensor_input):
        t_ctrl = step_sensor_input[STATES.THERMOSTAT_TEMPERATURE]
        return t_ctrl

    @staticmethod
    def filter(state, prev_state_estimate, alpha):
        if prev_state_estimate:
            # y[i] := y[i-1] + α * (x[i] - y[i-1])
            state_estimate = prev_state_estimate + alpha * (state - prev_state_estimate)
        else:
            # cold start
            state_estimate = state
        return state_estimate

    def do_step(
        self,
        t_start,
        t_step,
        step_sensor_input,
    ):
        """Simulate controller time step."""
        self.step_output[STATES.STEP_STATUS] = 1

        self.step_output[STATES.THERMOSTAT_TEMPERATURE_ESTIMATE] = LowPassFilter.filter(
            state=step_sensor_input[STATES.THERMOSTAT_TEMPERATURE],
            prev_state_estimate=self.step_output[
                STATES.THERMOSTAT_TEMPERATURE_ESTIMATE
            ],
            alpha=self.alpha_temperature,
        )

        self.step_output[STATES.THERMOSTAT_HUMIDITY_ESTIMATE] = LowPassFilter.filter(
            state=step_sensor_input[STATES.THERMOSTAT_HUMIDITY],
            prev_state_estimate=self.step_output[STATES.THERMOSTAT_HUMIDITY_ESTIMATE],
            alpha=self.alpha_temperature,
        )

        # non filtered states
        self.step_output[STATES.THERMOSTAT_MOTION_ESTIMATE] = step_sensor_input[
            STATES.THERMOSTAT_MOTION
        ]

        self.step_output[STATES.STEP_STATUS] = 0
        self.add_step_to_output(self.step_output)
        self.current_t_idx += 1

        return self.step_output[STATES.STEP_STATUS]

    def add_step_to_output(self, step_output):
        for k, v in step_output.items():
            self.output[k][self.current_t_idx] = v

    def change_settings(self, new_settings):
        # this model has no settings
        pass
