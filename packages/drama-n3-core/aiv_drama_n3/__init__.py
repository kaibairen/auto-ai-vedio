"""Drama D-N3 unit cards + G3 thin gate + library attach/promote stubs.

Gold-A CHAR look-generate (032) lives here: assemble_gold_a_sheet_prompt +
generate_gold_a_sheet. Split full-body / heads prompts live in split_look
and are not routed through generate-look. SCENE plates live in scene_look
(opt-in generate-scene; name+one_line; role=plate). Does not auto-flip usable_for_n4.
Isolated from koubo-N1 / N4+. Does not expand D-N2 schema.
docs≠PASS. ForcePass=never. G3 pass ≠ usable_for_n4.
"""

__version__ = "0.1.0"
