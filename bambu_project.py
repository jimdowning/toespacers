"""Write a Bambu Studio project .3mf directly, so opening it in Studio skips
straight to "load these print settings?" instead of importing a bare STL and
having to set nozzle/layer/infill by hand.

This mirrors the exact package structure Bambu Studio itself writes (learned
by inspecting two real examples: `../Fußspreitzer+v2+v4.3mf`, the original
model's own project file, and a version of this project's own generated
output that was opened, mesh-repaired, and re-saved *by Bambu Studio itself*
- see the second design note below) rather than the simpler single-file,
inline-mesh 3MF this module first tried:

- `3D/3dmodel.model` needs an `Application` metadata value that reads as a
  Bambu Studio version (e.g. `BambuStudio-02.07.01.57`) for Studio to
  recognize an incoming file as *one of its own projects* - and therefore
  actually offer to load `Metadata/project_settings.config` - rather than
  just importing bare geometry with a "not from bambulab" warning and the
  currently-active profile.
- Each object's mesh lives in its own `3D/Objects/object_N.model` file,
  referenced from `3dmodel.model` via a `<component>` (the 3MF Production
  Extension, `xmlns:p`, with a UUID on every object/component/build item) -
  not inlined directly into `3dmodel.model`'s own `<resources>`.
- `Metadata/model_settings.config` assigns each object to a filament slot
  (`extruder`) and lists per-object mesh stats - without it, Studio doesn't
  know which slot to print each object with and silently defaults to slot 1
  (harmless here, since slot 1 - `extruder`'s own default - is also the only
  slot a single-filament, no-AMS setup has).

Second design note - the mesh itself: the first version of this module
tessellated each build123d shape face-by-face and wrote every face's
vertices straight through, unshared, exactly like an STL. That's normally
harmless (STL has no shared vertices at all, ever, and every slicer copes),
but a 3MF *indexed* mesh is expected to actually share one vertex index
between adjacent faces at a common edge - leaving it unshared means two
triangles that are geometrically edge-adjacent (same XYZ) don't *look*
adjacent to an index-based mesh checker, since they don't reference the same
vertex. Bambu Studio's own repair, run on a first attempt at this file,
reported thousands of "open edges" on exactly this basis and wasn't wrong -
confirmed by counting edges that appear in only one triangle, both ways: on
the order of 16000 with raw per-face vertices, and exactly 0 once vertices
are deduplicated by rounded position first (see `_dedupe_mesh`). Every mesh
below goes through that dedup before being written.

Third design note - print settings, and where they come from: this module
just clones `Metadata/project_settings.config` from `template_path` and
applies overrides (see `load_print_settings`); it has no opinion on what
printer/process/filament that settings document actually describes. The
default template `generate.py` passes in, `bambu_a1_mini_tpu_settings.json`,
is a *flattened* Bambu Studio settings document (not a .3mf) built for a
Bambu Lab A1 mini with no AMS and a single TPU filament - see the README
("Generating a ready-to-slice Bambu Studio project") for exactly how it was
produced and how to regenerate it against a future Bambu Studio release.
`load_print_settings` accepts either shape (`.json` read directly, `.3mf`
unzipped as before) so an actual reference project.3mf - like the original
`../Fußspreitzer+v2+v4.3mf`, still used above only to learn this module's
package structure, not for its print settings - still works as a template
too.
"""
import datetime
import json
import uuid
import zipfile
from collections import Counter

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD_NS = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
BBL_NS = "http://schemas.bambulab.com/package/2021"

CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
'''

TOP_LEVEL_RELS = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
'''


def _dedupe_mesh(vertices, triangles, precision=6):
    """Merge vertices at (nearly) the same position into one shared index,
    remapping triangles to match - see the module docstring's second design
    note for why this matters. `vertices` is anything with .X/.Y/.Z (e.g.
    build123d Vectors); returns (list[(x, y, z)], list[(i, j, k)])."""
    key_to_index = {}
    merged = []
    remap = []
    for v in vertices:
        key = (round(v.X, precision), round(v.Y, precision), round(v.Z, precision))
        index = key_to_index.get(key)
        if index is None:
            index = len(merged)
            key_to_index[key] = index
            merged.append(key)
        remap.append(index)
    remapped_triangles = [(remap[a], remap[b], remap[c]) for a, b, c in triangles]
    return merged, remapped_triangles


def count_open_edges(triangles):
    """Number of edges used by triangles exactly once - as opposed to
    exactly twice, which every edge of a closed watertight mesh should be.
    Diagnostic only (see module docstring); not called by the writer."""
    edge_uses = Counter()
    for a, b, c in triangles:
        for u, v in ((a, b), (b, c), (c, a)):
            edge_uses[frozenset((u, v))] += 1
    return sum(1 for n in edge_uses.values() if n != 2)


