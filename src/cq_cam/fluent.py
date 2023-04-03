from __future__ import annotations

from copy import copy
from typing import List, Optional

from cadquery import cq

from cq_cam.command import Command
from cq_cam.common import Unit
from cq_cam.operations.profile import profile
from cq_cam.utils.utils import extract_wires, flatten_list
from cq_cam.visualize import visualize_job, visualize_job_as_edges


class Operation:
    def __init__(self, job, name: str, commands: List[Command]):
        self.job = job
        self.name = name
        self.commands = commands

    def to_gcode(self):
        # Set starting position above rapid height so that
        # we guarantee getting the correct Z rapid in the beginning
        position = cq.Vector(0, 0, self.job.rapid_height + 1)
        gcodes = [f'({self.job.name} - {self.name})']
        previous_command = None
        for command in self.commands:
            gcode, position = command.to_gcode(previous_command, position)
            previous_command = command
            gcodes.append(gcode)

        return '\n'.join(gcodes)


class Job:
    def __init__(self,
                 top: cq.Plane,
                 feed: float,
                 tool_diameter: Optional[float] = None,
                 name='Job',
                 plunge_feed: float = None,
                 rapid_height: float = None,
                 op_safe_height: float = None,
                 gcode_precision: int = 3,
                 unit: Unit = Unit.METRIC):
        self.top = top
        self.top_plane_face = cq.Face.makePlane(None, None, top.origin, top.zDir)
        self.feed = feed
        self.tool_diameter = tool_diameter
        self.tool_radius = tool_diameter / 2
        self.name = name
        self.plunge_feed = feed if plunge_feed is None else plunge_feed
        self.rapid_height = self._default_rapid_height(unit) if rapid_height is None else rapid_height
        self.op_safe_height = self._default_op_safe_height(unit) if op_safe_height is None else op_safe_height
        self.gcode_precision = gcode_precision
        self.unit = unit

        self.max_stepdown_count = 100

        self.operations: List[Operation] = []

    @staticmethod
    def _default_rapid_height(unit: Unit):
        if unit == Unit.METRIC:
            return 10
        return 0.4

    @staticmethod
    def _default_op_safe_height(unit: Unit):
        if unit == Unit.METRIC:
            return 1
        return 0.04

    def to_gcode(self):
        task_break = "\n\n\n"

        to_home = f'G1Z0\nG0Z{self.rapid_height}\nX0Y0'
        return (
            f"({self.name} - Feedrate: {self.feed} - Unit: {self.unit})\n"
            f"G90\n"
            f"{self.unit.to_gcode()}\n"
            f"{task_break.join(task.to_gcode() for task in self.operations)}"
            f"{to_home}"
        )

    def show(self, show_object):
        for i, operation in enumerate(self.operations):
            show_object(visualize_job(self.top, operation.commands[1:]), f'{self.name} #{i} {operation.name}')

    def to_shapes(self, as_edges=False):
        if as_edges:
            return flatten_list(
                [visualize_job_as_edges(self.top, operation.commands[1:]) for operation in self.operations])
        return [visualize_job(self.top, operation.commands[1:]) for operation in self.operations]

    def _add_operation(self, name: str, commands: List[Command]):
        job = copy(self)
        job.operations = [*self.operations, Operation(job, name, commands)]
        return job

    def profile(self, shape, outer_offset=None, inner_offset=None, stepdown=None, tabs=None):
        if self.tool_diameter is None:
            raise ValueError('Profile requires tool_diameter to be est')

        if outer_offset is None and inner_offset is None:
            raise ValueError('Set at least one of "outer_offset" or "inner_offset"')
        outer_wires, inner_wires = extract_wires(shape)

        commands = profile(
            job=self,
            outer_wires=outer_wires,
            inner_wires=inner_wires,
            outer_offset=outer_offset,
            inner_offset=inner_offset,
            stepdown=stepdown,
            tabs=tabs
        )
        return self._add_operation('Profile', commands)

    def pocket(self, *args, **kwargs):
        from cq_cam import Pocket
        if self.tool_diameter is None:
            raise ValueError('Profile requires tool_diameter to be est')
        if 'tool_diameter' not in kwargs:
            kwargs['tool_diameter'] = self.tool_diameter
        pocket = Pocket(self, *args, **kwargs)
        return self._add_operation('Pocket', pocket.commands)

    def drill(self, *args, **kwargs):
        from cq_cam import Drill
        drill = Drill(self, *args, **kwargs)
        return self._add_operation('Drill', drill.commands)

    def surface3d(self, *args, **kwargs):
        from cq_cam import Surface3D
        surface3d = Surface3D(self, *args, **kwargs)
        return self._add_operation('Surface 3D', surface3d.commands)
