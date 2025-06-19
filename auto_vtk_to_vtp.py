#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch convert all .vtk files under a directory tree to .vtp,
writing the outputs (preserving relative paths) into assets/vtu.
Uses VTK's readers and writers with Update()/Write().
"""

import os
import sys
import vtk

def vtk2vtp(invtkfile, outvtpfile, binary=False):
    """Convert one .vtk UnstructuredGrid to .vtp XML PolyData."""
    # reader for unstructured grid
    reader = vtk.vtkUnstructuredGridReader()
    reader.SetFileName(invtkfile)
    reader.Update()

    unstructured_grid = reader.GetOutput()
    
    # Convert unstructured grid to polydata using geometry filter
    geometry_filter = vtk.vtkGeometryFilter()
    geometry_filter.SetInputData(unstructured_grid)
    geometry_filter.Update()
    
    polydata = geometry_filter.GetOutput()

    # writer
    writer = vtk.vtkXMLPolyDataWriter()
    writer.SetFileName(outvtpfile)
    if binary:
        writer.SetDataModeToBinary()
    else:
        writer.SetDataModeToAscii()
    writer.SetInputData(polydata)
    writer.Write()

def convert_all_vtk2vtp(vtk_root_dir="assets/vtk", vtp_root_dir="assets/vtp", binary=False):
    """
    Walk vtk_root_dir, convert each .vtk found to .vtp under vtp_root_dir,
    preserving directory structure.
    """
    if not os.path.isdir(vtk_root_dir):
        print(f"❌ Input directory not found: {vtk_root_dir}")
        return

    for root, dirs, files in os.walk(vtk_root_dir):
        # compute relative path from the vtk root
        rel = os.path.relpath(root, vtk_root_dir)
        rel = "" if rel == "." else rel

        # ensure corresponding output directory exists
        out_dir = os.path.join(vtp_root_dir, rel)
        os.makedirs(out_dir, exist_ok=True)

        for fname in files:
            if not fname.lower().endswith(".vtk"):
                continue

            invtk = os.path.join(root, fname)
            outvtp = os.path.join(out_dir, fname[:-4] + ".vtp")
            try:
                print(f"Converting: {invtk} → {outvtp}")
                vtk2vtp(invtk, outvtp, binary=binary)
                print(f"✅ Success: {outvtp}")
            except Exception as e:
                print(f"❌ Failed: {invtk} ({e})")

if __name__ == "__main__":
    # parse optional -b flag and optional input/output dirs
    args = sys.argv[1:]
    binary = False
    if "-b" in args:
        args.remove("-b")
        binary = True

    # allow user to override input/output roots
    if len(args) >= 1:
        vtk_root = args[0]
    else:
        vtk_root = "assets/vtk"
    if len(args) >= 2:
        vtp_root = args[1]
    else:
        vtp_root = os.path.join("assets", "vtp")

    print(f"🚀 Batch converting .vtk → .vtp\n  from: {vtk_root}\n  to:   {vtp_root}\n  binary: {binary}")
    convert_all_vtk2vtp(vtk_root, vtp_root, binary=binary)