def _place_on_plate(parts, gap=20.0, margin=20.0):
    """Lay `parts` (build123d Shapes) left-to-right along +X, `gap` mm of
    clearance between bounding boxes, each starting at the same Y (`margin`)
    - avoids overlap regardless of each part's actual size, so it doesn't
    need to assume anything about the post layout. Returns a list of
    (tx, ty) translations, one per part, in the same order."""
    x = margin
    placements = []
    for part in parts:
        bb = part.bounding_box()
        tx = x - bb.min.X
        ty = margin - bb.min.Y
        placements.append((tx, ty))
        x += (bb.max.X - bb.min.X) + gap
    return placements


def _object_model_xml(inner_id, obj_uuid, vertices, triangles):
    """The content of one `3D/Objects/object_N.model` component file: a
    single object with an inline, deduplicated mesh."""
    lines = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE_NS}" '
        f'xmlns:BambuStudio="{BBL_NS}" xmlns:p="{PROD_NS}" requiredextensions="p">',
        ' <metadata name="BambuStudio:3mfVersion">1</metadata>',
        ' <resources>',
        f'  <object id="{inner_id}" p:UUID="{obj_uuid}" type="model">',
        '   <mesh>',
        '    <vertices>',
    ]
    for x, y, z in vertices:
        lines.append(f'     <vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>')
    lines.append('    </vertices>')
    lines.append('    <triangles>')
    for a, b, c in triangles:
        lines.append(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>')
    lines += [
        '    </triangles>',
        '   </mesh>',
        '  </object>',
        ' </resources>',
        ' <build/>',
        '</model>',
        '',
    ]
    return '\n'.join(lines)


def _top_model_xml(objects, application, creation_date):
    """`3D/3dmodel.model`: metadata (incl. the `Application` tag Studio
    checks to recognize its own project - see module docstring) plus one
    component-referencing object and one build item per entry in `objects`
    (each a dict with outer_id, inner_id, uuid, component_uuid, item_uuid,
    tx, ty)."""
    lines = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE_NS}" '
        f'xmlns:p="{PROD_NS}" requiredextensions="p" xmlns:BambuStudio="{BBL_NS}">',
        f' <metadata name="Application">{application}</metadata>',
        ' <metadata name="BambuStudio:3mfVersion">1</metadata>',
        ' <metadata name="Copyright"></metadata>',
        f' <metadata name="CreationDate">{creation_date}</metadata>',
        ' <metadata name="Description"></metadata>',
        ' <metadata name="Designer"></metadata>',
        ' <metadata name="DesignerCover"></metadata>',
        ' <metadata name="DesignerUserId"></metadata>',
        ' <metadata name="License"></metadata>',
        f' <metadata name="ModificationDate">{creation_date}</metadata>',
        ' <metadata name="Origin"></metadata>',
        ' <metadata name="ProfileCover"></metadata>',
        ' <metadata name="ProfileDescription"></metadata>',
        ' <metadata name="ProfileTitle"></metadata>',
        ' <metadata name="Title"></metadata>',
        ' <resources>',
    ]
    for o in objects:
        lines.append(f'  <object id="{o["outer_id"]}" p:UUID="{o["uuid"]}" type="model">')
        lines.append('   <components>')
        lines.append(
            f'    <component p:path="/3D/Objects/object_{o["inner_id"]}.model" objectid="{o["inner_id"]}" '
            f'p:UUID="{o["component_uuid"]}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
        )
        lines.append('   </components>')
        lines.append('  </object>')
    lines.append(f' </resources>')
    lines.append(f' <build p:UUID="{uuid.uuid4()}">')
    for o in objects:
        lines.append(
            f'  <item objectid="{o["outer_id"]}" p:UUID="{o["item_uuid"]}" '
            f'transform="1 0 0 0 1 0 0 0 1 {o["tx"]:.6f} {o["ty"]:.6f} 0" printable="1"/>'
        )
    lines.append(' </build>')
    lines.append('</model>')
    lines.append('')
    return '\n'.join(lines)


