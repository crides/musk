from functools import reduce
import math
from typing import Callable, Tuple, TypeVar
import pcbnew, cadquery as cq
from kicaq import *

m2_hole_d = 2.2
board = Board("musk.kicad_pcb")

T = TypeVar("T")

def partition(l: list[T], f: Callable[[T], bool]) -> Tuple[list[T], list[T]]:
    t, n = [], []
    for i in l:
        if f(i):
            t.append(i)
        else:
            n.append(i)
    return t, n

def p_sw(sw: pcbnew.FOOTPRINT) -> Tuple[float, float]:
    x, y = board.p(sw.GetPosition())
    diff = 4.35
    match sw.GetOrientationDegrees():
        case 0: return x, y - diff
        case 90: return x + diff, y
        case 180: return x, y + diff
        case 270: return x - diff, y
        case _: raise NotImplementedError()

holes = [board.pos(fp) for fp in board.fps() if fp.GetFPIDAsString() == "MountingHole:MountingHole_2.2mm_M2"]
mouse = board.fps_with_val("PMW3610")[0]
encoder = board.fps_with_val("RotaryEncoder")[0]
thumb_home = board.fp("K14")
edge_holes, outer_edge = partition(board.edges_raw(), lambda e: e.GetShape() == pcbnew.SHAPE_T_RECT)
outer_edge = board.convert_shape(outer_edge)

def gen_bottom():
    mouse_hole = board.layer_of(mouse, pcbnew.Edge_Cuts)
    real_optic_center = board.p(board.layer_raw_of(mouse, pcbnew.Dwgs_User)[0].GetPosition())
    optic_center = board.p(board.layer_raw_of(mouse, pcbnew.Cmts_User)[0].GetPosition())
    avg_center = optic_center[0], (optic_center[1] + real_optic_center[1]) / 2
    keepouts = board.layer(pcbnew.Dwgs_User)
    encoder_court = board.courtyard(encoder).vertices().fillet(2)
    bottom = (cq.Workplane().workplane(offset=-1.6).placeSketch(outer_edge).extrude(-4)
              .moveTo(0, 0).placeSketch(keepouts).cutThruAll()
              .faces(">Z").workplane().placeSketch(encoder_court).cutBlind(-2))

    def cut_at_key(w: cq.Workplane, key: str, ylen: float) -> cq.Workplane:
        return (w.moveTo(*p_sw(board.fp(key)))
                .sketch().rect(12.5, ylen).vertices().fillet(1.5).finalize().cutBlind(-2))
    for key in "5678":
        key = "K" + key
        bottom = cut_at_key(bottom, key, 12.5 * 3)
    thumb_home_pos = p_sw(thumb_home)
    bottom = (bottom.moveTo(thumb_home_pos[0] - 12.5 / 2, thumb_home_pos[1])
              .sketch().rect(12.5 * 2, 12.5).vertices().fillet(1.5).finalize().cutBlind(-2)
              .faces(">Z").workplane()
              .placeSketch(mouse_hole).cutBlind(-2).moveTo(0, 0)
              .placeSketch(board.convert_shape(edge_holes)).cutThruAll()
              .moveTo(*avg_center).slot2D(9 + abs(optic_center[1] - real_optic_center[1]), 6, 90).cutThruAll())
    def gen_led_groove():
        offset = math.sqrt(1 ** 2 - 0.5 ** 2)
        cut = cq.Edge.makeLine((14.5, -8), (6.5, 50.5))
        cut = cq.Edge.makeLine(cut.positionAt(-100), cut.positionAt(100))
        left_wire = (cq.Wire.assembleEdges([e for e in board.edges().faces("<Y").val().outerWire().offset2D(offset)[0]
                                           .split(cut).Edges() if e.Center().x < 3])
                     .translate((0, 0, -0.5 - 1.6)))
        return cq.Workplane("ZY", (-14.5, -8 - offset, -0.5 - 1.6)).circle(1).sweep(left_wire)
    bottom -= gen_led_groove()
    flip = lambda hs: [(h[0], -h[1]) for h in hs]
    bore, hollow = partition(holes, lambda h: bottom.val().facesIntersectedByLine((*h, -100), (0,0,1)) != [])
    bottom = (bottom.faces("<Z").workplane()
            .pushPoints(flip(bore)).cboreHole(m2_hole_d, 5, 2))
    if hollow:
        bottom = bottom.pushPoints(flip(hollow)).hole(5, 10)

    led_hole = cq.Workplane().circle(1.2).extrude(-2).rect(1, 10, centered=(True, False)).extrude(-1.2)
    bottom -= led_hole.translate(board.pos("TP2"))
    bottom -= led_hole.rotate((0,0,0), (0,0,1), 180).translate(board.pos("TP1"))
    return bottom

