"""Parse a triangle mesh out of a raw .model XML file, or directly out of a
zipped .3mf archive (Bambu/3MF-consortium format)."""
import xml.etree.ElementTree as ET
import zipfile
import numpy as np
import sys

NS = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'


def _parse_xml(root):
    verts = [(float(v.get('x')), float(v.get('y')), float(v.get('z')))
             for v in root.iter(f'{NS}vertex')]
    tris = [(int(t.get('v1')), int(t.get('v2')), int(t.get('v3')))
            for t in root.iter(f'{NS}triangle')]
    return np.array(verts), np.array(tris)


def parse_model(path):
    """path: a raw .model XML file (e.g. extracted 3D/Objects/object_N.model)."""
    tree = ET.parse(path)
    return _parse_xml(tree.getroot())


def parse_3mf_object(archive_path, object_path='3D/Objects/object_1.model'):
    """Read one object's mesh straight out of a .3mf zip archive - no manual
    unzip needed. Use `list_3mf_objects` to see what's available."""
    with zipfile.ZipFile(archive_path) as z:
        with z.open(object_path) as f:
            root = ET.parse(f).getroot()
    return _parse_xml(root)


def list_3mf_objects(archive_path):
    """List the /3D/Objects/*.model paths inside a .3mf archive."""
    with zipfile.ZipFile(archive_path) as z:
        return sorted(n for n in z.namelist() if n.startswith('3D/Objects/') and n.endswith('.model'))


if __name__ == '__main__':
    path = sys.argv[1]
    if path.lower().endswith('.3mf'):
        print("objects in archive:", list_3mf_objects(path))
        verts, tris = parse_3mf_object(path, sys.argv[2] if len(sys.argv) > 2 else list_3mf_objects(path)[0])
    else:
        verts, tris = parse_model(path)
    print("verts", verts.shape, "tris", tris.shape)
    print("bbox min", verts.min(axis=0))
    print("bbox max", verts.max(axis=0))
