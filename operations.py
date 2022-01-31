from dataclasses import dataclass
from typing import List, Union, Tuple

import numpy as np
import pyclipper
from cadquery import cq

from base import Task, Unit, Rapid, Plunge, Cut, Job, PlaneNotAligned, OperationError
from utils import is_parallel_plane, flatten_edges


class PlaneValidationMixin:
    @staticmethod
    def validate_plane(job: Job, source_workplane: cq.Workplane):
        face_workplane = source_workplane.workplane()
        if not is_parallel_plane(job.workplane.plane, face_workplane.plane):
            raise OperationError('Face plane is not parallel with job plane')
        return face_workplane, source_workplane

    @staticmethod
    def validate_coplanar(source_workplanes: List[cq.Workplane]):
        # TODO
        objs = [obj for source_workplane in source_workplanes for obj in source_workplane.objects]
        try:
            cq.Workplane().add(objs).workplane()
        except ValueError as ex:
            raise OperationError(*ex.args)


class ObjectsValidationMixin:
    @staticmethod
    def _validate_count(source_workplane: cq.Workplane, count=None):
        if not source_workplane.objects:
            raise OperationError("Empty source workplane")

        if count is not None and len(source_workplane.objects) != count:
            raise OperationError(
                f"Workplane contains incorrect amount of faces (expected {count}, actual {len(source_workplane.objects)}"
            )

    @staticmethod
    def _validate_class(source_workplane: cq.Workplane, cls):
        for workplane_object in source_workplane.objects:
            if not isinstance(workplane_object, cls):
                raise OperationError(f"Workplane has non-{cls.__name__} object(s)")

    def validate_faces(self, source_workplane: cq.Workplane, count=None):
        self._validate_count(source_workplane, count)
        self._validate_class(source_workplane, cq.Face)

    def validate_wires(self, source_workplane: cq.Workplane, count=None):
        self._validate_count(source_workplane, count)
        self._validate_class(source_workplane, cq.Wire)


@dataclass
class Profile(PlaneValidationMixin, ObjectsValidationMixin, Task):
    """
    Create a profile around the outer wire of a given face
    """
    wire: cq.Workplane
    offset: float
    stepdown: Union[float, None]

    def __post_init__(self):
        self.validate_wires(self.wire, 1)
        workplane, _ = self.validate_plane(job, self.wire)

        edges = self.wire.objects[0].Edges()
        vectors = flatten_edges(edges)
        scaled_points = pyclipper.scale_to_clipper(tuple((vector.x, vector.y) for vector in vectors))

        pco = pyclipper.PyclipperOffset()
        pco.AddPath(scaled_points, pyclipper.JT_SQUARE, pyclipper.ET_CLOSEDLINE)

        points = pyclipper.scale_from_clipper(pco.Execute(pyclipper.scale_to_clipper(self.offset)))[0]

        # Render your stuff man!

        visual = workplane.moveTo(points[0][0], points[0][1])
        for sx in points[1:]:
            visual = visual.lineTo(sx[0], sx[1])
        visual = visual.close()


        # TODO collect layers?
        # Generate automatically the motions when moving between layers
        # Also layer entry points etc.
        profile = [Cut(point[0], point[1], None) for point in points]
        bottom_height = 0
        if self.stepdown:

            depths = list(np.arange(self.top_height - self.stepdown, bottom_height, self.stepdown))
            if depths[-1] != bottom_height:
                depths.append(bottom_height)

            for i, depth in enumerate(depths):
                self.commands.append(profile[0])
                self.commands.append(Cut(None, None, depth))
                self.commands += profile[1:]
            self.commands.append(profile[0])
        else:
            self.commands.append(profile[0])
            self.commands.append(Cut(None, None, bottom_height))
            self.commands = profile[1:]
            self.commands.append(profile[0])



        # Construct profile polygons

        # Generate operation layers

        self.job.tasks.append(self)


class Pocket(PlaneValidationMixin, ObjectsValidationMixin, Task):
    def __init__(self, job: Job, obj: Union[cq.Workplane, List[cq.Workplane]]):
        source_workplanes: List[cq.Workplane] = obj if isinstance(obj, list) else [obj]

        # Validate source workplane object stack
        for source_workplane in source_workplanes:
            self.validate_faces(source_workplane)

        # Create face-source workplane pairs
        pairs = [self.validate_plane(job, wp) for wp in source_workplanes]

        # TODO validate faces are co-blah

        # Determine face depths

        # Construct profile polygons

        # Generate operation layers


if __name__ == '__main__':
    """
    commands = [
        Rapid(None, None, 10),
        Rapid(20, 15, 10),
        Rapid(20, 15, 5),
        Plunge(2),
        Cut(15, 10, 2),
        Cut(15, 0, 2),
        Plunge(5),
        Rapid(None, None, 10),
        Rapid(20, 15, 10)

    ]
    """
    box = cq.Workplane().box(10, 10, 10)

    job = Job(box, 300, 50, Unit.METRIC, 15)
    profile = Profile(job, 15, 10, box.wires('>Z'), 3.175 / 2, -2.77)

    print(job.to_gcode())
