#!/bin/bash

set -e

top=10
vmid=30
bottom=120

left=50
hmid1=88
hmid2=130
right=167

kikit_rect() {
    echo "rectangle; tlx: ${1}mm; tly: ${2}mm; brx: ${3}mm; bry: ${4}mm"
}

kikit separate -s "$(kikit_rect $left $vmid $right $bottom)" musk.kicad_pcb main.kicad_pcb
kibot -e musk.kicad_sch -b main.kicad_pcb jlc-gerbers jlc-drill jlc jlc-pos jlc-bom
kikit separate -s "$(kikit_rect $left $top $hmid1 $vmid)" musk.kicad_pcb left.kicad_pcb
kibot -e musk.kicad_sch -b left.kicad_pcb jlc-gerbers jlc-drill jlc
kikit separate -s "$(kikit_rect $hmid1 $top $hmid2 $vmid)" musk.kicad_pcb top.kicad_pcb
kibot -e musk.kicad_sch -b top.kicad_pcb jlc-gerbers jlc-drill jlc
kikit separate -s "$(kikit_rect $hmid2 $top $right $vmid)" musk.kicad_pcb right.kicad_pcb
kibot -e musk.kicad_sch -b right.kicad_pcb jlc-gerbers jlc-drill jlc
rm {main,left,top,right}.kicad_*

python - <<EOF
from case import *
cq.Assembly().add(gen_bottom(), color=cq.Color("darkseagreen1")).save("bottom.step")
cq.Assembly().add(gen_top(), color=cq.Color("darkseagreen1")).save("top.step")
EOF
