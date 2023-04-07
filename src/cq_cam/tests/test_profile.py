import cadquery as cq

from cq_cam.utils.circle_bug_workaround import circle_bug_workaround


def test_circle_bug_workaround():
    wp = cq.Workplane("XY")
    wp = wp.box(1, 1, 1)
    wp = wp.faces(">Z")
    c1_wp = wp.circle(0.75)
    c2_wp = wp.offset2D(0.1)

    # noinspection PyTypeChecker
    circle_bug_workaround(c1_wp.objects[0], c2_wp.objects)
    assert (
        c1_wp.objects[0].location().toTuple() != c2_wp.objects[0].location().toTuple()
    )