def gen_mouse_cut():
    k1_p = board.pos("K1")
    comps = [fp for fp in board.fps()
             if not (ref := Board.ref(fp).startswith("K")) and ref not in ["C4", "C13", "BT1", "U8", "REF**", "G***"]
             and (pos := board.pos(fp))[0] > k1_p[0] and pos[1] > k1_p[1]]
    bb = cq.Workplane().placeSketch(*[board.courtyard(fp) for fp in comps]).extrude(2).val().BoundingBox()
    small_comps = cq.Workplane().moveTo(bb.xmin, bb.ymin).rect(bb.xlen, bb.ylen, centered=False).extrude(2.5)
    bb = (cq.Workplane().placeSketch(*[board.courtyard(fp) for fp in [mouse, board.fp("C13")]])
          .extrude(2).val().BoundingBox())
    sensor = (cq.Workplane().moveTo(bb.xmin, bb.ymin).rect(bb.xlen, bb.ylen, centered=False)
                   .extrude(board.height(mouse, 0)))
    bat = board.fp("BT1")
    bat = cq.Workplane().placeSketch(board.courtyard(bat)).extrude(board.height(bat, 0))
    cap = board.pos("C4")
    cap = cq.Workplane().moveTo(cap[0], cap[1] - 2).rect(17, 25, centered=(True, False)).extrude(17)
    return sensor + small_comps + bat + cap

def gen_top():
    screw_r, axle_r = 3, 2.5
    axle_t = 2
    axle_end_t = 2
    axle_or = axle_t + axle_r
    bot_hole, top_hole = sorted([board.pos(fp) for fp in board.fps_with_val("wheel-hole")], key = lambda p: p[1])
    wheel_y = board.pos(encoder)[1]
    holder_base = cq.Sketch().segment((0, 0), (11, 0)).arc((11, -axle_or), axle_or, 90, -180).segment((0, -2 * axle_or)).close().assemble()
    holder = cq.Workplane().transformed(offset=(bot_hole[0], wheel_y + axle_or)).transformed((0, -90, 0)).workplane()
    holder = holder.placeSketch(holder_base).extrude(-axle_end_t) + holder.placeSketch(holder_base.push([(11, -axle_or)]).circle(axle_r, mode="s")).extrude(-screw_r * 2)
    groups = [
        ("R2", "R3", "R4", "R5", "R6"),
        ("U3", "C3", "C9"),
        ("R1", "C2", "L1"),
        ("R10", "R9", "J2"),
        ("JP1", "JP2"), ("C16", "U4"),
        ("U5", "C4", "C5", "C6", "R7", "R8"),
        ("Q1", "R15", "R16"),
    ]
    # right_board = board.layer_raw(pcbnew.Cmts_User)[0]
    right_edge = board.x(min(g.GetStartX() for g in board.layer_raw_of("K1", pcbnew.Dwgs_User))) - 0.2
    bot_edge = board.y(max(g.GetStartY() for g in board.layer_raw_of(thumb_home, pcbnew.Dwgs_User)))
    boundary = outer_edge.push([(-50 + right_edge, 50 + bot_edge)]).rect(100, 100, mode="i")
    top = (cq.Workplane().placeSketch(boundary).extrude(5).faces(">Z").workplane()
           .pushPoints([bot_hole, top_hole]).cboreHole(m2_hole_d, 5, 3)
           .moveTo(0, 0) + holder)
    wheel_hole = max(edge_holes, key=lambda r: r.GetCenter().y)
    top -= cq.Workplane().transformed(offset=(*board.p(wheel_hole.GetCenter()), 11)).transformed((0, 90, 0)).cylinder(iu2mm(abs(wheel_hole.GetStartX() - wheel_hole.GetEndX())), 12.8)
    group_all = [i for g in groups for i in g]
    alone = board.fps_where(lambda fp: board.ref(fp) not in group_all and fp.GetValue() != "wheel-hole")
    for a in alone:
        court = board.layer_of(a, pcbnew.F_CrtYd)
        if court != None:
            height = 20 if board.ref(a) in ["SW2", "J1"] else max(board.height(a, 2), 1)
            top -= cq.Workplane().placeSketch(court).extrude(height)
    for g in groups:
        fps = [board.fp(fp) for fp in g]
        bbs = [fp.GetBoundingBox(False, False) for fp in fps]
        merged = reduce(lambda a, b: a.Merge(b) or a, bbs).getWxRect()
        w, h = iu2mm(merged.GetWidth()), iu2mm(merged.GetHeight())
        pos = board.p(merged.GetPosition())
        pos = pos[0] + w / 2, pos[1] - h / 2        # XXX Somehow this is not centered
        top -= cq.Workplane().placeSketch(cq.Sketch().push([pos]).rect(w, h)).extrude(max(board.max_height({}, 2, fps), 1))
    return top

if "show_object" in locals():
    bottom = gen_bottom()
    cq.Assembly().add(bottom, color=cq.Color("darkseagreen1")).save("bottom.step")
    show_object(bottom)

    # mouse_cut = gen_mouse_cut()
    # show_object(mouse_cut)

    top = gen_top()
    cq.Assembly().add(top, color=cq.Color("darkseagreen1")).save("top.step")
    show_object(top)
