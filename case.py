from typing import Callable, Tuple
import pcbnew, cadquery as cq
from kicaq import *

m2_hole_d = 2.2
board = Board("musk.kicad_pcb")

def partition(l: list, f: Callable[..., bool]) -> Tuple[list, list]:
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
mouse = [fp for fp in board.fps() if fp.GetValue() == "PMW3610"][0]
encoder = [fp for fp in board.fps() if fp.GetValue() == "RotaryEncoder"][0]

def gen_bottom():
    edge_holes, outer_edge = [board.convert_shape(es) for es in partition(board.edges_raw(), lambda e: e.GetShape() == pcbnew.SHAPE_T_RECT)]
    mouse_hole = board.layer_of(mouse, pcbnew.Edge_Cuts)
    real_optic_center = board.p(board.layer_raw_of(mouse, pcbnew.Dwgs_User)[0].GetPosition())
    optic_center = board.p(board.layer_raw_of(mouse, pcbnew.Cmts_User)[0].GetPosition())
    avg_center = optic_center[0], (optic_center[1] + real_optic_center[1]) / 2
    keepouts = board.layer(pcbnew.Dwgs_User)
    encoder_court = board.courtyard(encoder).vertices().fillet(2)
    bottom = (cq.Workplane().workplane(offset=-1.6).placeSketch(outer_edge).extrude(-4)
              .moveTo(0, 0).placeSketch(keepouts).cutThruAll()
              .faces(">Z").workplane().placeSketch(encoder_court).cutBlind(-2)
              .moveTo(*board.pos("C4")).rect(11, 4, centered=True).cutBlind(-2))

    def cut_at_key(w: cq.Workplane, key: str, ylen: float) -> cq.Workplane:
        return (w.moveTo(*p_sw(board.fp(key)))
                .sketch().rect(12.5, ylen).vertices().fillet(1.5).finalize().cutBlind(-2))
    for key in "5678":
        key = "K" + key
        bottom = cut_at_key(bottom, key, 12.5 * 3)
    thumb_home = p_sw(board.fp("K14"))
    bottom = (bottom.moveTo(thumb_home[0] - 12.5 / 2, thumb_home[1])
              .sketch().rect(12.5 * 2, 12.5).vertices().fillet(1.5).finalize().cutBlind(-2)
              .faces(">Z").workplane()
              .placeSketch(mouse_hole).cutBlind(-2).moveTo(0, 0)
              .placeSketch(edge_holes).cutThruAll()
              .moveTo(*avg_center).slot2D(9 + abs(optic_center[1] - real_optic_center[1]), 6, 90).cutThruAll())
    flip = lambda hs: [(h[0], -h[1]) for h in hs]
    bore, hollow = partition(holes, lambda h: bottom.val().facesIntersectedByLine((*h, -100), (0,0,1)))
    return (bottom.faces("<Z").workplane()
            .pushPoints(flip(bore)).cboreHole(m2_hole_d, 5, 2)
            .pushPoints(flip(hollow)).hole(5, 10))

def gen_wheel_holder():
    screw_r, axle_r = 3, 2.5
    axle_t = 2
    axle_end_t = 1
    axle_or = axle_t + axle_r
    bot_hole, top_hole = sorted([board.pos(fp) for fp in board.fps() if fp.GetValue() == "wheel-hole"],
                                key = lambda p: p[1])
    wheel_y = board.pos(encoder)[1]
    holder = cq.Sketch().segment((0, 0), (11, 0)).arc((11, -axle_or), axle_or, 90, -180).segment((0, -2 * axle_or)).close().assemble()
    base = (cq.Workplane()
            .moveTo(bot_hole[0] + screw_r, wheel_y + axle_r + axle_t)
            .hLine(-2 * screw_r).vLineTo(top_hole[1] + screw_r).hLineTo(top_hole[0])
            .tangentArcPoint((0, - 2 * screw_r))
            .hLineTo(bot_hole[0] - screw_r).vLineTo(bot_hole[1])
            .tangentArcPoint((2 * screw_r, 0))
            .close().extrude(4)
            .faces(">Z").workplane()
            .pushPoints([bot_hole]).rect(screw_r * 2, screw_r * 2).cutBlind(-2)
            .pushPoints([bot_hole, top_hole]).hole(m2_hole_d, 10)
            .vertices(">Y").vertices("<X and <Z").workplane(centerOption="CenterOfMass").transformed((0, -90, 0)))
    base += base.placeSketch(holder).extrude(-axle_end_t) + base.placeSketch(holder.push([(11, -axle_or)]).circle(axle_r, mode="s")).extrude(-screw_r * 2)
    flash_court = board.courtyard("U1")
    return base - cq.Workplane().placeSketch(flash_court).extrude(board.height("U1", 2))

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

wheel_holder = gen_wheel_holder()
# cq.exporters.export(wheel_holder, "wheel_holder.step")
show_object(wheel_holder)

# bottom = gen_bottom()
# cq.Assembly().add(bottom, color=cq.Color("gray40")).save("bottom.step")
# show_object(bottom)

# mouse_cut = gen_mouse_cut()
# show_object(mouse_cut)