def _model_settings_xml(objects, extruder):
    """`Metadata/model_settings.config`: per-object name/filament-slot
    assignment and mesh stats, plus the single-plate assembly - without
    this, Studio silently defaults every object to filament slot 1 instead
    of whichever slot `extruder` actually names (a no-op with today's
    single-filament default, but still needed if that ever changes)."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<config>']
    for o in objects:
        lines += [
            f'  <object id="{o["outer_id"]}">',
            f'    <metadata key="name" value="{o["name"]}"/>',
            f'    <metadata key="extruder" value="{extruder}"/>',
            f'    <metadata face_count="{o["ntris"]}"/>',
            f'    <part id="{o["inner_id"]}" subtype="normal_part">',
            f'      <metadata key="name" value="{o["name"]}"/>',
            '      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>',
            '      <metadata key="source_object_id" value="0"/>',
            '      <metadata key="source_volume_id" value="0"/>',
            f'      <mesh_stat face_count="{o["ntris"]}" edges_fixed="0" degenerate_facets="0" '
            'facets_removed="0" facets_reversed="0" backwards_edges="0"/>',
            '    </part>',
            '  </object>',
        ]
    lines.append('  <plate>')
    lines += [
        '    <metadata key="plater_id" value="1"/>',
        '    <metadata key="plater_name" value=""/>',
        '    <metadata key="locked" value="false"/>',
    ]
    for o in objects:
        lines += [
            '    <model_instance>',
            f'      <metadata key="object_id" value="{o["outer_id"]}"/>',
            '      <metadata key="instance_id" value="0"/>',
            '    </model_instance>',
        ]
    lines.append('  </plate>')
    lines.append('  <assemble>')
    for o in objects:
        lines.append(
            f'   <assemble_item object_id="{o["outer_id"]}" instance_id="0" '
            f'transform="1 0 0 0 1 0 0 0 1 {o["tx"]:.6f} {o["ty"]:.6f} 0" offset="0 0 0"/>'
        )
    lines.append('  </assemble>')
    lines.append('</config>')
    lines.append('')
    return '\n'.join(lines)


def load_print_settings(template_path, **overrides):
    """Read `Metadata/project_settings.config` (a JSON document) out of an
    existing Bambu Studio project .3mf, or (if `template_path` ends in
    `.json`) load that flattened settings document directly - see
    `bambu_a1_mini_tpu_settings.json` and its own note on how it was built.
    Either way, any of its keys can be overridden."""
    if str(template_path).endswith('.json'):
        settings = json.load(open(template_path))
    else:
        with zipfile.ZipFile(template_path) as z:
            settings = json.loads(z.read('Metadata/project_settings.config'))
    settings.update(overrides)
    return settings


def write_bambu_project(path, named_parts, template_path, extruder=1,
                         application='BambuStudio-02.07.01.57', creation_date=None,
                         tessellate_tolerance=1e-3, tessellate_angular_tolerance=0.1,
                         **settings_overrides):
    """Write a Bambu Studio project .3mf to `path`: one plate holding one
    build item per (name, build123d Shape) in `named_parts`, laid out with
    guaranteed clearance (see `_place_on_plate`), plus print settings cloned
    from `template_path` (another Bambu Studio project .3mf, or a flattened
    `.json` settings document - see `load_print_settings`) with
    `settings_overrides` applied - e.g. `sparse_infill_pattern='gyroid'`.
    `extruder` is the 1-based filament slot every object is assigned to
    (default 1, the only slot there is on a single-filament, no-AMS setup -
    see `bambu_a1_mini_tpu_settings.json`); check it matches your own
    filament setup if you've changed the cloned settings' filament list.
    """
    if creation_date is None:
        creation_date = datetime.date.today().isoformat()
    settings = load_print_settings(template_path, **settings_overrides)
    placements = _place_on_plate([part for _, part in named_parts])

    objects = []
    for i, ((name, part), (tx, ty)) in enumerate(zip(named_parts, placements)):
        vertices, triangles = part.tessellate(tessellate_tolerance, tessellate_angular_tolerance)
        vertices, triangles = _dedupe_mesh(vertices, triangles)
        objects.append({
            'name': name,
            'outer_id': 2 * i + 2,
            'inner_id': 2 * i + 1,
            'uuid': uuid.uuid4(),            # the outer (component-referencing) object, in 3dmodel.model
            'component_uuid': uuid.uuid4(),  # that object's <component> reference, in 3dmodel.model
            'inner_uuid': uuid.uuid4(),      # the actual mesh object, in object_N.model itself
            'item_uuid': uuid.uuid4(),       # the <build><item>, in 3dmodel.model
            'tx': tx, 'ty': ty,
            'vertices': vertices, 'triangles': triangles,
            'ntris': len(triangles),
        })

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', CONTENT_TYPES)
        z.writestr('_rels/.rels', TOP_LEVEL_RELS)
        z.writestr('3D/3dmodel.model', _top_model_xml(objects, application, creation_date))
        rels = ['<?xml version="1.0" encoding="UTF-8"?>',
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
        for o in objects:
            rels.append(
                f' <Relationship Target="/3D/Objects/object_{o["inner_id"]}.model" Id="rel-{o["inner_id"]}" '
                'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
            )
        rels.append('</Relationships>')
        z.writestr('3D/_rels/3dmodel.model.rels', '\n'.join(rels))
        for o in objects:
            z.writestr(f'3D/Objects/object_{o["inner_id"]}.model',
                       _object_model_xml(o['inner_id'], o['inner_uuid'], o['vertices'], o['triangles']))
        z.writestr('Metadata/model_settings.config', _model_settings_xml(objects, extruder))
        z.writestr('Metadata/project_settings.config', json.dumps(settings, indent=4))
